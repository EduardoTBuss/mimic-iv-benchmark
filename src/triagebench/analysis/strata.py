"""Pre-registered stratified test report (amendment of 05/11, before any result):
stays with ALL six vitals present and a numeric pain score ("complete") vs the rest.

Missing vitals and non-numeric pain are strong proxies of acuity 1 (documentation pattern);
this table shows how much of each model's performance comes from the incomplete stratum.
Computed from the saved private predictions, no retraining; output is aggregate only.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from triagebench.data.schema import VITALS
from triagebench.evaluation.metrics import compute_metrics
from triagebench.reporting.disclosure import mask_count
from triagebench.reporting.tables import md_table

METRICS = ("macro_f1", "balanced_accuracy", "qwk", "recall_1")


def stratified_test_metrics(cdir: Path, prepared: Path, variants: list[str], strategy: str = "none") -> pd.DataFrame:
    rows = []
    for variant in variants:
        path = Path(prepared) / "private" / f"{variant}.parquet"
        if not path.exists():
            continue
        data = pd.read_parquet(path, columns=["stay_id", *VITALS, "pain_status"])
        complete = data[list(VITALS)].notna().all(axis=1) & (data["pain_status"].astype(str) == "numeric")
        flag = pd.Series(complete.to_numpy(), index=data["stay_id"].to_numpy())
        for d in sorted(Path(cdir, "tasks").glob(f"{variant}__s*__*__{strategy}")):
            pred_path = d / "private" / "predictions.parquet"
            if not (d / "DONE").exists() or not pred_path.exists():
                continue
            _, seed, model, _ = d.name.split("__")
            p = pd.read_parquet(pred_path, columns=["stay_id", "partition", "y_true", "y_pred"])
            p = p[p["partition"] == "test"]
            is_complete = flag.reindex(p["stay_id"].to_numpy()).fillna(False).to_numpy(dtype=bool)
            for name, mask in (("complete", is_complete), ("incomplete", ~is_complete)):
                sub = p[mask]
                if sub.empty:
                    continue
                m = compute_metrics(sub["y_true"], sub["y_pred"])
                rows.append({"variant": variant, "seed": int(seed.lstrip("s")), "model": model, "stratum": name,
                             "n": int(len(sub)), "n_acuity_1": int((sub["y_true"] == 1).sum()),
                             **{k: m[k] for k in METRICS}})
    return pd.DataFrame(rows)


def strata_markdown(df: pd.DataFrame, order: list[str], k: int = 11) -> str:
    if df.empty:
        return "_sem predições para estratificar_"
    out = []
    for variant in df["variant"].unique():
        rows = []
        sub_v = df[df["variant"] == variant]
        for model in [m for m in order if m in set(sub_v["model"])]:
            cells = [model]
            for stratum in ("complete", "incomplete"):
                s = sub_v[(sub_v["model"] == model) & (sub_v["stratum"] == stratum)]
                cells += [mask_count(round(s["n"].mean()), k) if not s.empty else "—"]
                cells += [f"{s[m].mean():.4f}" if not s.empty else "—" for m in METRICS]
            rows.append(cells)
        heads = ["modelo"] + [f"{st}: {h}" for st in ("completos", "incompletos") for h in ("n médio/seed", *METRICS)]
        out += [f"Variante `{variant}`, estratégia none, teste (média entre seeds):", "", md_table(heads, rows), ""]
    return "\n".join(out)
