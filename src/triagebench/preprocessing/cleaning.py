"""Versioned cleaning rules with a before/after log for every rule.

Row rules remove stays (kept in ``excluded`` and saved privately, never destroyed).
Value rules only turn implausible values into NaN / clip them; the stay is kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from triagebench.data.schema import ACUITY_LEVELS, VITALS
from triagebench.preprocessing.pain import PainRules, parse_pain


@dataclass
class CleanResult:
    data: pd.DataFrame
    excluded: dict[str, pd.DataFrame] = field(default_factory=dict)
    log: list[dict] = field(default_factory=list)


def by_acuity(mask: pd.Series | np.ndarray, acuity: pd.Series) -> dict[str, int]:
    sel = acuity[np.asarray(mask, dtype=bool)]
    counts = {str(level): int((sel == level).sum()) for level in ACUITY_LEVELS}
    counts["missing"] = int(sel.isna().sum())
    return counts


def _row_rule(df: pd.DataFrame, mask: pd.Series, rule: str, reason: str, result: CleanResult,
              acuity_col: str) -> pd.DataFrame:
    mask = mask.fillna(False).astype(bool)
    result.excluded[rule] = df[mask].copy()
    result.log.append({
        "rule": rule, "type": "row", "reason": reason,
        "n_rows_before": int(len(df)), "n_removed": int(mask.sum()), "n_rows_after": int((~mask).sum()),
        "by_acuity": by_acuity(mask, df[acuity_col]),
    })
    return df[~mask]


def _value_log(result: CleanResult, rule: str, variable: str, action: str, mask: pd.Series,
               df: pd.DataFrame) -> None:
    result.log.append({
        "rule": rule, "type": "value", "variable": variable, "action": action,
        "n_rows": int(len(df)), "n_values_affected": int(mask.sum()),
        "by_acuity": by_acuity(mask, df["acuity"]),
    })


def apply_value_rules(df: pd.DataFrame, ccfg: dict, result: CleanResult) -> pd.DataFrame:
    df = df.copy()

    lo, hi = ccfg["celsius_like_range"]
    action = ccfg.get("celsius_like_action", "convert")
    mask = df["temperature"].between(lo, hi)
    if action == "convert":
        df.loc[mask, "temperature"] = df.loc[mask, "temperature"] * 9.0 / 5.0 + 32.0
    elif action == "nan":
        df.loc[mask, "temperature"] = np.nan
    elif action != "keep":
        raise ValueError(f"unknown celsius_like_action {action!r}")
    _value_log(result, "temperature_celsius_like", "temperature", action, mask, df)

    for var in ccfg.get("zero_to_nan", []) or []:
        mask = df[var] == 0
        df.loc[mask, var] = np.nan
        _value_log(result, "zero_to_nan", var, "nan", mask, df)

    for var, r in ccfg["ranges"].items():
        x = df[var]
        out = (x < r["outlier_low"]) | (x > r["outlier_high"])
        clip_low = (x >= r["outlier_low"]) & (x < r["valid_low"])
        clip_high = (x > r["valid_high"]) & (x <= r["outlier_high"])
        df.loc[out, var] = np.nan
        df.loc[clip_low, var] = r["valid_low"]
        df.loc[clip_high, var] = r["valid_high"]
        _value_log(result, "range_outlier_to_nan", var, "nan", out, df)
        _value_log(result, "range_clip_low", var, f"clip_to_{r['valid_low']}", clip_low, df)
        _value_log(result, "range_clip_high", var, f"clip_to_{r['valid_high']}", clip_high, df)

    action = ccfg.get("dbp_ge_sbp_action", "none")
    mask = df["dbp"].notna() & df["sbp"].notna() & (df["dbp"] >= df["sbp"])
    if action == "nan_both":
        df.loc[mask, ["sbp", "dbp"]] = np.nan
    elif action != "none":
        raise ValueError(f"unknown dbp_ge_sbp_action {action!r}")
    _value_log(result, "dbp_ge_sbp", "sbp/dbp", action, mask, df)
    return df


def prepare_variant(base: pd.DataFrame, variant_cfg: dict, ccfg: dict) -> CleanResult:
    """``base`` = output of ``load_triage`` (with ``acuity_raw`` and ``pain_raw``)."""
    result = CleanResult(data=pd.DataFrame())
    df = base.copy()

    acuity = df["acuity_raw"]
    df = _row_rule(df, acuity.isna(), "acuity_missing", "no label: cannot train or evaluate", result, "acuity_raw")
    invalid = ~df["acuity_raw"].isin(ACUITY_LEVELS)
    df = _row_rule(df, invalid, "acuity_invalid", "label outside 1..5", result, "acuity_raw")
    df = df.assign(acuity=df["acuity_raw"].astype("int64")).drop(columns=["acuity_raw"])

    parsed = parse_pain(df["pain_raw"], PainRules.from_config(ccfg["pain"]))
    df = pd.concat([df, parsed], axis=1)

    df = apply_value_rules(df, ccfg, result)

    if variant_cfg.get("exclude_non_numeric_pain"):
        df = _row_rule(df, df["pain_kind"] != "numeric", "pain_not_numeric",
                       "variant B: pain is not a plain number in [0, 10]", result, "acuity")

    keep = ["stay_id", "subject_id", "acuity", *VITALS, "pain_value", "pain_status", "pain_kind", "pain_raw"]
    result.data = df[keep].reset_index(drop=True)
    return result
