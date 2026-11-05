"""Load ``triage`` and ``edstays`` with a strict schema check (never loads chiefcomplaint)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from triagebench.data.schema import (
    EDSTAYS_COLUMNS,
    EDSTAYS_LOAD_COLUMNS,
    TRIAGE_COLUMNS,
    TRIAGE_LOAD_COLUMNS,
    VITALS,
    DataConsistencyError,
    SchemaMismatchError,
)


def table_path(cfg: dict, table: str) -> Path:
    ds = cfg["dataset"]
    return Path(ds["extract_dir"]) / f"mimic-iv-ed-{ds['version']}" / ds["tables"][table]


def check_header(path: Path, expected: tuple[str, ...]) -> list[str]:
    columns = list(pd.read_csv(path, nrows=0).columns)
    if columns != list(expected):
        raise SchemaMismatchError(
            f"{path.name}: columns {columns} differ from the documented v2.2 schema {list(expected)}"
        )
    return columns


def _ids(raw: pd.Series, name: str) -> pd.Series:
    ids = pd.to_numeric(raw, errors="coerce")
    if ids.isna().any():
        raise DataConsistencyError(f"{int(ids.isna().sum())} rows with missing/non-numeric {name}")
    return ids.astype("int64")


def load_triage(path: Path) -> tuple[pd.DataFrame, dict]:
    """Return (frame, load_report). Vitals become float; pain is kept as the raw string."""
    check_header(path, TRIAGE_COLUMNS)
    raw = pd.read_csv(
        path,
        usecols=list(TRIAGE_LOAD_COLUMNS),
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )
    report: dict = {"n_rows": int(len(raw)), "non_numeric_coerced": {}}
    df = pd.DataFrame({"subject_id": _ids(raw["subject_id"], "subject_id"), "stay_id": _ids(raw["stay_id"], "stay_id")})
    for var in VITALS:
        num = pd.to_numeric(raw[var], errors="coerce")
        report["non_numeric_coerced"][var] = int((num.isna() & raw[var].notna()).sum())
        df[var] = num.astype("float64")
    df["pain_raw"] = raw["pain"].astype(object).where(raw["pain"].notna(), None)
    acuity = pd.to_numeric(raw["acuity"], errors="coerce")
    report["acuity_non_numeric"] = int((acuity.isna() & raw["acuity"].notna()).sum())
    df["acuity_raw"] = acuity.astype("float64")
    return df, report


def load_edstays(path: Path) -> pd.DataFrame:
    check_header(path, EDSTAYS_COLUMNS)
    raw = pd.read_csv(path, usecols=list(EDSTAYS_LOAD_COLUMNS), dtype=str)
    return pd.DataFrame({"subject_id": _ids(raw["subject_id"], "subject_id"), "stay_id": _ids(raw["stay_id"], "stay_id")})


def consistency_report(triage: pd.DataFrame, edstays: pd.DataFrame) -> dict:
    merged = triage[["stay_id", "subject_id"]].merge(
        edstays[["stay_id", "subject_id"]].drop_duplicates("stay_id"),
        on="stay_id",
        how="left",
        suffixes=("", "_ed"),
        indicator=True,
    )
    both = merged["_merge"] == "both"
    return {
        "triage_duplicated_stay_id": int(triage["stay_id"].duplicated().sum()),
        "edstays_duplicated_stay_id": int(edstays["stay_id"].duplicated().sum()),
        "triage_stays_not_in_edstays": int((merged["_merge"] == "left_only").sum()),
        "edstays_stays_without_triage": int((~edstays["stay_id"].isin(triage["stay_id"])).sum()),
        "subject_id_mismatch": int((both & (merged["subject_id"] != merged["subject_id_ed"])).sum()),
    }


def assert_consistent(report: dict) -> None:
    problems = {k: v for k, v in report.items()
                if k in ("triage_duplicated_stay_id", "subject_id_mismatch") and v > 0}
    if problems:
        raise DataConsistencyError(f"structural inconsistency, stop and ask: {problems}")
