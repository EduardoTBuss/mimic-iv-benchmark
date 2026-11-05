"""Metrics against sklearn / closed-form ordinal definitions, and small-cell disclosure control."""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sklearn.metrics import accuracy_score, balanced_accuracy_score, cohen_kappa_score, f1_score

from tests._helpers import make_cfg
from triagebench.data.audit import build_audit, render_audit_markdown
from triagebench.data.load import consistency_report, load_edstays, load_triage, table_path
from triagebench.evaluation.metrics import LABELS, compute_metrics, scalar_metrics
from triagebench.reporting.disclosure import (
    MASK,
    is_small,
    mask_count,
    mask_count_columns,
    mask_matrix,
    mask_pct,
)
from triagebench.runner.data_stages import stage_ingest
from triagebench.utils.io import atomic_write_json
from triagebench.utils.synthetic import write_synthetic_zip

# sklearn warns on the degenerate partitions exercised on purpose below
pytestmark = pytest.mark.filterwarnings("ignore::UserWarning:sklearn.*")

labels = st.integers(1, 5)
pairs = st.integers(1, 300).flatmap(lambda n: st.tuples(st.lists(labels, min_size=n, max_size=n),
                                                       st.lists(labels, min_size=n, max_size=n)))


def _random_pair(seed: int, n: int = 2000):
    rng = np.random.default_rng(seed)
    y = rng.choice(LABELS, size=n, p=[0.06, 0.33, 0.53, 0.07, 0.01])
    noise = rng.choice([-2, -1, 0, 0, 0, 1, 2], size=n)
    return y, np.clip(y + noise, 1, 5)


# --------------------------------------------------------------------------- 8. metrics

@pytest.mark.parametrize("seed", range(5))
def test_matches_sklearn(seed):
    y, p = _random_pair(seed)
    m = compute_metrics(y, p)
    assert m["accuracy"] == pytest.approx(accuracy_score(y, p), abs=1e-15)
    assert m["balanced_accuracy"] == pytest.approx(balanced_accuracy_score(y, p), abs=1e-15)
    assert m["macro_f1"] == pytest.approx(f1_score(y, p, labels=list(LABELS), average="macro"), abs=1e-15)
    assert m["weighted_f1"] == pytest.approx(f1_score(y, p, labels=list(LABELS), average="weighted"), abs=1e-15)
    assert m["qwk"] == pytest.approx(cohen_kappa_score(y, p, weights="quadratic"), abs=1e-12)


def _qwk_reference(y, p, k=5):
    """Textbook quadratic-weighted kappa (independent of sklearn)."""
    observed = np.zeros((k, k))
    for a, b in zip(y, p, strict=True):
        observed[a - 1, b - 1] += 1
    weights = np.array([[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)])
    expected = np.outer(observed.sum(1), observed.sum(0)) / observed.sum()
    return 1 - (weights * observed).sum() / (weights * expected).sum()


@pytest.mark.parametrize("seed", range(5))
def test_ordinal_definitions_closed_form(seed):
    y, p = _random_pair(seed)
    m = compute_metrics(y, p)
    d = p - y
    assert m["mae_ordinal"] == pytest.approx(np.mean(np.abs(d)))
    assert m["under_triage_rate"] == pytest.approx(np.mean(p > y))
    assert m["over_triage_rate"] == pytest.approx(np.mean(p < y))
    assert m["severe_under_triage_rate"] == pytest.approx(np.mean(d >= 2))
    assert m["under_triage_rate_urgent"] == pytest.approx(np.mean(p[y <= 2] > y[y <= 2]))
    assert m["adjacent_error_share"] == pytest.approx(np.sum(np.abs(d) == 1) / np.sum(d != 0))
    assert m["qwk"] == pytest.approx(_qwk_reference(y, p), abs=1e-12)
    conf = np.array(m["confusion"])
    assert conf.sum() == len(y) and np.trace(conf) == np.sum(d == 0)
    assert sum(m["abs_error_counts"].values()) == len(y)
    for lab in LABELS:
        assert m[f"support_{lab}"] == np.sum(y == lab) == conf[lab - 1].sum()
        assert m[f"predicted_{lab}"] == np.sum(p == lab) == conf[:, lab - 1].sum()


def test_hand_computed_example():
    y = np.array([1, 2, 3, 3, 4, 5])
    p = np.array([3, 2, 2, 3, 5, 5])   # d = [2, 0, -1, 0, 1, 0]
    m = compute_metrics(y, p)
    assert m["accuracy"] == pytest.approx(3 / 6)
    assert m["mae_ordinal"] == pytest.approx(4 / 6)
    assert m["under_triage_rate"] == pytest.approx(2 / 6)
    assert m["over_triage_rate"] == pytest.approx(1 / 6)
    assert m["severe_under_triage_rate"] == pytest.approx(1 / 6)
    assert m["under_triage_rate_urgent"] == pytest.approx(1 / 2)    # y<=2: {1->3, 2->2}
    assert m["adjacent_error_share"] == pytest.approx(2 / 3)
    assert m["abs_error_counts"] == {"0": 3, "1": 2, "2": 1, "3": 0, "4": 0}


def test_all_correct_with_every_class():
    y = np.array([1, 2, 3, 4, 5] * 4)
    m = compute_metrics(y, y)
    for key in ("accuracy", "balanced_accuracy", "macro_f1", "weighted_f1", "qwk"):
        assert m[key] == pytest.approx(1.0)
    for key in ("mae_ordinal", "under_triage_rate", "over_triage_rate", "severe_under_triage_rate",
                "under_triage_rate_urgent"):
        assert m[key] == 0.0
    assert math.isnan(m["adjacent_error_share"])        # no errors: share undefined


def test_absent_class_counts_as_zero_f1_in_macro_average():
    """Documents the current convention: macro-F1 averages over the 5 fixed labels, so a perfect
    prediction of a partition WITHOUT acuity 5 scores 0.8 (balanced accuracy, by contrast, uses only
    the classes present). Changing this convention must be a deliberate decision."""
    y = np.array([1, 2, 3, 4] * 5)
    m = compute_metrics(y, y)
    assert m["macro_f1"] == pytest.approx(0.8)
    assert m["balanced_accuracy"] == pytest.approx(1.0)
    assert m["support_5"] == 0 and m["predicted_5"] == 0 and m["f1_5"] == 0.0


def test_predicting_a_class_absent_from_truth():
    y = np.array([3, 3, 3, 2, 2])
    p = np.array([5, 3, 3, 2, 1])
    m = compute_metrics(y, p)
    assert m["precision_5"] == 0.0 and m["recall_5"] == 0.0 and m["support_5"] == 0
    assert m["predicted_5"] == 1 and m["predicted_1"] == 1
    assert m["under_triage_rate_urgent"] == 0.0   # y<=2: 2->2, 2->1 (over-triage)


def test_single_class_partition_gives_nan_qwk_not_a_crash():
    m = compute_metrics([3, 3, 3], [3, 3, 3])
    assert m["accuracy"] == 1.0
    assert math.isnan(m["qwk"])
    assert math.isnan(m["under_triage_rate_urgent"])    # no y <= 2


def test_no_urgent_cases_gives_nan_urgent_rate():
    m = compute_metrics([3, 4, 5], [4, 4, 5])
    assert math.isnan(m["under_triage_rate_urgent"])
    assert m["under_triage_rate"] == pytest.approx(1 / 3)


def test_empty_input_returns_nan_metrics():
    m = compute_metrics([], [])
    assert m["n"] == 0 and math.isnan(m["mae_ordinal"])


def test_metrics_with_documented_nan_can_be_persisted(tmp_path):
    m = compute_metrics([3, 4, 5], [3, 4, 5])      # adjacent_error_share and urgent rate are NaN
    atomic_write_json(tmp_path / "result.json", {"test": m})


def test_scalar_metrics_drops_only_containers():
    m = compute_metrics([1, 2, 3], [1, 2, 2])
    s = scalar_metrics(m)
    assert "confusion" not in s and "abs_error_counts" not in s
    assert set(m) - set(s) == {"confusion", "abs_error_counts"}


@settings(max_examples=200, deadline=None)
@given(pair=pairs)
def test_property_rates_in_unit_interval_and_mae_zero_iff_perfect(pair):
    y, p = (np.array(v) for v in pair)
    m = compute_metrics(y, p)
    for key in ("accuracy", "balanced_accuracy", "macro_f1", "weighted_f1", "under_triage_rate", "over_triage_rate",
                "severe_under_triage_rate", "under_triage_rate_urgent", "adjacent_error_share"):
        v = m[key]
        assert math.isnan(v) or 0.0 <= v <= 1.0, key
    assert 0.0 <= m["mae_ordinal"] <= 4.0
    assert (m["mae_ordinal"] == 0.0) == (m["accuracy"] == 1.0)
    assert m["under_triage_rate"] + m["over_triage_rate"] + m["accuracy"] == pytest.approx(1.0)
    assert m["severe_under_triage_rate"] <= m["under_triage_rate"]
    assert math.isnan(m["qwk"]) or -1.0 - 1e-12 <= m["qwk"] <= 1.0 + 1e-12


@settings(max_examples=100, deadline=None)
@given(pair=pairs)
def test_property_label_order_reversal_swaps_under_and_over_triage(pair):
    y, p = (np.array(v) for v in pair)
    m = compute_metrics(y, p)
    r = compute_metrics(6 - y, 6 - p)
    assert r["under_triage_rate"] == pytest.approx(m["over_triage_rate"])
    assert r["mae_ordinal"] == pytest.approx(m["mae_ordinal"])
    assert r["macro_f1"] == pytest.approx(m["macro_f1"])


# --------------------------------------------------------------------------- 9. disclosure

@pytest.mark.parametrize("n", range(1, 11))
def test_mask_count_masks_1_to_10(n):
    assert mask_count(n) == "<11"
    assert mask_count(np.int64(n)) == "<11"
    assert is_small(n)


@pytest.mark.parametrize(("n", "shown"), [(0, "0"), (11, "11"), (12, "12"), (1000, "1,000"), (10**6, "1,000,000")])
def test_mask_count_shows_zero_and_11_plus(n, shown):
    assert mask_count(n) == shown


def test_mask_count_custom_k():
    assert mask_count(4, k=5) == "<5"
    assert mask_count(5, k=5) == "5"


def test_mask_pct():
    assert mask_pct(5, 1000) == MASK            # small numerator: masked
    assert mask_pct(10, 1000) == MASK
    assert mask_pct(11, 1000) == "1.10%"
    assert mask_pct(0, 1000) == "0.00%"
    assert mask_pct(500, 0) == MASK             # undefined denominator
    assert mask_pct(np.int64(3), np.int64(50)) == MASK


def test_mask_matrix_and_columns():
    arr = mask_matrix(np.array([[0, 1, 10], [11, 5, 200]]))
    assert arr[0, 0] == 0 and arr[1, 0] == 11 and arr[1, 2] == 200
    assert np.isnan(arr[0, 1]) and np.isnan(arr[0, 2]) and np.isnan(arr[1, 1])
    df = mask_count_columns(pd.DataFrame({"n": [0, 3, 11, np.nan]}), ["n"])
    assert list(df["n"]) == ["0", "<11", "11", MASK]


@settings(max_examples=300, deadline=None)
@given(n=st.integers(0, 10**7), d=st.integers(0, 10**7))
def test_property_never_prints_a_small_count(n, d):
    out = mask_count(n)
    if 1 <= n <= 10:
        assert out == "<11"
    else:
        assert int(out.replace(",", "")) == n
    pct = mask_pct(n, d)
    if 1 <= n <= 10 or d == 0:
        assert pct == MASK


@pytest.fixture(scope="module")
def audit_env(tmp_path_factory):
    """A SMALL synthetic cohort so that many cells are 1..10 and masking is really exercised."""
    root = tmp_path_factory.mktemp("audit")
    zip_path = write_synthetic_zip(root / "zip", n_stays=600, seed=11)
    cfg = make_cfg(root, zip_path)
    ingest = stage_ingest(cfg)
    triage, load_report = load_triage(table_path(cfg, "triage"))
    edstays = load_edstays(table_path(cfg, "edstays"))
    audit = build_audit(triage, load_report, consistency_report(triage, edstays), ingest, cfg)
    return {"audit": audit, "md": render_audit_markdown(audit), "triage": triage}


def test_audit_markdown_contains_no_identifier(audit_env):
    md = audit_env["md"]
    ids = set(audit_env["triage"]["stay_id"]) | set(audit_env["triage"]["subject_id"])
    numbers = set(re.findall(r"\d[\d,]*", md))
    leaked = [i for i in ids if str(i) in numbers or f"{i:,}" in numbers]
    assert not leaked, f"identifiers printed in the audit: {leaked[:5]}"


_INT_CELL = re.compile(r"^\d{1,3}(,\d{3})*$")


def _table_cells(md: str):
    """Yield (table_header, row, cell) for every body cell after the first (label) column."""
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith("| ") and i + 1 < len(lines) and lines[i + 1].startswith("|---"):
            header = lines[i]
            j = i + 2
            while j < len(lines) and lines[j].startswith("| "):
                cells = [c.strip() for c in lines[j].strip().strip("|").split(" | ")]
                for c in cells[1:]:
                    yield header, lines[j], c
                j += 1
            i = j
        else:
            i += 1


def test_audit_tables_have_no_unmasked_small_count(audit_env):
    cells = list(_table_cells(audit_env["md"]))
    assert cells, "no markdown tables found"
    masked = sum(c == "<11" for _, _, c in cells)
    assert masked > 0, "fixture should produce small cells; otherwise this test proves nothing"
    bad = [(h, r) for h, r, c in cells if _INT_CELL.match(c) and 1 <= int(c.replace(",", "")) <= 10]
    assert not bad, f"unmasked counts 1..10: {bad[:3]}"


# an integer 1..10 (not part of a decimal, a percentage or a larger number) that ends a sentence
# or is followed by "estadias"/"strings"
PROSE_SMALL_COUNT = r"(?<![\w.,<-])([1-9]|10)(?!\d|[.,]\d|%)\s*(?:estadias|strings|\.|$)"


@pytest.mark.parametrize(("text", "found"), [
    ("Estadias sem nenhum dos 6 sinais vitais nem dor: 7.", ["7"]),
    ("as raras somam 3 estadias em <11 strings.", ["3"]),
    ("somam <11 estadias em 4 strings.", ["4"]),
    ("dor: 10.", ["10"]),
    ("Numéricos não inteiros (ex.: 7.5): <11.", []),
    ("Contagens de 1 a 10 aparecem como `<11`;", []),
    ("removal ratio <= 1.5 and Cramer's V < 0.05.", []),
    ("dor: 0.", []),
    ("dor: 11.", []),
])
def test_prose_detector_itself(text, found):
    """The leak detector must catch planted leaks (a vacuous regex would prove nothing)."""
    assert re.findall(PROSE_SMALL_COUNT, text, flags=re.M) == found


def test_table_detector_itself():
    md = "| a | b |\n|---|---|\n| x | 7 |\n| 3 | <11 |\n| y | 1,234 |\n"
    bad = [c for _, _, c in _table_cells(md) if _INT_CELL.match(c) and 1 <= int(c.replace(",", "")) <= 10]
    assert bad == ["7"]          # the label column ("3") is not a count


def test_audit_prose_counts_are_masked(audit_env):
    # sentences outside tables (and headings) that carry counts ("...: 7." / "somam 3 estadias")
    prose = "\n".join(line for line in audit_env["md"].splitlines() if not line.startswith(("|", "#")))
    small = re.findall(PROSE_SMALL_COUNT, prose, flags=re.M)
    assert not small, f"unmasked small counts in prose: {small}"


def test_audit_never_prints_raw_rare_pain_strings(audit_env):
    a = audit_env["audit"]
    k = a["disclosure_min_cell"]
    shown = {d["string"] for d in a["pain"]["frequent_non_numeric_strings"]}
    assert all(d["n"] >= k for d in a["pain"]["frequent_non_numeric_strings"])
    vc = audit_env["triage"]["pain_raw"].dropna().str.strip().str.lower().value_counts()
    rare = {s for s, c in vc.items() if c < k and not re.fullmatch(r"[\d.,/\- to]+", s)}
    assert not (rare & shown)
