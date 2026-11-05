"""Collect every finished task into analysable tables (Parquet, under the campaign directory).

Tables (aggregates only; per-stay predictions stay in tasks/*/private/):
metrics (long), per_class, confusion (long), abs_error, hpo_trials, timings, failures, not_applicable.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from triagebench.runner.ledger import Ledger
from triagebench.utils.io import atomic_write_parquet, read_json, read_jsonl

SCALAR_EXCLUDE = {"confusion", "abs_error_counts"}
KEYS = ["variant", "seed", "model", "model_kind", "model_group", "strategy"]


def _task_results(cdir: Path) -> list[dict]:
    out = []
    for d in sorted((cdir / "tasks").glob("*")):
        if (d / "DONE").exists() and (d / "result.json").exists():
            out.append(read_json(d / "result.json"))
    return out


def aggregate_campaign(cdir: Path) -> dict[str, pd.DataFrame]:
    cdir = Path(cdir)
    results = _task_results(cdir)
    metrics, per_class, confusion, abs_err, timings = [], [], [], [], []
    for r in results:
        key = {k: r["task"][k] for k in KEYS}
        for split in ("val", "test"):
            m = r[split]
            for name, value in m.items():
                if name in SCALAR_EXCLUDE or isinstance(value, (list, dict)):
                    continue
                metrics.append({**key, "split": split, "metric": name, "value": float(value) if value is not None else np.nan})
            for lab in range(1, 6):
                per_class.append({**key, "split": split, "label": lab, "precision": m[f"precision_{lab}"],
                                  "recall": m[f"recall_{lab}"], "f1": m[f"f1_{lab}"], "support": m[f"support_{lab}"],
                                  "predicted": m[f"predicted_{lab}"]})
            for i, row in enumerate(m["confusion"]):
                for j, count in enumerate(row):
                    confusion.append({**key, "split": split, "true": i + 1, "pred": j + 1, "count": int(count)})
            for dist, count in m["abs_error_counts"].items():
                abs_err.append({**key, "split": split, "distance": int(dist), "count": int(count)})
        t = r["timing"]
        timings.append({**key, "final_fit_seconds": t["final_fit_seconds"], "predict_test_seconds": t["predict_test_seconds"],
                        "task_seconds": t["task_seconds"], "hpo_seconds": r["hpo"]["trial_seconds_total"],
                        "n_train": r["data"]["n_train"], "n_test": r["data"]["n_test"],
                        "final_train_cap": t.get("final_train_cap"), "threads": r["env"]["threads"],
                        "peak_rss_mb": r["env"].get("peak_rss_mb"), "best_trial_index": r["best_trial_index"],
                        "best_params": json.dumps(r["frozen_config"]["params"], sort_keys=True),
                        "hpo_n_ok": r["hpo"]["n_ok"], "hpo_n_error": r["hpo"]["n_error"],
                        "n_warnings_final": t.get("n_warnings_final", 0)})

    trials = []
    ledger = Ledger(cdir)
    failures = []
    for d in sorted((cdir / "tasks").glob("*")):
        parts = d.name.split("__")
        if len(parts) != 4:
            continue
        base = {"variant": parts[0], "seed": int(parts[1].lstrip("s")), "model": parts[2], "strategy": parts[3]}
        for t in read_jsonl(d / "trials.jsonl"):
            row = {**base, "index": t["index"], "status": t.get("status"), "params": json.dumps(t.get("params"), sort_keys=True),
                   "fit_seconds": t.get("fit_seconds"), "predict_val_seconds": t.get("predict_val_seconds"),
                   "n_warnings": t.get("n_warnings"), "error": t.get("error")}
            for k, v in (t.get("val") or {}).items():
                row[f"val_{k}"] = v
            trials.append(row)
        st = ledger.state(d.name)
        if st.get("state") == "failed" or ((d / "error.json").exists() and not ledger.is_done(d.name)):
            err = read_json(d / "error.json") if (d / "error.json").exists() else {}
            failures.append({**base, "state": st.get("state"), "attempts": st.get("attempts"),
                             "error": err.get("error"), "last_reason": (st.get("history") or [{}])[-1].get("reason")})

    grid = read_json(cdir / "grid.json") if (cdir / "grid.json").exists() else {"not_applicable": []}
    tables = {
        "metrics": pd.DataFrame(metrics),
        "per_class": pd.DataFrame(per_class),
        "confusion": pd.DataFrame(confusion),
        "abs_error": pd.DataFrame(abs_err),
        "timings": pd.DataFrame(timings),
        "hpo_trials": pd.DataFrame(trials),
        "failures": pd.DataFrame(failures),
        "not_applicable": pd.DataFrame(grid.get("not_applicable", [])),
    }
    for name, df in tables.items():
        atomic_write_parquet(df, cdir / "tables" / f"{name}.parquet")
    return tables


def load_predictions(cdir: Path, partitions: tuple[str, ...] = ("test",), max_rows: int = 80_000_000) -> pd.DataFrame | None:
    """Concatenate private per-stay predictions (kept in memory only, never written to reports)."""
    frames, total = [], 0
    for d in sorted((Path(cdir) / "tasks").glob("*")):
        path = d / "private" / "predictions.parquet"
        if not path.exists() or not (d / "DONE").exists():
            continue
        variant, seed, model, strategy = d.name.split("__")
        df = pd.read_parquet(path, columns=["stay_id", "subject_id", "partition", "y_true", "y_pred"])
        df = df[df["partition"].isin(partitions)]
        total += len(df)
        if total > max_rows:
            return None
        df = df.assign(variant=variant, seed=int(seed.lstrip("s")), model=model, strategy=strategy)
        frames.append(df)
    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    for c in ("variant", "model", "strategy", "partition"):
        out[c] = out[c].astype("category")
    return out
