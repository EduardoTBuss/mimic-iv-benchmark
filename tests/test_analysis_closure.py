"""Analysis/reporting closure checks using generated, nonclinical data only."""

from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd
import pytest

from triagebench.analysis import stats as S
from triagebench.analysis.secondary import h1_validation_selected_strategy
from triagebench.evaluation.metrics import compute_metrics, scalar_metrics
from triagebench.reporting import summary

VA, VB, VC = "A_keep_encode", "B_pain_numeric_only", "C_values_only"
AS_OF = "2026-11-06T15:00:00+00:00"
FINISHED = "2026-11-05T15:00:00+00:00"
SETTINGS = {"simple_models": ["logreg"], "complex_models": ["rf"], "extra_models": [],
            "reference_models": [], "strategies": ["none"], "expected_seeds": 6, "min_seeds": 2}


def synthetic_tables():
    rows, predictions = [], []
    for seed in range(1, 7):
        for variant in (VA, VB, VC):
            y = np.tile(np.arange(1, 6), 4)
            if variant == VB:
                y = y[:-2]
            for model in ("logreg", "rf"):
                pred = y.copy()
                n_errors = (4 if model == "logreg" else 2) + (seed % 2) + (variant == VC)
                pred[:n_errors] = np.minimum(y[:n_errors] + 1, 5)
                task = {"variant": variant, "seed": seed, "model": model, "strategy": "none"}
                metrics = scalar_metrics(compute_metrics(y, pred))
                for split in ("val", "test"):
                    rows.extend({**task, "split": split, "metric": key, "value": value,
                                 "finished_at": FINISHED} for key, value in metrics.items())
                predictions.append(pd.DataFrame({**task, "stay_id": seed * 100 + np.arange(len(y)),
                                                 "subject_id": seed * 100 + np.arange(len(y)) // 2,
                                                 "partition": "test", "y_true": y, "y_pred": pred}))
    return pd.DataFrame(rows), pd.concat(predictions, ignore_index=True)


def run(metrics, predictions=None, **kwargs):
    return S.run_preregistered_analysis(metrics, predictions, SETTINGS, analysis_time=AS_OF, n_boot=20, **kwargs)


def test_paired_ablation_reports_missing_pairs_and_registered_corrected_ci():
    metrics, _ = synthetic_tables()
    missing = (metrics.variant == VC) & (metrics.model == "rf") & (metrics.seed == 2)
    metrics = metrics.loc[~missing]
    result = run(metrics)
    ablation = result["ablation_a_minus_c"]
    row = next(r for r in ablation["rows"] if r["model"] == "rf")
    expected = S.corrected_resampled_ttest([p["diff_a_minus_c"] for p in row["per_seed"]], .70, .15)
    assert row["n_pairs"] == 5
    assert row["paired_seeds"] == [1, 3, 4, 5, 6]
    assert row["missing_pairs"] == [{"seed": 2, "missing_variants": [VC]}]
    assert row["mean_diff_a_minus_c"] == pytest.approx(expected["mean"])
    assert row["ci_low"] == pytest.approx(expected["ci_low"])
    assert row["ci_high"] == pytest.approx(expected["ci_high"])
    assert ablation["role"] == "descriptive" and ablation["multiplicity_correction"] is None
    text = S.render_stats_markdown(result)
    assert "A minus C" in text and "Missing pairs" in text
    urgent = next(r for r in result["h3"]["rows"] if r["model"] == "rf")
    assert urgent["under_triage_rate_urgent_n_seeds"] == 6
    assert urgent["under_triage_rate_urgent_sd"] is not None
    assert "Urgent undertriage" in text and "Available seeds" in text


def test_preview_asof_excludes_known_future_tasks_and_preserves_prefix():
    metrics, predictions = synthetic_tables()
    late = (metrics.variant == VA) & (metrics.model == "rf") & (metrics.seed == 3)
    metrics.loc[late, "finished_at"] = "2026-11-07T00:00:00Z"
    result = run(metrics, predictions)
    assert result["seeds_used"] == [1, 2]
    assert result["meta"]["analysis_status"] == "technical_preview"
    assert not result["meta"]["principal_analysis"]
    assert result["meta"]["tasks_excluded_after_boundary"] == 1
    assert result["prediction_integrity"]["valid"]
    assert result["bootstrap_ci"]["summary"]["h1_n_seeds"] == 2


def test_after_cutoff_fails_closed_even_with_producer_timestamps():
    metrics, predictions = synthetic_tables()
    late = (metrics.variant == VA) & (metrics.model == "rf") & (metrics.seed == 3)
    metrics.loc[late, "finished_at"] = "2026-11-10T15:00:01Z"
    kwargs = {"analysis_time": "2026-11-11T10:00:00-03:00", "n_boot": 20}
    result = S.run_preregistered_analysis(metrics, predictions, SETTINGS, **kwargs)
    again = S.run_preregistered_analysis(metrics, predictions, SETTINGS, **kwargs)
    assert result == again
    assert result["meta"]["schema_version"] == 2
    assert result["meta"]["analysis_status"] == "pending_cutoff_provenance"
    assert result["meta"]["principal_cutoff_utc"] == S.PRINCIPAL_CUTOFF
    assert result["meta"]["tasks_excluded_after_boundary"] == 1
    assert result["seed_selection"]["candidate_preview_prefix"] == [1, 2]
    assert result["seeds_used"] == [] and result["h1"] == {} and result["h2"] == {}
    assert result["bootstrap_ci"] == {} and not result["meta"]["principal_analysis"]
    assert not result["meta"]["cutoff_provenance_verified"]
    assert "blocked" in S.render_stats_markdown(result)
    json.dumps(result, allow_nan=False)


def test_missing_provenance_is_explicit_and_naive_asof_is_rejected():
    metrics, _ = synthetic_tables()
    result = run(metrics.drop(columns="finished_at"))
    assert result["meta"]["tasks_missing_completion_time"] == 36
    assert result["meta"]["analysis_status"] == "technical_preview"
    with pytest.raises(ValueError, match="timezone-aware"):
        S.run_preregistered_analysis(metrics, None, SETTINGS, analysis_time="2026-11-06T12:00:00")


def test_empty_analysis_still_records_status_and_never_designates_principal():
    empty = pd.DataFrame(columns=S.REQUIRED_METRIC_COLS + ["finished_at"])
    result = run(empty)
    assert result["meta"]["analysis_status"] == "technical_preview"
    assert result["seeds_used"] == [] and result["h1"] == {}
    result = S.run_preregistered_analysis(empty, None, SETTINGS, analysis_time="2026-11-10T15:00:00Z")
    assert result["meta"]["analysis_status"] == "pending_cutoff_provenance"
    assert not result["meta"]["principal_analysis"]


def test_prediction_integrity_accepts_coherent_tasks_and_paired_universes():
    metrics, predictions = synthetic_tables()
    result = run(metrics, predictions)
    assert result["prediction_integrity"]["valid"]
    assert result["prediction_integrity"]["anomalies"] == []
    assert result["sensitivity_b_vs_a"]["available"]
    assert result["bootstrap_ci"]["summary"]["h1_n_seeds"] == 6
    assert not any(note.startswith("ERRO") for note in result["notes"])


@pytest.mark.parametrize("mutation,kind", [
    ("duplicate", "prediction_duplicate_or_missing_identifiers"),
    ("truncate", "metrics_predictions_mismatch"),
    ("metric", "metrics_predictions_mismatch"),
    ("label", "prediction_incompatible_test_universe"),
    ("universe", "prediction_incompatible_variant_universe"),
    ("missing", "predictions_missing_task"),
])
def test_unsafe_prediction_sections_are_omitted_with_cell_anomalies(mutation, kind):
    metrics, predictions = synthetic_tables()
    cell = (predictions.variant == VA) & (predictions.seed == 1) & (predictions.model == "rf")
    if mutation == "duplicate":
        predictions = pd.concat([predictions, predictions.loc[cell].iloc[:1]], ignore_index=True)
    elif mutation == "truncate":
        predictions = predictions.drop(predictions.loc[cell].index[-1])
    elif mutation == "metric":
        metrics.loc[(metrics.variant == VA) & (metrics.seed == 1) & (metrics.model == "rf") &
                    (metrics.split == "test") & (metrics.metric == "macro_f1"), "value"] = .123
    elif mutation == "label":
        predictions.loc[predictions.loc[cell].index[0], "y_true"] = 5
    elif mutation == "universe":
        # Change C stays consistently across models, preserving all metric scores.
        predictions.loc[(predictions.variant == VC) & (predictions.seed == 1), "stay_id"] += 10000
    else:
        predictions = predictions.loc[~cell]
    result = run(metrics, predictions)
    assert not result["prediction_integrity"]["valid"]
    assert any(a["type"] == kind for a in result["anomalies"])
    assert result["bootstrap_ci"] == {}
    assert not result["sensitivity_b_vs_a"]["available"]
    assert result["h1"]  # Metric-only preview is retained, with the anomaly disclosed.
    serialized = json.dumps(result)
    assert '"stay_id"' not in serialized and '"subject_id"' not in serialized


def project_config(tmp_path):
    return {"models": {"primary": ["logreg", "rf"], "groups": {"simple": ["logreg"], "complex": ["rf"]}},
            "variants": {VA: {"role": "primary"}, VB: {"role": "sensitivity"}, VC: {"role": "sensitivity", "strategies": ["none"]}},
            "imbalance": {"strategies": ["none"]},
            "split": {"seeds": list(range(1, 7)), "fractions": {"train": .70, "test": .15, "val": .15}},
            "paths": {"reports": str(tmp_path / "synthetic-report")},
            "evaluation": {"disclosure_min_cell": 11}, "campaign": {"tag": "synthetic"}}


def test_aggregates_only_never_loads_private_inputs_and_preserves_full_report(tmp_path, monkeypatch):
    from triagebench.cli import build_parser
    from triagebench.runner import pipeline

    assert build_parser().parse_args(["analyze", "--aggregates-only"]).aggregates_only
    assert not build_parser().parse_args(["analyze"]).aggregates_only
    metrics, _ = synthetic_tables()
    cfg = project_config(tmp_path)
    cfg["paths"]["outputs"] = str(tmp_path / "synthetic-output")
    cdir = tmp_path / "synthetic-campaign"
    (cdir / "tables").mkdir(parents=True)
    metadata = {"campaign_id": "synthetic", "prepared_id": "synthetic", "dataset": {
        "name": "synthetic", "version": "0", "zip_sha256": "0" * 64}}
    (cdir / "campaign.json").write_text(json.dumps(metadata), encoding="utf-8")
    (cdir / "manifest.json").write_text('{"sessions": []}', encoding="utf-8")
    full_stats = cdir / "tables" / "stats.json"
    full_stats.write_text("existing full analysis", encoding="utf-8")
    full_report = tmp_path / "synthetic-report" / "campaigns" / "synthetic" / "summary.md"
    full_report.parent.mkdir(parents=True)
    full_report.write_text("existing full report", encoding="utf-8")

    timings = metrics[S.TASK_COLS + ["finished_at"]].drop_duplicates().assign(
        final_fit_seconds=1., predict_test_seconds=.1, n_test=20, task_seconds=1.,
        n_warnings_final=0, hpo_n_error=0)
    tables = {"metrics": metrics, "timings": timings,
              "confusion": pd.DataFrame(columns=S.TASK_COLS + ["split", "true", "pred", "count"]),
              **{key: pd.DataFrame() for key in
                 ("per_class", "abs_error", "hpo_trials", "failures", "not_applicable")}}
    monkeypatch.setattr(pipeline, "aggregate_campaign", lambda path: tables)

    def forbidden(*args, **kwargs):
        pytest.fail("aggregates-only mode attempted a private-input operation")

    monkeypatch.setattr(pipeline, "load_predictions", forbidden)
    monkeypatch.setattr(summary, "_strata_section", forbidden)
    monkeypatch.setattr(summary, "_decodings_section", forbidden)
    monkeypatch.setattr(summary.shutil, "copyfile", forbidden)
    for name in ("fig_metric_box", "fig_strategy_effect", "fig_error_distance", "fig_confusion"):
        monkeypatch.setattr(summary.figures, name, lambda *args, **kwargs: None)

    report = pipeline.analyze_and_report(cfg, cdir, analysis_time=AS_OF, aggregates_only=True)
    result = json.loads((cdir / "tables" / "stats_aggregates_only.json").read_text(encoding="utf-8"))
    expected = S.run_preregistered_analysis(metrics, None, pipeline.stats_config(cfg), analysis_time=AS_OF)
    for key in ("seeds_used", "h1", "h2", "h3", "ablation_a_minus_c"):
        assert result[key] == expected[key]
    assert result["meta"]["input_scope"] == "aggregates_only"
    assert not result["meta"]["predictions_available"]
    assert not result["prediction_integrity"]["checked"]
    assert result["bootstrap_ci"] == {} and not result["sensitivity_b_vs_a"]["available"]
    assert report == tmp_path / "synthetic-report" / "aggregates-only" / "campaigns" / "synthetic" / "summary.md"
    text = report.read_text(encoding="utf-8")
    assert "Input scope: aggregates only" in text and "This report does not replace" in text
    assert full_stats.read_text(encoding="utf-8") == "existing full analysis"
    assert full_report.read_text(encoding="utf-8") == "existing full report"
    assert cfg["paths"]["reports"] == str(tmp_path / "synthetic-report")


def test_secondary_h1_uses_prefix_and_requires_all_candidates(tmp_path):
    metrics, _ = synthetic_tables()
    cfg = project_config(tmp_path)
    complete = h1_validation_selected_strategy(metrics, cfg, VA, seeds=[1, 2])
    assert [r["seed"] for r in complete["per_seed"]] == [1, 2]
    missing = (metrics.variant == VA) & (metrics.seed == 2) & (metrics.model == "rf")
    metrics = metrics.loc[~missing]
    result = h1_validation_selected_strategy(metrics, cfg, VA)
    assert result["per_seed"] == []  # A later complete seed cannot bypass a prefix gap.
    forced = h1_validation_selected_strategy(metrics, cfg, VA, seeds=[1, 2])
    assert [r["seed"] for r in forced["per_seed"]] == [1]
    assert forced["missing_cells"][0]["seed"] == 2


def test_report_and_figures_use_exact_selected_inventory(tmp_path, monkeypatch):
    metrics, _ = synthetic_tables()
    result = run(metrics)
    result["seeds_used"] = [1, 2]
    timings = metrics[S.TASK_COLS + ["finished_at"]].drop_duplicates().assign(
        final_fit_seconds=1., predict_test_seconds=.1, n_test=20, task_seconds=1.,
        n_warnings_final=0, hpo_n_error=0)
    # Keep unneeded aggregate tables empty; all artifacts are generated under pytest's disposable directory.
    tables = {"metrics": metrics, "timings": timings, **{key: pd.DataFrame() for key in
              ("per_class", "confusion", "abs_error", "hpo_trials", "failures", "not_applicable")}}
    chosen = summary._selected_tables(tables, result)
    assert set(chosen["metrics"].seed) == {1, 2}
    cfg = project_config(tmp_path)
    meta = {"campaign_id": "synthetic", "prepared_id": "synthetic", "dataset": {
        "name": "synthetic", "version": "0", "zip_sha256": "0" * 64}}
    monkeypatch.setattr(summary, "read_json", lambda path: meta if path.name == "campaign.json" else {})
    captures = []

    def capture(frame, *args):
        captures.append(frame.copy())
        return None

    for name in ("fig_metric_box", "fig_strategy_effect", "fig_error_distance"):
        monkeypatch.setattr(summary.figures, name, capture)
    # Avoid the optional confusion figure by removing validation rows only for this presentation check.
    tables["metrics"] = metrics.loc[metrics.split == "test"]
    report = summary.write_reports(cfg, tmp_path / "synthetic-campaign", tables, result, None)
    text = report.read_text(encoding="utf-8")
    assert "technical_preview" in text and "Selected seeds: 1, 2" in text
    assert "under_triage_rate_urgent" in text and "urgent metric available seeds" in text
    assert "omitted:" in text.lower()
    assert all(set(frame.seed) == {1, 2} for frame in captures if not frame.empty)
    assert "5000.000" in summary._main_table(chosen["metrics"], chosen["timings"], VA, ["rf"], ["none"])
    # Missing/unverified analysis never falls back to every currently available seed.
    assert summary._selected_tables(tables, None)["metrics"].empty


def test_task_completion_timestamp_survives_aggregation(tmp_path, monkeypatch):
    from triagebench.analysis import aggregate

    m = compute_metrics(np.tile(np.arange(1, 6), 3), np.tile(np.arange(1, 6), 3))
    task = {"variant": VA, "seed": 1, "model": "rf", "strategy": "none", "model_kind": "primary", "model_group": "complex"}
    record = {"task": task, "val": m, "test": m, "finished_at": FINISHED,
              "timing": {"final_fit_seconds": 1, "predict_test_seconds": 1, "task_seconds": 2},
              "hpo": {"trial_seconds_total": 1, "n_ok": 1, "n_error": 0},
              "data": {"n_train": 20, "n_test": 15}, "env": {"threads": 1},
              "best_trial_index": 0, "frozen_config": {"params": {}}}
    monkeypatch.setattr(aggregate, "_task_results", lambda _: [copy.deepcopy(record)])
    tables = aggregate.aggregate_campaign(tmp_path / "synthetic-aggregate")
    for key in ("metrics", "per_class", "confusion", "abs_error", "timings"):
        assert set(tables[key].finished_at) == {FINISHED}


def test_coherent_preview_restores_scoped_secondary_sections_and_independent_cost(tmp_path):
    from triagebench.data.schema import VITALS

    metrics, predictions = synthetic_tables()
    result = run(metrics, predictions)
    result["seeds_used"] = [1]
    cfg = project_config(tmp_path)
    cfg["variants"] = {VA: {"role": "primary"}}
    cfg["evaluation"]["cost_benchmark"] = {"variant": VA, "seed": 1}
    cdir, prepared = tmp_path / "synthetic-secondary", tmp_path / "synthetic-prepared"
    tables = cdir / "tables"
    tables.mkdir(parents=True)
    selected_pred = predictions.loc[(predictions.variant == VA) & (predictions.seed == 1) & (predictions.model == "rf")].copy()
    for seed in (1, 6):
        directory = cdir / "tasks" / f"{VA}__s{seed:02d}__rf__none"
        (directory / "private").mkdir(parents=True)
        (directory / "DONE").touch()
        if seed == 6:
            # Must be excluded before any attempt to decode/read this out-of-prefix input.
            (directory / "private" / "predictions.parquet").write_bytes(b"out-of-prefix sentinel")
            continue
        p = selected_pred.copy()
        for label in range(1, 6):
            p[f"proba_{label}"] = (p.y_pred == label).astype(float)
        p.to_parquet(directory / "private" / "predictions.parquet", index=False)
        (directory / "result.json").write_text(json.dumps({"task": {"variant": VA, "seed": seed,
            "model": "rf", "strategy": "none"}, "data": {"train_class_counts": {str(k): 10 for k in range(1, 6)}}}), encoding="utf-8")
    (prepared / "private").mkdir(parents=True)
    mapping = pd.DataFrame({"stay_id": selected_pred.stay_id, "pain_status": "numeric", **{v: 1. for v in VITALS}})
    mapping.iloc[0, mapping.columns.get_loc(VITALS[0])] = np.nan
    mapping.to_parquet(prepared / "private" / f"{VA}.parquet", index=False)

    text = summary._strata_section(cfg, cdir, prepared, ["rf"], 11, result)
    assert "omitted" not in text.lower()
    assert set(pd.read_parquet(tables / "strata.parquet").seed) == {1}
    text = summary._decodings_section(cdir, VA, ["rf"], result)
    assert "omitted" not in text.lower()
    assert set(pd.read_parquet(tables / "decodings.parquet").seed) == {1}

    importance = []
    for seed, drop in ((1, .2), (6, .8)):
        baseline = metrics.loc[(metrics.variant == VA) & (metrics.seed == seed) & (metrics.model == "rf") &
                               (metrics.split == "test") & (metrics.metric == "macro_f1"), "value"].iloc[0]
        importance.append({"variant": VA, "seed": seed, "model": "rf", "strategy": "none", "group": "synthetic",
                           "repeat": 0, "macro_f1_base": baseline, "macro_f1_drop": drop, "qwk_drop": .1})
    pd.DataFrame(importance).to_parquet(tables / "importance.parquet", index=False)
    selected = metrics.loc[metrics.seed == 1]
    text = summary._importance_section(cdir, cfg, selected, result)
    assert "0.2000" in text and "0.8000" not in text

    cost = pd.DataFrame([{"model": model, "strategy": "none", "fit_seconds": fit,
                          "predict_ms_per_1000": 2., "repeat": 0, "host": "synthetic", "at": FINISHED}
                         for model, fit in (("rf", 1.), ("not_eligible", 999.))])
    cost.to_parquet(tables / "cost_benchmark.parquet", index=False)
    result["prediction_integrity"]["valid"] = False
    text = summary._cost_table(cdir, cfg, result)
    assert "rf" in text and "not_eligible" not in text and "measurement timestamps" in text
    assert "omitted" not in text.lower()
    assert "omitted" in summary._strata_section(cfg, cdir, prepared, ["rf"], 11, result).lower()
    assert "omitted" in summary._decodings_section(cdir, VA, ["rf"], result).lower()
