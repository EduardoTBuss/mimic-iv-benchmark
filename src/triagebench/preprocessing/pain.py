"""Parse the free-text ``pain`` column (free text since MIMIC-IV-ED v2.0).

Every raw string is kept (``pain_raw``, private) and mapped to:

* ``pain_value``  float in [min, max] or NaN
* ``pain_kind``   fine-grained parser outcome (audit/traceability)
* ``pain_status`` coarse category used as a model feature (numeric/missing/unable/other)

Kinds: numeric ("7", "7.5"), range ("5-6" -> mean), fraction ("7/10"), out_of_range ("13"),
missing (empty), unable (matches ``unable_patterns``), text_other (anything else).
Variant B keeps only ``kind == "numeric"`` (a plain number in [min, max]).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

KINDS = ("numeric", "range", "fraction", "out_of_range", "missing", "unable", "text_other")

_NUMBER = r"\d+(?:[.,]\d+)?"
_NUM_RE = re.compile(rf"^({_NUMBER})$")
_RANGE_RE = re.compile(rf"^({_NUMBER})\s*(?:-|to)\s*({_NUMBER})$")
_FRACTION_RE = re.compile(rf"^({_NUMBER})\s*/\s*10$")


def normalize_pain_string(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _to_float(text: str) -> float:
    return float(text.replace(",", "."))


@dataclass(frozen=True)
class PainRules:
    min_value: float = 0.0
    max_value: float = 10.0
    range_policy: str = "mean"
    unable_patterns: tuple[str, ...] = ()
    status_map: dict = field(default_factory=lambda: {
        "numeric": "numeric", "range": "numeric", "fraction": "numeric", "missing": "missing",
        "unable": "unable", "out_of_range": "other", "text_other": "other",
    })
    status_categories: tuple[str, ...] = ("numeric", "missing", "unable", "other")

    @classmethod
    def from_config(cls, pain_cfg: dict) -> PainRules:
        return cls(
            min_value=float(pain_cfg.get("min", 0)),
            max_value=float(pain_cfg.get("max", 10)),
            range_policy=pain_cfg.get("range_policy", "mean"),
            unable_patterns=tuple(pain_cfg.get("unable_patterns", ())),
            status_map=dict(pain_cfg.get("status_map", cls().status_map)),
            status_categories=tuple(pain_cfg.get("status_categories", cls().status_categories)),
        )

    def unable_regex(self) -> re.Pattern | None:
        if not self.unable_patterns:
            return None
        return re.compile("|".join(f"(?:{p})" for p in self.unable_patterns), re.IGNORECASE)


def classify_pain(raw: object, rules: PainRules, unable_re: re.Pattern | None = None) -> tuple[float, str]:
    """Return ``(value, kind)`` for one raw entry."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)) or raw is pd.NA:
        return math.nan, "missing"
    text = normalize_pain_string(raw)
    if text == "":
        return math.nan, "missing"
    lo, hi = rules.min_value, rules.max_value

    m = _NUM_RE.match(text)
    if m:
        value = _to_float(m.group(1))
        return (value, "numeric") if lo <= value <= hi else (math.nan, "out_of_range")
    m = _RANGE_RE.match(text)
    if m:
        a, b = _to_float(m.group(1)), _to_float(m.group(2))
        if lo <= a <= hi and lo <= b <= hi:
            value = (a + b) / 2 if rules.range_policy == "mean" else max(a, b)
            return value, "range"
        return math.nan, "out_of_range"
    m = _FRACTION_RE.match(text)
    if m:
        value = _to_float(m.group(1))
        return (value, "fraction") if lo <= value <= hi else (math.nan, "out_of_range")
    if unable_re is not None and unable_re.search(text):
        return math.nan, "unable"
    return math.nan, "text_other"


def parse_pain(raw: pd.Series, rules: PainRules) -> pd.DataFrame:
    """Vectorised over unique strings; index-aligned with ``raw``."""
    unable_re = rules.unable_regex()
    as_obj = raw.astype(object)
    uniques = pd.unique(as_obj[as_obj.notna()])
    table = {u: classify_pain(u, rules, unable_re) for u in uniques}
    values = as_obj.map(lambda x: table[x][0] if x is not None and not pd.isna(x) else math.nan)
    kinds = as_obj.map(lambda x: table[x][1] if x is not None and not pd.isna(x) else "missing")
    unknown = set(kinds.unique()) - set(rules.status_map)
    if unknown:
        raise ValueError(f"pain kinds without a status mapping: {sorted(unknown)}")
    return pd.DataFrame(
        {
            "pain_value": values.astype("float64").to_numpy(),
            "pain_kind": kinds.astype(object).to_numpy(),
            "pain_status": kinds.map(rules.status_map).astype(object).to_numpy(),
        },
        index=raw.index,
    )


def is_plain_numeric(kinds: pd.Series) -> np.ndarray:
    return (kinds == "numeric").to_numpy()
