"""Pain parser (preprocessing/pain.py) with the REAL rules of configs/cleaning.yaml."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.conftest import REPO
from triagebench.preprocessing.pain import KINDS, PainRules, classify_pain, parse_pain
from triagebench.utils.config import load_config

CLEANING = load_config(REPO / "configs" / "main.yaml")["cleaning"]
RULES = PainRules.from_config(CLEANING["pain"])
UNABLE_RE = RULES.unable_regex()


def kind_value(raw):
    return classify_pain(raw, RULES, UNABLE_RE)


@pytest.mark.parametrize(("raw", "value", "kind"), [
    ("0", 0.0, "numeric"),
    ("7", 7.0, "numeric"),
    ("10", 10.0, "numeric"),
    ("7.5", 7.5, "numeric"),
    ("7,5", 7.5, "numeric"),          # decimal comma
    ("  8  ", 8.0, "numeric"),        # surrounding whitespace
    ("5-6", 5.5, "range"),
    ("5 - 6", 5.5, "range"),
    ("6-5", 5.5, "range"),            # reversed bounds: mean is order-independent
    ("4 to 8", 6.0, "range"),
    ("0-10", 5.0, "range"),
    ("7/10", 7.0, "fraction"),
    ("7 / 10", 7.0, "fraction"),
    ("0/10", 0.0, "fraction"),
])
def test_numeric_forms(raw, value, kind):
    v, k = kind_value(raw)
    assert k == kind
    assert v == pytest.approx(value)


@pytest.mark.parametrize("raw", ["13", "11", "10.5", "99", "5-13", "12/10", "-1-3"])
def test_numbers_outside_0_10_are_out_of_range_not_clipped(raw):
    v, k = kind_value(raw)
    if raw == "-1-3":  # a leading sign is not a number for this parser
        assert k == "text_other"
    else:
        assert k == "out_of_range"
    assert math.isnan(v)


@pytest.mark.parametrize("raw", ["unable", "UNABLE", "Unable ", "uta", "UTA", "u/a", "U/A", "ua", "u",
                                 "pt unable to rate", "unabl", "uanble", "unresponsive", "intubated", "ETT",
                                 "sedated", "nonverbal", "non-verbal", "aphasic", "unconscious", "asleep",
                                 "sleeping"])
def test_unable_patterns_from_config(raw):
    v, k = kind_value(raw)
    assert k == "unable"
    assert math.isnan(v)


@pytest.mark.parametrize("raw", ["denies", "crit", "ok", "8 out of 10", "10+", "yes", "mild", "utah", "ultra",
                                 "dull ache", "çãé", "疼痛", "7/9"])
def test_free_text_is_text_other(raw):
    v, k = kind_value(raw)
    assert k == "text_other", raw
    assert math.isnan(v)


@pytest.mark.parametrize("raw", [None, np.nan, float("nan"), pd.NA, "", "   ", "\t\n"])
def test_empty_or_null_is_missing(raw):
    v, k = kind_value(raw)
    assert k == "missing"
    assert math.isnan(v)


def test_unable_pattern_does_not_override_a_number():
    # numbers are matched first, so a pattern can never swallow a valid score
    assert kind_value("8")[1] == "numeric"


def test_parse_pain_series_status_mapping_and_index_alignment():
    raw = pd.Series(["7", "5-6", "7/10", "13", "unable", "denies", None, ""], index=[10, 11, 12, 13, 14, 15, 16, 17])
    out = parse_pain(raw, RULES)
    assert list(out.index) == list(raw.index)
    assert list(out["pain_kind"]) == ["numeric", "range", "fraction", "out_of_range", "unable", "text_other",
                                      "missing", "missing"]
    assert list(out["pain_status"]) == ["numeric", "numeric", "numeric", "out_of_range", "unable", "other",
                                        "missing", "missing"]
    np.testing.assert_array_equal(out["pain_value"].to_numpy()[:3], [7.0, 5.5, 7.0])
    assert out["pain_value"].iloc[3:].isna().all()
    assert set(out["pain_status"]) <= set(CLEANING["pain"]["status_categories"])


def test_parse_pain_empty_series():
    out = parse_pain(pd.Series([], dtype=object), RULES)
    assert len(out) == 0
    assert list(out.columns) == ["pain_value", "pain_kind", "pain_status"]


def test_every_kind_has_a_status_in_the_config():
    assert set(KINDS) <= set(CLEANING["pain"]["status_map"])
    assert set(CLEANING["pain"]["status_map"].values()) <= set(CLEANING["pain"]["status_categories"])


def test_kind_without_status_mapping_is_an_error():
    rules = PainRules(status_map={"numeric": "numeric"})
    with pytest.raises(ValueError, match="without a status mapping"):
        parse_pain(pd.Series(["7", "abc"]), rules)


pain_like = st.one_of(
    st.text(max_size=12),
    st.text(alphabet="0123456789.,-/ to", max_size=10),
    st.integers(-50, 500).map(str),
    st.floats(-100, 1000, allow_nan=False).map(lambda f: f"{f:.2f}"),
    st.tuples(st.integers(0, 30), st.integers(0, 30)).map(lambda t: f"{t[0]}-{t[1]}"),
    st.integers(0, 30).map(lambda x: f"{x}/10"),
    st.none(),
)


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(raw=pain_like)
def test_property_value_always_in_0_10_or_nan(raw):
    v, k = kind_value(raw)
    assert k in KINDS
    if math.isnan(v):
        assert k not in ("numeric", "range", "fraction")
    else:
        assert 0.0 <= v <= 10.0
        assert k in ("numeric", "range", "fraction")


@settings(max_examples=100, deadline=None)
@given(raws=st.lists(pain_like, max_size=30))
def test_property_vectorised_parse_equals_scalar_classify(raws):
    out = parse_pain(pd.Series(raws, dtype=object), RULES)
    for raw, (_, row) in zip(raws, out.iterrows(), strict=True):
        v, k = kind_value(raw)
        assert row["pain_kind"] == k
        assert (math.isnan(v) and math.isnan(row["pain_value"])) or row["pain_value"] == v
        assert 0.0 <= row["pain_value"] <= 10.0 or math.isnan(row["pain_value"])
