"""One task = (variant, seed, model, strategy):

1. load the prepared variant and the patient partitions of ``seed``;
2. random search: N configurations fitted on TRAIN, scored on VALIDATION (journaled per trial,
   so an interrupted task resumes from the last finished trial);
3. freeze the configuration with the best validation ``selection_metric``;
4. refit it on TRAIN and evaluate it ONCE on TEST (guarded), saving per-stay predictions privately.
"""

from __future__ import annotations

import time
import traceback
import warnings
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from triagebench.evaluation.metrics import compute_metrics, scalar_metrics
from triagebench.evaluation.test_guard import guard_test_access
from triagebench.models.imbalance import build_pipeline, fit_params, subsample_cap
from triagebench.models.registry import get_spec, model_group, model_kind
from triagebench.models.spaces import sample_configs
from triagebench.utils.config import stable_hash
from triagebench.utils.io import append_jsonl, atomic_write_parquet, read_jsonl, utc_now
from triagebench.utils.seeds import derive_seed


@dataclass
class TaskContext:
    cfg: dict
    campaign_dir: Path
    prepared_dir: Path
    threads: int
    science_hash: str


def _peak_rss_mb() -> float | None:
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except (ImportError, AttributeError):
        import psutil

        return psutil.Process().memory_info().rss / 2**20


def load_task_data(ctx: TaskContext, variant: str, seed: int) -> dict[str, pd.DataFrame]:
    data = pd.read_parquet(ctx.prepared_dir / "private" / f"{variant}.parquet")
    assign = pd.read_parquet(ctx.prepared_dir / "private" / "splits" / f"seed_{seed}.parquet")
    df = data.merge(assign[["stay_id", "partition"]], on="stay_id", how="inner", validate="one_to_one")
    if len(df) != len(data):
        raise RuntimeError(f"{len(data) - len(df)} stays of {variant} have no partition for seed {seed}")
    df["pain_status"] = df["pain_status"].astype(object)
    return {part: df[df["partition"] == part].reset_index(drop=True) for part in ("train", "val", "test")}


def _fit_predict(model, params, strategy, ctx, vcfg, seed, X_tr, y_tr_enc, X_eval_list, cap):
    pipe = build_pipeline(model, params, strategy, ctx.cfg, vcfg, seed, ctx.threads, cap=cap)
    kwargs = fit_params(model, strategy, y_tr_enc, cap=cap)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        t0 = time.perf_counter()
        pipe.fit(X_tr, y_tr_enc, **kwargs)
        fit_s = time.perf_counter() - t0
    preds, pred_s = [], []
    for X in X_eval_list:
        t1 = time.perf_counter()
        preds.append(np.asarray(pipe.predict(X)).astype(int) + 1)
        pred_s.append(time.perf_counter() - t1)
    warn = [f"{w.category.__name__}: {str(w.message)[:160]}" for w in caught]
    return pipe, preds, fit_s, pred_s, warn


def run_task(task, ctx: TaskContext) -> dict:
    cfg = ctx.cfg
    vcfg = cfg["variants"][task.variant]
    features = list(vcfg["numeric_features"]) + list(vcfg["categorical_features"])
    task_dir = ctx.campaign_dir / "tasks" / task.id
    private = task_dir / "private"
    t_start = time.perf_counter()

    parts = load_task_data(ctx, task.variant, task.seed)
    X = {p: parts[p][features] for p in parts}
    y = {p: parts[p]["acuity"].to_numpy(dtype=int) for p in parts}
    y_tr_enc = y["train"] - 1
    labels_present = set(np.unique(y["train"]))
    if labels_present != set(cfg["features"]["labels"]):
        raise RuntimeError(f"training partition lacks classes: {sorted(set(cfg['features']['labels']) - labels_present)}")

    model_seed = derive_seed(task.seed, task.model, "model")
    space = cfg["models"]["spaces"].get(task.model) or {}
    configs = sample_configs(space, int(cfg["hpo"]["n_configs"]),
                             np.random.default_rng(derive_seed(task.seed, task.model, "hpo")),
                             include_defaults=bool(cfg["hpo"].get("include_defaults", True)))
    sel = cfg["hpo"]["selection_metric"]
    hpo_cap = subsample_cap(task.model, cfg, "hpo")
    final_cap = subsample_cap(task.model, cfg, "final")

    trials_path = task_dir / "trials.jsonl"
    done = {t["index"]: t for t in read_jsonl(trials_path)}
    for i, params in enumerate(configs):
        if i in done:
            continue
        record = {"index": i, "params": params, "started_at": utc_now(), "train_cap": hpo_cap}
        try:
            _, (pred_val,), fit_s, (pred_s,), warn = _fit_predict(
                task.model, params, task.strategy, ctx, vcfg, model_seed, X["train"], y_tr_enc, [X["val"]], hpo_cap)
            record.update(status="ok", fit_seconds=fit_s, predict_val_seconds=pred_s,
                          val=scalar_metrics(compute_metrics(y["val"], pred_val)),
                          n_warnings=len(warn), warnings=warn[:3])
        except Exception as exc:  # a failing configuration does not kill the task
            record.update(status="error", error=f"{type(exc).__name__}: {exc}"[:500],
                          traceback=traceback.format_exc()[-2000:])
        append_jsonl(trials_path, record)
        done[i] = record

    ok = [t for t in done.values() if t.get("status") == "ok"]
    if not ok:
        raise RuntimeError(f"all {len(done)} configurations failed; first error: {next(iter(done.values())).get('error')}")
    best = max(ok, key=lambda t: (t["val"][sel], -t["index"]))
    frozen = {"variant": task.variant, "seed": task.seed, "model": task.model, "strategy": task.strategy,
              "params": best["params"], "science_hash": ctx.science_hash}
    frozen_hash = stable_hash(frozen)

    pipe, (pred_val,), fit_s, (pred_val_s,), warn = _fit_predict(
        task.model, best["params"], task.strategy, ctx, vcfg, model_seed, X["train"], y_tr_enc,
        [X["val"]], final_cap)
    access = guard_test_access(task_dir, frozen_hash)  # the test partition is touched only after this
    t_test = time.perf_counter()
    pred_test = np.asarray(pipe.predict(X["test"])).astype(int) + 1
    pred_test_s = time.perf_counter() - t_test
    m_val = compute_metrics(y["val"], pred_val)
    m_test = compute_metrics(y["test"], pred_test)

    ev = cfg["evaluation"]
    if ev.get("save_predictions", True):
        frames = []
        for part, pred in (("val", pred_val), ("test", pred_test)):
            frame = pd.DataFrame({
                "stay_id": parts[part]["stay_id"].to_numpy(), "subject_id": parts[part]["subject_id"].to_numpy(),
                "partition": part, "y_true": y[part].astype(np.int8), "y_pred": pred.astype(np.int8)})
            if get_spec(task.model).has_proba and hasattr(pipe, "predict_proba"):
                proba = pipe.predict_proba(X[part])
                for j in range(proba.shape[1]):
                    frame[f"proba_{j + 1}"] = proba[:, j].astype(np.float32)
            frames.append(frame)
        atomic_write_parquet(pd.concat(frames, ignore_index=True), private / "predictions.parquet")
    if task.model in (ev.get("save_models") or []):
        private.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipe, private / "model.joblib", compress=3)

    return {
        "task": {"id": task.id, "variant": task.variant, "seed": task.seed, "model": task.model,
                 "strategy": task.strategy, "model_kind": model_kind(task.model, cfg),
                 "model_group": model_group(task.model, cfg)},
        "frozen_config": frozen,
        "frozen_config_hash": frozen_hash,
        "best_trial_index": best["index"],
        "selection_metric": sel,
        "hpo": {"n_configs": len(configs), "n_ok": len(ok), "n_error": len(done) - len(ok),
                "best_val": best["val"][sel], "train_cap": hpo_cap,
                "trial_seconds_total": float(sum(t.get("fit_seconds", 0) + t.get("predict_val_seconds", 0) for t in ok))},
        "val": m_val,
        "test": m_test,
        "test_access": access,
        "timing": {"final_fit_seconds": fit_s, "predict_val_seconds": pred_val_s, "predict_test_seconds": pred_test_s,
                   "task_seconds": time.perf_counter() - t_start, "final_train_cap": final_cap,
                   "n_warnings_final": len(warn), "warnings_final": warn[:3]},
        "data": {"n_train": int(len(y["train"])), "n_val": int(len(y["val"])), "n_test": int(len(y["test"])),
                 "train_class_counts": {str(k): int((y["train"] == k).sum()) for k in cfg["features"]["labels"]}},
        "env": {"threads": ctx.threads, "peak_rss_mb": _peak_rss_mb()},
        "finished_at": utc_now(),
    }
