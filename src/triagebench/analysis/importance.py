"""Grouped permutation importance (F5) on the TEST partition of each seed.

Models: the best SIMPLE and the best COMPLEX primary model, chosen by mean VALIDATION macro-F1
(variant A, strategy none) — never by test. Each frozen configuration is refitted on train
(deterministic, same seed) and every raw variable is permuted as a group: a vital sign together
with its missing indicator (both derive from the same raw column), pain_value together with
pain_status. Importance = metric(original) - metric(permuted), mean over repeats.
Permuting the test features uses no label for any decision; outputs are aggregates only.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from triagebench.data.schema import VITALS
from triagebench.utils.io import atomic_write_json, atomic_write_parquet, read_json

METRICS = ("macro_f1", "qwk", "balanced_accuracy", "recall_1")


def choose_models(metrics: pd.DataFrame, cfg: dict, variant: str) -> list[str]:
    val = metrics[(metrics.variant == variant) & (metrics.split == "val") & (metrics.strategy == "none")
                  & (metrics.metric == "macro_f1")]
    chosen = []
    for group in ("simple", "complex"):
        members = (cfg["models"].get("groups") or {}).get(group, [])
        means = val[val.model.isin(members)].groupby("model").value.mean()
        if not means.empty:
            chosen.append(str(means.idxmax()))
    return chosen


def _groups(vcfg: dict) -> dict[str, list[str]]:
    groups = {v: [v] for v in VITALS if v in vcfg["numeric_features"]}
    pain = [c for c in ("pain_value", "pain_status") if c in vcfg["numeric_features"] + vcfg["categorical_features"]]
    if pain:
        groups["pain"] = pain
    return groups


def _one(job: dict) -> dict:
    """Refit one frozen config and permute each group (runs in a separate process)."""
    from triagebench.evaluation.metrics import compute_metrics
    from triagebench.evaluation.protocol import TaskContext, load_task_data
    from triagebench.models.imbalance import build_pipeline, fit_params, subsample_cap
    from triagebench.utils.seeds import derive_seed

    cfg, cdir, prepared = job["cfg"], Path(job["cdir"]), Path(job["prepared"])
    res = read_json(cdir / "tasks" / job["task_id"] / "result.json")
    variant, seed, model, strategy = (res["task"][k] for k in ("variant", "seed", "model", "strategy"))
    vcfg = cfg["variants"][variant]
    ctx = TaskContext(cfg, cdir, prepared, 1, "")
    parts = load_task_data(ctx, variant, seed)
    feats = list(vcfg["numeric_features"]) + list(vcfg["categorical_features"])
    X_tr, X_te = parts["train"][feats], parts["test"][feats]
    y_tr = parts["train"]["acuity"].to_numpy(dtype=int) - 1
    y_te = parts["test"]["acuity"].to_numpy(dtype=int)
    cap = subsample_cap(model, cfg, "final")
    pipe = build_pipeline(model, res["frozen_config"]["params"], strategy, cfg, vcfg, derive_seed(seed, model, "model"), 1, cap=cap)
    pipe.fit(X_tr, y_tr, **fit_params(model, strategy, y_tr, cap=cap))
    base = compute_metrics(y_te, np.asarray(pipe.predict(X_te)).astype(int) + 1)
    rows = []
    rng = np.random.default_rng(derive_seed(seed, model, "permutation"))
    for group, cols in _groups(vcfg).items():
        for r in range(int(job["n_repeats"])):
            idx = rng.permutation(len(X_te))
            Xp = X_te.copy()
            for c in cols:
                Xp[c] = X_te[c].to_numpy()[idx]
            m = compute_metrics(y_te, np.asarray(pipe.predict(Xp)).astype(int) + 1)
            rows.append({"variant": variant, "seed": seed, "model": model, "strategy": strategy, "group": group,
                         "repeat": r, **{f"{k}_base": base[k] for k in METRICS},
                         **{f"{k}_drop": base[k] - m[k] for k in METRICS}})
    out = {"task_id": job["task_id"], "rows": rows}
    atomic_write_json(Path(job["journal"]), out)
    return out


def run_importance(cfg: dict, cdir: Path, prepared: Path, metrics: pd.DataFrame, variant: str,
                   n_repeats: int = 5, workers: int = 4) -> Path | None:
    from joblib import Parallel, delayed

    models = choose_models(metrics, cfg, variant)
    jobs = []
    for model in models:
        for d in sorted((Path(cdir) / "tasks").glob(f"{variant}__s*__{model}__none")):
            if not (d / "DONE").exists():
                continue
            journal = Path(cdir) / "importance" / f"{d.name}.json"
            if journal.exists():
                continue
            jobs.append({"cfg": cfg, "cdir": str(cdir), "prepared": str(prepared), "task_id": d.name,
                         "n_repeats": n_repeats, "journal": str(journal)})
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[var] = "1"
    if jobs:
        Parallel(n_jobs=max(1, workers), backend="loky")(delayed(_one)(j) for j in jobs)
    rows = [r for f in sorted((Path(cdir) / "importance").glob("*.json")) for r in read_json(f)["rows"]]
    if not rows:
        return None
    return atomic_write_parquet(pd.DataFrame(rows), Path(cdir) / "tables" / "importance.parquet")


def importance_markdown(df: pd.DataFrame) -> str:
    from triagebench.reporting.tables import md_table

    if df.empty:
        return "_—_"
    per_seed = df.groupby(["model", "group", "seed"])[["macro_f1_drop", "qwk_drop"]].mean().reset_index()
    out = []
    for model in per_seed.model.unique():
        sub = per_seed[per_seed.model == model]
        agg = sub.groupby("group").agg(f1=("macro_f1_drop", "mean"), f1_sd=("macro_f1_drop", "std"),
                                       qwk=("qwk_drop", "mean"), qwk_sd=("qwk_drop", "std"), seeds=("seed", "nunique"))
        agg = agg.sort_values("f1", ascending=False)
        rows = [[g, int(r.seeds), f"{r.f1:.4f} ± {0 if np.isnan(r.f1_sd) else r.f1_sd:.4f}",
                 f"{r.qwk:.4f} ± {0 if np.isnan(r.qwk_sd) else r.qwk_sd:.4f}"] for g, r in agg.iterrows()]
        out += [f"`{model}` (estratégia none; queda média ao permutar a variável, média ± DP entre seeds):", "",
                md_table(["variável", "seeds", "queda de Macro-F1", "queda de QWK"], rows), ""]
    return "\n".join(out)
