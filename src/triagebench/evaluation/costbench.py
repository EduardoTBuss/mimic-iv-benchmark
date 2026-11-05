"""Clean timing benchmark: refit each frozen configuration sequentially with ONE thread.

Campaign timings are contaminated by concurrent workers; this stage re-measures training and
inference cost one task at a time (validation features only, labels are not used for metrics).
Run as a subprocess so the BLAS thread limit is set before numpy is imported.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

from triagebench.utils.io import append_jsonl, atomic_write_parquet, read_json, read_jsonl, utc_now


def run_cost_benchmark(campaign: Path, prepared: Path) -> Path | None:
    from triagebench.evaluation.protocol import TaskContext, load_task_data
    from triagebench.models.imbalance import build_pipeline, fit_params, subsample_cap
    from triagebench.runner.scheduler import load_average
    from triagebench.utils.seeds import derive_seed

    cfg = yaml.safe_load((campaign / "config.resolved.yaml").read_text(encoding="utf-8"))
    cb = cfg["evaluation"].get("cost_benchmark") or {}
    if not cb.get("enabled"):
        return None
    variant, seed, repeats = cb["variant"], int(cb["seed"]), int(cb.get("repeats", 3))
    meta = read_json(campaign / "campaign.json")
    ctx = TaskContext(cfg, campaign, prepared, 1, meta["science_hash"])
    parts = load_task_data(ctx, variant, seed)
    vcfg = cfg["variants"][variant]
    feats = list(vcfg["numeric_features"]) + list(vcfg["categorical_features"])
    X_tr, X_val = parts["train"][feats], parts["val"][feats]
    y_tr = parts["train"]["acuity"].to_numpy(dtype=int) - 1
    journal = campaign / "cost_benchmark.jsonl"
    done = {(r["model"], r["strategy"], r["repeat"]) for r in read_jsonl(journal)}
    for d in sorted((campaign / "tasks").glob(f"{variant}__s{seed:02d}__*")):
        if not (d / "DONE").exists():
            continue
        res = read_json(d / "result.json")
        model, strategy, params = res["task"]["model"], res["task"]["strategy"], res["frozen_config"]["params"]
        cap = subsample_cap(model, cfg, "final")
        for rep in range(repeats):
            if (model, strategy, rep) in done:
                continue
            pipe = build_pipeline(model, params, strategy, cfg, vcfg, derive_seed(seed, model, "model"), 1, cap=cap)
            load_before = load_average()
            t0 = time.perf_counter()
            pipe.fit(X_tr, y_tr, **fit_params(model, strategy, y_tr, cap=cap))
            fit_s = time.perf_counter() - t0
            t1 = time.perf_counter()
            pipe.predict(X_val)
            pred_s = time.perf_counter() - t1
            append_jsonl(journal, {"model": model, "strategy": strategy, "repeat": rep, "fit_seconds": fit_s,
                                   "predict_seconds": pred_s, "predict_ms_per_1000": 1000 * pred_s / len(X_val) * 1000,
                                   "n_train": len(X_tr), "train_cap": cap, "n_val": len(X_val),
                                   "load1_before": load_before, "load1_after": load_average(),
                                   "host": socket.gethostname(), "at": utc_now()})
    rows = read_jsonl(journal)
    return atomic_write_parquet(pd.DataFrame(rows), campaign / "tables" / "cost_benchmark.parquet")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="triagebench.evaluation.costbench")
    p.add_argument("--campaign", required=True)
    p.add_argument("--prepared", required=True)
    p.add_argument("--nice", type=int, default=0)
    args = p.parse_args(argv)
    if os.name == "posix":
        os.umask(0o077)
        if args.nice:
            os.nice(args.nice)
    run_cost_benchmark(Path(args.campaign), Path(args.prepared))
    return 0


if __name__ == "__main__":
    sys.exit(main())
