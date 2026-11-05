"""Patient-level train/val/test partitions (a patient never crosses partitions).

Patients are stratified by their most urgent visit (min acuity) so the rare urgent classes
are spread across partitions; within each stratum patients are shuffled with the seed and
cut by the configured fractions. Deterministic: patient ids are sorted before shuffling.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PARTITIONS = ("train", "val", "test")


def assign_partitions(df: pd.DataFrame, seed: int, fractions: dict[str, float],
                      group_col: str = "subject_id", label_col: str = "acuity") -> pd.DataFrame:
    """Return one row per stay: ``stay_id, subject_id, partition``."""
    stratum = df.groupby(group_col, sort=True)[label_col].min()
    rng = np.random.default_rng(seed)
    part_of_patient: dict[int, str] = {}
    for level in sorted(stratum.unique()):
        ids = np.sort(stratum.index[stratum == level].to_numpy())
        perm = rng.permutation(ids)
        n = len(perm)
        n_test = int(round(n * fractions["test"]))
        n_val = int(round(n * fractions["val"]))
        for pid in perm[:n_test]:
            part_of_patient[int(pid)] = "test"
        for pid in perm[n_test:n_test + n_val]:
            part_of_patient[int(pid)] = "val"
        for pid in perm[n_test + n_val:]:
            part_of_patient[int(pid)] = "train"
    out = df[["stay_id", group_col]].copy()
    out["partition"] = out[group_col].map(part_of_patient)
    if out["partition"].isna().any():
        raise RuntimeError("some stays were not assigned to a partition")
    return out.reset_index(drop=True)


def split_summary(assign: pd.DataFrame, data: pd.DataFrame, group_col: str = "subject_id",
                  label_col: str = "acuity") -> dict:
    merged = assign.merge(data[["stay_id", label_col]], on="stay_id", how="left")
    summary: dict = {"partitions": {}}
    for part in PARTITIONS:
        sub = merged[merged["partition"] == part]
        summary["partitions"][part] = {
            "n_stays": int(len(sub)),
            "n_patients": int(sub[group_col].nunique()),
            "acuity_counts": {str(k): int(v) for k, v in sub[label_col].value_counts().sort_index().items()},
        }
    groups = [set(merged.loc[merged["partition"] == p, group_col]) for p in PARTITIONS]
    summary["patient_overlap"] = {
        "train_val": len(groups[0] & groups[1]),
        "train_test": len(groups[0] & groups[2]),
        "val_test": len(groups[1] & groups[2]),
    }
    return summary
