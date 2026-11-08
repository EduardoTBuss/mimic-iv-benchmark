"""End-to-end orchestration: ingest -> audit -> prepare -> tasks -> cost benchmark -> analysis -> report."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from triagebench.analysis.aggregate import aggregate_campaign, load_predictions
from triagebench.models.imbalance import applicability
from triagebench.runner.campaign import close_session, init_campaign, resolve_campaign_dir
from triagebench.runner.data_stages import stage_audit, stage_ingest, stage_prepare
from triagebench.runner.scheduler import _SRC, THREAD_VARS, run_scheduler
from triagebench.runner.tasks import build_grid, filter_tasks
from triagebench.utils.config import all_models, load_config, primary_variant
from triagebench.utils.io import atomic_write_json, read_json
from triagebench.utils.logging import get_logger, setup_logging

log = get_logger("pipeline")
REPO = Path(__file__).resolve().parents[3]


def stats_config(cfg: dict) -> dict:
    primary = primary_variant(cfg)
    others = [v for v in cfg["variants"] if v != primary]
    groups = cfg["models"].get("groups") or {}
    na = [[m, s] for m in all_models(cfg) for s in cfg["imbalance"]["strategies"]
          if m not in cfg["models"].get("reference", []) and not applicability(m, s, cfg)[0]]
    n_seeds = len(cfg["split"]["seeds"])
    return {"variant_main": primary, "variant_sens": others[0] if others else None,
            "variant_ablation": "C_values_only",
            "strategies": list(cfg["imbalance"]["strategies"]), "not_applicable": na,
            "simple_models": list(groups.get("simple", [])), "complex_models": list(groups.get("complex", [])),
            "extra_models": list(cfg["models"].get("extra", [])), "reference_models": list(cfg["models"].get("reference", [])),
            "expected_seeds": n_seeds, "min_seeds": min(5, n_seeds),
            "train_frac": cfg["split"]["fractions"]["train"], "test_frac": cfg["split"]["fractions"]["test"]}


def run_tasks(cfg: dict, filters: dict | None = None, max_workers: int | None = None) -> dict:
    ingest = stage_ingest(cfg)
    prepared = stage_prepare(cfg, ingest)
    cdir, _ = init_campaign(cfg, ingest, prepared)
    setup_logging(cdir / "logs" / "runner.log")
    tasks = filter_tasks(build_grid(cfg)[0], filters)
    res = dict(cfg["resources"])
    if max_workers:
        res["max_workers"] = max_workers
    summary = run_scheduler(cdir, prepared, tasks, res)
    close_session(cdir, summary)
    summary["campaign"] = str(cdir)
    return summary


def run_cost_stage(cfg: dict, cdir: Path, prepared: Path) -> None:
    if not (cfg["evaluation"].get("cost_benchmark") or {}).get("enabled"):
        return
    env = os.environ.copy()
    for var in THREAD_VARS:
        env[var] = "1"
    env["PYTHONPATH"] = _SRC + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    log.info("cost benchmark (sequential, 1 thread)")
    code = subprocess.call([sys.executable, "-m", "triagebench.evaluation.costbench", "--campaign", str(cdir),
                            "--prepared", str(prepared), "--nice", str(int(cfg["resources"].get("nice", 0)))], env=env)
    if code != 0:
        log.warning("cost benchmark exited with code %s (report continues without it)", code)


def analyze_and_report(cfg: dict, campaign: Path | None = None, *, analysis_time: str | None = None,
                       aggregates_only: bool = False) -> Path:
    from triagebench.analysis.stats import REQUIRED_METRIC_COLS, run_preregistered_analysis
    from triagebench.reporting.summary import write_reports

    cdir = Path(campaign) if campaign else resolve_campaign_dir(cfg)
    meta = read_json(cdir / "campaign.json")
    prep = None if aggregates_only else Path(cfg["paths"]["outputs"]) / "prepared" / meta["prepared_id"]
    tables = aggregate_campaign(cdir)
    metrics = tables["metrics"]
    preds = load_predictions(cdir, partitions=("test",)) if not aggregates_only and not metrics.empty else None
    if metrics.empty:
        metrics = metrics.reindex(columns=REQUIRED_METRIC_COLS + ["finished_at"])
    stats = run_preregistered_analysis(metrics, preds, stats_config(cfg),
                                       n_boot=int((cfg.get("analysis") or {}).get("n_boot", 1000)),
                                       analysis_time=analysis_time)
    stats["meta"]["input_scope"] = "aggregates_only" if aggregates_only else "with_private_predictions"
    report_cfg = cfg
    if aggregates_only:
        stats["notes"].append("Aggregates-only mode: private predictions and prepared data were not read. "
                              "Prediction integrity, patient bootstrap, common-stay A/B comparisons, strata "
                              "and alternative decodings are unavailable; this is not a full empirical review.")
        report_cfg = {**cfg, "paths": {**cfg["paths"], "reports": str(Path(cfg["paths"]["reports"]) / "aggregates-only")}}
    stats_name = "stats_aggregates_only.json" if aggregates_only else "stats.json"
    atomic_write_json(cdir / "tables" / stats_name, stats)
    return write_reports(report_cfg, cdir, tables, stats, prep if prep is not None and prep.exists() else None,
                         allow_private_inputs=not aggregates_only)


def run_all(cfg: dict, force: bool = False, filters: dict | None = None, max_workers: int | None = None) -> dict:
    ingest = stage_ingest(cfg)
    stage_audit(cfg, ingest, force=force)
    prepared = stage_prepare(cfg, ingest, force=force)
    summary = run_tasks(cfg, filters=filters, max_workers=max_workers)
    if summary.get("interrupted"):
        log.warning("interrupted: analysis skipped (re-run to resume)")
        return summary
    cdir = Path(summary["campaign"])
    cb = cfg["evaluation"].get("cost_benchmark") or {}
    f = filters or {}
    if (not f.get("variants") or cb.get("variant") in f["variants"]) and (not f.get("seeds") or cb.get("seed") in f["seeds"]):
        run_cost_stage(cfg, cdir, prepared)
    try:
        from triagebench.analysis.aggregate import aggregate_campaign
        from triagebench.analysis.importance import run_importance

        run_importance(cfg, cdir, prepared, aggregate_campaign(cdir)["metrics"], primary_variant(cfg),
                       workers=int(cfg["resources"].get("max_workers", 1)))
    except Exception as exc:  # importance is complementary: never block the report
        log.warning("permutation importance failed: %s", exc)
    summary["report"] = str(analyze_and_report(cfg, cdir))
    log.info("report: %s", summary["report"])
    return summary


def run_smoke(workdir: Path | None = None, n_stays: int = 2500, keep: bool = False) -> Path:
    """Full pipeline on a synthetic archive (no MIMIC access needed)."""
    from triagebench.utils.synthetic import write_synthetic_zip

    work = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="triagebench-smoke-"))
    zip_path = write_synthetic_zip(work / "zip", n_stays=n_stays, seed=0)
    cfg = load_config(REPO / "configs" / "main.yaml", "smoke", [
        f"dataset.zip_path={zip_path.as_posix()}", f"dataset.extract_dir={(work / 'extracted').as_posix()}",
        f"paths.outputs={(work / 'outputs').as_posix()}", f"paths.reports={(work / 'reports').as_posix()}"])
    summary = run_all(cfg)
    if summary.get("failed"):
        raise RuntimeError(f"smoke: {summary['failed']} task(s) failed: {summary.get('failed_ids')}")
    report = Path(summary["report"])
    leaked = [p for p in (work / "reports").rglob("*") if p.suffix in {".csv", ".gz", ".parquet", ".joblib"}]
    if leaked:
        raise RuntimeError(f"smoke: data-like files inside reports/: {leaked}")
    if not keep and workdir is None:
        out = Path(tempfile.gettempdir()) / "triagebench-smoke-last-summary.md"
        shutil.copyfile(report, out)
        shutil.rmtree(work, ignore_errors=True)
        return out
    return report
