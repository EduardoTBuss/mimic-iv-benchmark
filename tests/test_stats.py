"""Tests for triagebench.analysis.stats.  SYNTHETIC data only (never MIMIC)."""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import balanced_accuracy_score, cohen_kappa_score, f1_score

from triagebench.analysis import stats as S

SIMPLE = ["logreg", "gnb", "knn", "dtree"]
COMPLEX = ["rf", "svm_rbf", "xgb", "mlp"]
EXTRA = ["hgb", "extratrees", "ordinal_logit"]
VA, VB = "A_keep_encode", "B_pain_numeric_only"


def make_metrics(complex_boost=0.05, noise=0.003, seeds=range(1, 11), models_skip=(), variants=(VA,), seed=0):
    """Long metrics table.  Seed-level shared shocks mimic overlapping holdouts."""
    rng = np.random.default_rng(seed)
    base = {"logreg": 0.34, "gnb": 0.30, "knn": 0.33, "dtree": 0.32, "rf": 0.34, "svm_rbf": 0.34, "xgb": 0.35,
            "mlp": 0.34, "hgb": 0.35, "extratrees": 0.34, "ordinal_logit": 0.31,
            "dummy_prior": 0.13, "dummy_stratified": 0.20}  # fmt: skip
    group = {**dict.fromkeys(SIMPLE, "simple"), **dict.fromkeys(COMPLEX, "complex")}
    kind = {**dict.fromkeys(SIMPLE + COMPLEX, "primary"), **dict.fromkeys(EXTRA, "extra"),
            "dummy_prior": "reference", "dummy_stratified": "reference"}  # fmt: skip
    rows = []
    for var in variants:
        for s in seeds:
            shock = rng.normal(0, 0.004)
            for m, b in base.items():
                for st in ["none", "class_weight", "oversample"]:
                    if (m == "knn" and st == "class_weight") or (m.startswith("dummy") and st != "none") or (m, st) in models_skip:
                        continue
                    lift = {"none": 0.0, "class_weight": 0.03, "oversample": 0.025}[st] if kind[m] != "reference" else 0
                    lvl = b + (complex_boost if group.get(m) == "complex" else 0.0) + lift + shock
                    test = lvl + rng.normal(0, noise)
                    val = lvl + rng.normal(0, noise)
                    for split, f1 in (("val", val), ("test", test)):
                        vals = {"macro_f1": f1, "balanced_accuracy": f1 + 0.05, "accuracy": 0.55 - lift,
                                "weighted_f1": 0.5, "qwk": 0.4 + f1 / 10, "mae_ordinal": 0.5,
                                "recall_1": 0.1 + lift * 3 + rng.normal(0, 0.01), "recall_2": 0.3, "recall_3": 0.7,
                                "recall_4": 0.3, "recall_5": 0.1, "precision_1": 0.2 - lift, "under_triage_rate": 0.2,
                                "over_triage_rate": 0.25, "severe_under_triage_rate": 0.01,
                                "adjacent_error_share": 0.9, "n": 60000.0}  # fmt: skip
                        for mt, v in vals.items():
                            rows.append((var, s, m, kind[m], group.get(m), st, split, mt, float(v)))
    return pd.DataFrame(rows, columns=["variant", "seed", "model", "model_kind", "model_group", "strategy", "split",
                                       "metric", "value"])  # fmt: skip


def make_predictions(seeds=(1, 2, 3), n_patients=400, rare_class_1=6, seed=0):
    """Stay-level synthetic predictions (patient-clustered) for variants A and B (B nested in A)."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in seeds:
        subj = np.repeat(np.arange(n_patients) + 1000 * s, rng.integers(1, 4, n_patients))
        n = len(subj)
        y = rng.choice([2, 3, 4, 5], p=[0.2, 0.5, 0.25, 0.05], size=n)
        y[:rare_class_1] = 1  # a very rare class 1 (small count must be masked in reports)
        stay = np.arange(n) + 10_000 * s
        keep_b = np.ones(n, bool)
        keep_b[:3] = False  # B removes 3 of the class-1 stays
        keep_b[rng.random(n) < 0.1] = False
        for var, keep in ((VA, np.ones(n, bool)), (VB, keep_b)):
            for m, acc in zip(SIMPLE + COMPLEX, (0.5, 0.4, 0.45, 0.42, 0.6, 0.58, 0.62, 0.59), strict=True):
                for st in ("none",):
                    flip = rng.random(n) > acc
                    pred = np.where(flip, np.clip(y + rng.integers(-1, 2, n), 1, 5), y)
                    rows.append(pd.DataFrame({"variant": var, "seed": s, "model": m, "strategy": st,
                                              "stay_id": stay[keep], "subject_id": subj[keep], "partition": "test",
                                              "y_true": y[keep], "y_pred": pred[keep]}))  # fmt: skip
    return pd.concat(rows, ignore_index=True)


# ------------------------------------------------------------------ (a) metrics vs sklearn
@pytest.mark.parametrize("seed", range(5))
def test_metrics_from_confusion_matches_sklearn(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(300, 1500))
    yt = rng.choice([1, 2, 3, 4, 5], p=[0.05, 0.2, 0.5, 0.2, 0.05], size=n)
    yp = np.where(rng.random(n) < 0.5, yt, rng.integers(1, 6, n))
    m = S.metrics_from_confusion(S.confusion_matrix_from_labels(yt, yp))
    assert m["macro_f1"] == pytest.approx(f1_score(yt, yp, average="macro", labels=[1, 2, 3, 4, 5], zero_division=0))
    assert m["balanced_accuracy"] == pytest.approx(balanced_accuracy_score(yt, yp))
    assert m["qwk"] == pytest.approx(cohen_kappa_score(yt, yp, weights="quadratic"))
    assert m["mae_ordinal"] == pytest.approx(np.abs(yt - yp).mean())
    assert m["accuracy"] == pytest.approx((yt == yp).mean())


def test_metrics_from_confusion_batched_equals_loop():
    rng = np.random.default_rng(0)
    cms = rng.integers(0, 30, size=(7, 5, 5)).astype(float)
    batched = S.metrics_from_confusion(cms)["macro_f1"]
    loop = [S.metrics_from_confusion(c)["macro_f1"] for c in cms]
    assert np.allclose(batched, loop)


# ------------------------------------------------------------------ (b) H1 scenarios
def test_h1_consistent_when_complex_clearly_better():
    r = S.run_preregistered_analysis(make_metrics(complex_boost=0.05), None, n_boot=0)
    assert r["seeds_used"] == list(range(1, 11))
    assert r["h1"]["verdict"] == "consistente"
    assert r["h1"]["all_positive"] and r["h1"]["ci_lower_gt_delta"]
    assert not any(n.startswith("ERRO") for n in r["notes"])
    json.dumps(r)  # serialisable


def test_h1_not_consistent_when_tie():
    r = S.run_preregistered_analysis(make_metrics(complex_boost=0.0, noise=0.004), None, n_boot=0)
    assert r["h1"]["verdict"] == "sem_superioridade_consistente"


def test_h1_small_effect_below_delta_is_not_consistent():
    r = S.run_preregistered_analysis(make_metrics(complex_boost=-0.004, noise=0.001), None, n_boot=0)
    assert r["h1"]["verdict"] == "sem_superioridade_consistente"
    assert not r["h1"]["ci_lower_gt_delta"]


def test_h1_selection_uses_validation_not_test():
    """Making a model terrible on TEST only must not change which model is selected."""
    m = make_metrics(complex_boost=0.05)
    r0 = S.run_preregistered_analysis(m, None, n_boot=0)
    m2 = m.copy()
    mask = (m2.model == "xgb") & (m2.split == "test") & (m2.metric == "macro_f1") & (m2.strategy == "none")
    m2.loc[mask, "value"] = 0.0
    r1 = S.run_preregistered_analysis(m2, None, n_boot=0)
    sel0 = [x["complex_model"] for x in r0["h1"]["per_seed"]]
    sel1 = [x["complex_model"] for x in r1["h1"]["per_seed"]]
    assert sel0 == sel1


# ------------------------------------------------------------------ (c) corrected t
def test_corrected_ttest_wider_than_naive():
    rng = np.random.default_rng(1)
    d = rng.normal(0.02, 0.005, 10)
    c = S.corrected_resampled_ttest(d, 0.70, 0.15)
    nv = c["naive"]
    assert (c["ci_high"] - c["ci_low"]) > (nv["ci_high"] - nv["ci_low"])
    assert c["p"] >= nv["p"]
    # width ratio equals sqrt(1 + k * n_test/n_train)
    ratio = (c["ci_high"] - c["ci_low"]) / (nv["ci_high"] - nv["ci_low"])
    assert ratio == pytest.approx(np.sqrt(1 + 10 * 0.15 / 0.70))


def test_corrected_ttest_degenerate_inputs():
    assert np.isnan(S.corrected_resampled_ttest([0.1], 0.7, 0.15)["p"])
    z = S.corrected_resampled_ttest([0.0, 0.0, 0.0], 0.7, 0.15)
    assert z["p"] == 1.0 and z["ci_low"] == 0.0
    c = S.corrected_resampled_ttest([0.1, 0.1, 0.1], 0.7, 0.15)
    assert c["p"] < 1e-9 and c["ci_low"] == pytest.approx(0.1)


# ------------------------------------------------------------------ (d) cluster bootstrap
def _patient_cms(seed=0):
    p = make_predictions(seeds=(1,), seed=seed)
    out = {}
    d = p[p.variant == VA]
    universe = np.unique(d.subject_id.to_numpy())
    for m, g in d.groupby("model"):
        out[m] = S.patient_confusions(g.subject_id.to_numpy(), g.y_true.to_numpy(), g.y_pred.to_numpy(), universe)
    return out


def test_cluster_bootstrap_reproducible_and_covers_point():
    cms = _patient_cms()
    a = S.cluster_bootstrap_ci(cms, n_boot=400, seed=7, contrasts=[("rf", "logreg")])
    b = S.cluster_bootstrap_ci(cms, n_boot=400, seed=7, contrasts=[("rf", "logreg")])
    c = S.cluster_bootstrap_ci(cms, n_boot=400, seed=8)
    assert a == b
    assert a["ci"] != c["ci"]
    for k, pt in a["point"].items():
        lo, hi = a["ci"][k]
        assert lo <= pt <= hi
    cr = a["contrasts"]["rf-logreg"]
    assert cr["ci"][0] <= cr["point"] <= cr["ci"][1]
    # point estimate equals the metric on the pooled confusion matrix
    pooled = cms["rf"].sum(0)
    assert a["point"]["rf"] == pytest.approx(S.metrics_from_confusion(pooled)["macro_f1"])


def test_patient_confusions_sum_equals_pooled():
    rng = np.random.default_rng(0)
    subj = rng.integers(0, 50, 1000)
    yt, yp = rng.integers(1, 6, 1000), rng.integers(1, 6, 1000)
    pc = S.patient_confusions(subj, yt, yp, np.unique(subj))
    assert np.array_equal(pc.sum(0), S.confusion_matrix_from_labels(yt, yp))


def test_full_pipeline_with_predictions_runs_bootstrap_and_sensitivity():
    metrics = make_metrics(seeds=(1, 2, 3, 4, 5), variants=(VA, VB))
    preds = make_predictions(seeds=(1, 2, 3, 4, 5))
    r = S.run_preregistered_analysis(metrics, preds, n_boot=100, seed=3)
    assert r["bootstrap_ci"]["summary"]["h1_n_seeds"] == 5
    assert r["sensitivity_b_vs_a"]["available"]
    # nested subset: B-common metrics are computed on the intersection only
    assert r["sensitivity_b_vs_a"]["rows"]
    again = S.run_preregistered_analysis(metrics, preds, n_boot=100, seed=3)
    assert again["bootstrap_ci"] == r["bootstrap_ci"]
    assert not any(n.startswith("ERRO") for n in r["notes"])


# ------------------------------------------------------------------ (e) incomplete data
def test_seed_cut_rule_uses_largest_complete_prefix():
    m = make_metrics()
    # seed 8 loses a primary model on test -> prefix is 1..7
    m = m[~((m.seed == 8) & (m.model == "rf") & (m.strategy == "oversample") & (m.split == "test"))]
    r = S.run_preregistered_analysis(m, None, n_boot=0)
    assert r["seeds_used"] == list(range(1, 8))
    assert any(a["type"] == "ausente_ou_falha" and a["model"] == "rf" for a in r["anomalies"])


def test_too_few_seeds_skips_main_analysis_without_error():
    m = make_metrics(seeds=range(1, 4))
    r = S.run_preregistered_analysis(m, None, n_boot=0)
    assert r["seeds_used"] == []
    assert r["h1"] == {}
    assert S.render_stats_markdown(r)


def test_failed_extra_and_missing_knn_class_weight_do_not_break():
    m = make_metrics()
    m = m[~((m.model == "hgb") & (m.seed.isin([2, 3])))]  # failed extra model
    r = S.run_preregistered_analysis(m, None, n_boot=0)
    assert r["seeds_used"] == list(range(1, 11))
    assert any(a["model"] == "hgb" for a in r["anomalies"])
    assert not any(a["model"] == "knn" and a["strategy"] == "class_weight" for a in r["anomalies"])  # N/A, not failure
    assert all(not (x["model"] == "knn" and x["strategy"] == "class_weight") for x in r["h2"]["rows"])
    assert "hgb" not in {x["model"] for x in r["ranking"]["by_strategy"]["none"]["models"]}
    assert any("hgb" in n for n in r["notes"])


def test_missing_predictions_and_variant_b_noted():
    r = S.run_preregistered_analysis(make_metrics(), None, n_boot=50)
    assert r["bootstrap_ci"] == {}
    assert any("predictions" in n for n in r["notes"])
    assert S.render_stats_markdown(r)


def test_missing_columns_raises():
    with pytest.raises(ValueError):
        S.run_preregistered_analysis(pd.DataFrame({"variant": ["A"]}), None)


def test_anomaly_flags_recall_zero_and_below_dummy():
    m = make_metrics()
    mask = (m.model == "gnb") & (m.strategy == "none") & (m.metric == "recall_1") & (m.split == "test")
    m.loc[mask, "value"] = 0.0
    mask2 = (m.model == "dtree") & (m.strategy == "none") & (m.metric == "macro_f1") & (m.split == "test")
    m.loc[mask2, "value"] = 0.05
    r = S.run_preregistered_analysis(m, None, n_boot=0)
    types = {(a["type"], a["model"]) for a in r["anomalies"]}
    assert ("classe_com_recall_zero", "gnb") in types
    assert ("abaixo_do_dummy", "dtree") in types


def test_h2_detects_strategy_gain_with_holm():
    r = S.run_preregistered_analysis(make_metrics(), None, n_boot=0)
    rows = [x for x in r["h2"]["rows"] if x["confirmatory"] and x["metric"] == "macro_f1"]
    assert rows and all(x["mean_diff"] > 0 and x["p_holm"] >= x["p"] - 1e-12 for x in rows)
    assert any(s["supported"] for s in r["h2"]["summary"])


def test_ranking_reports_friedman_and_kendall():
    r = S.run_preregistered_analysis(make_metrics(), None, n_boot=0)
    rk = r["ranking"]["by_strategy"]["none"]
    assert 0 <= rk["kendall_w"] <= 1 and rk["nemenyi_cd"] > 0
    assert "Poder baixo" in r["ranking"]["warning"]


# ------------------------------------------------------------------ (f) rendering / disclosure
def test_mask_count():
    assert S.mask_count(0) == "0"
    assert S.mask_count(1) == "<11" and S.mask_count(10) == "<11"
    assert S.mask_count(11) == "11" and S.mask_count(60000) == "60000"


def test_render_markdown_masks_small_counts():
    metrics = make_metrics(seeds=(1, 2, 3, 4, 5), variants=(VA, VB))
    preds = make_predictions(seeds=(1, 2, 3, 4, 5), rare_class_1=6)
    r = S.run_preregistered_analysis(metrics, preds, n_boot=50)
    removal = r["sensitivity_b_vs_a"]["removal_by_class"]
    assert removal["1"]["n_test_a_mean_per_seed"] == "<11"  # raw 6 never stored
    assert removal["1"]["n_removed_mean_per_seed"] == "<11"  # raw 3 never stored
    md = S.render_stats_markdown(r)
    assert "<11" in md
    row = next(line for line in md.splitlines() if re.match(r"\| 1 \|", line) and "<11" in line)
    assert row.count("<11") == 2
    assert "H1" in md and "Nadeau" in md
    # no bare small integers in count cells of the removal table
    for line in md.splitlines():
        if re.match(r"\| [1-5] \|", line):
            cells = [c.strip() for c in line.strip("|").split("|")]
            for c in cells[1:3]:
                assert not re.fullmatch(r"[1-9]|10", c)
    json.dumps(r)
