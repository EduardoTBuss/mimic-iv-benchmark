"""Command-line interface: ``python -m triagebench <command>`` (or ``triagebench <command>``).

Every command reads the same YAML configuration (``--config``/``--profile``/``--set``) and is
safe to re-run: finished work is detected and skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from triagebench.utils.config import load_config
from triagebench.utils.logging import setup_logging


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", default="configs/main.yaml", help="main YAML config")
    p.add_argument("--profile", default=None, help="profile name (configs/profiles/<name>.yaml) or path")
    p.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE",
                   help="override a config value (dotted key), repeatable")
    p.add_argument("--force", action="store_true", help="recompute this stage even if up to date")


def _cfg(args: argparse.Namespace) -> dict:
    return load_config(args.config, args.profile, args.overrides)


def cmd_env(args: argparse.Namespace) -> int:
    from triagebench.utils.manifest import environment_snapshot

    print(json.dumps(environment_snapshot(include_all_packages=False), indent=2))
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from triagebench.runner.data_stages import stage_ingest

    rec = stage_ingest(_cfg(args))
    print(f"OK {rec['zip_name']} sha256={rec['zip_sha256']} files_verified={len(rec['files'])}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    from triagebench.runner.data_stages import stage_audit, stage_ingest

    cfg = _cfg(args)
    audit = stage_audit(cfg, stage_ingest(cfg), force=args.force)
    b = audit["variant_b_bias_check"]
    print(f"audit -> {Path(cfg['paths']['reports']) / 'data_audit.md'} | stays={audit['cohort']['n_stays']} "
          f"subjects={audit['cohort']['n_subjects']} | B removal={b['overall_removal_rate']:.4f} "
          f"V={b['cramers_v']:.4f} B_can_be_primary={b['b_can_be_primary']}")
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    from triagebench.runner.data_stages import stage_ingest, stage_prepare

    cfg = _cfg(args)
    out = stage_prepare(cfg, stage_ingest(cfg), force=args.force)
    print(f"prepared -> {out}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from triagebench.runner.pipeline import run_tasks

    cfg = _cfg(args)
    summary = run_tasks(cfg, filters=_filters(args), max_workers=args.max_workers)
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("failed", 0) == 0 else 3


def cmd_run_all(args: argparse.Namespace) -> int:
    from triagebench.runner.pipeline import run_all

    cfg = _cfg(args)
    summary = run_all(cfg, force=args.force, filters=_filters(args), max_workers=args.max_workers)
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("failed", 0) == 0 else 3


def cmd_status(args: argparse.Namespace) -> int:
    from triagebench.runner.campaign import resolve_campaign_dir
    from triagebench.runner.status import campaign_status, render_status

    cdir = Path(args.campaign) if args.campaign else resolve_campaign_dir(_cfg(args))
    st = campaign_status(cdir)
    print(json.dumps(st, indent=2, default=str) if args.json else render_status(st))
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    from triagebench.runner.pipeline import analyze_and_report

    cfg = _cfg(args)
    out = analyze_and_report(cfg, campaign=Path(args.campaign) if args.campaign else None,
                             aggregates_only=args.aggregates_only)
    print(f"report -> {out}")
    return 0


def _campaign_paths(args: argparse.Namespace, cfg: dict) -> tuple[Path, Path]:
    from triagebench.runner.campaign import resolve_campaign_dir
    from triagebench.utils.io import read_json

    cdir = Path(args.campaign) if args.campaign else resolve_campaign_dir(cfg)
    prepared = Path(cfg["paths"]["outputs"]) / "prepared" / read_json(cdir / "campaign.json")["prepared_id"]
    return cdir, prepared


def cmd_importance(args: argparse.Namespace) -> int:
    from triagebench.analysis.aggregate import aggregate_campaign
    from triagebench.analysis.importance import run_importance
    from triagebench.utils.config import primary_variant

    cfg = _cfg(args)
    cdir, prepared = _campaign_paths(args, cfg)
    tables = aggregate_campaign(cdir)
    out = run_importance(cfg, cdir, prepared, tables["metrics"], primary_variant(cfg), n_repeats=args.repeats,
                         workers=args.workers)
    print(f"importance -> {out}")
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    from triagebench.runner.merge import merge_campaign

    print(json.dumps(merge_campaign(Path(args.campaign), Path(args.source)), indent=2))
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    from triagebench.runner.pipeline import run_smoke

    out = run_smoke(Path(args.workdir) if args.workdir else None, n_stays=args.n_stays, keep=args.keep)
    print(f"smoke OK -> {out}")
    return 0


def cmd_estimate(args: argparse.Namespace) -> int:
    from triagebench.runner.estimate import estimate_from_pilot

    cfg = _cfg(args)
    print(estimate_from_pilot(cfg, Path(args.pilot), workers=args.workers))
    return 0


def _filters(args: argparse.Namespace) -> dict:
    def split(v: str | None) -> list[str] | None:
        return [x for x in v.split(",") if x] if v else None

    seeds = split(getattr(args, "seeds", None))
    return {
        "variants": split(getattr(args, "variants", None)),
        "seeds": [int(s) for s in seeds] if seeds else None,
        "models": split(getattr(args, "models", None)),
        "strategies": split(getattr(args, "strategies", None)),
    }


def _add_filters(p: argparse.ArgumentParser) -> None:
    p.add_argument("--variants", help="comma-separated subset of variants")
    p.add_argument("--seeds", help="comma-separated subset of split seeds")
    p.add_argument("--models", help="comma-separated subset of models")
    p.add_argument("--strategies", help="comma-separated subset of imbalance strategies")
    p.add_argument("--max-workers", type=int, default=None, help="override resources.max_workers")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="triagebench", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, fn, helptext in [
        ("env", cmd_env, "print the environment snapshot used in manifests"),
        ("ingest", cmd_ingest, "verify SHA256SUMS and extract the PhysioNet zip"),
        ("audit", cmd_audit, "aggregate-only dataset audit -> reports/data_audit.md"),
        ("prepare", cmd_prepare, "apply cleaning variants and build patient-level splits"),
    ]:
        p = sub.add_parser(name, help=helptext)
        _common(p)
        p.set_defaults(func=fn)

    p = sub.add_parser("run", help="run (or resume) the task grid of the campaign")
    _common(p)
    _add_filters(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("run-all", help="ingest -> audit -> prepare -> tasks -> analysis -> report")
    _common(p)
    _add_filters(p)
    p.set_defaults(func=cmd_run_all)

    p = sub.add_parser("status", help="progress, ETA and failures of a campaign")
    _common(p)
    p.add_argument("--campaign", help="campaign directory (default: derived from the config)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("analyze", help="aggregate results, statistics, figures and reports/summary.md")
    _common(p)
    p.add_argument("--campaign", help="campaign directory (default: derived from the config)")
    p.add_argument("--aggregates-only", action="store_true",
                   help="do not read private predictions or prepared data; write a separate, incomplete report")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("importance", help="grouped permutation importance of the best simple/complex models (F5)")
    _common(p)
    p.add_argument("--campaign", help="campaign directory (default: derived from the config)")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--workers", type=int, default=8)
    p.set_defaults(func=cmd_importance)

    p = sub.add_parser("merge", help="copy DONE tasks of the same campaign computed on another machine")
    p.add_argument("--campaign", required=True, help="destination campaign directory")
    p.add_argument("--from", dest="source", required=True, help="source campaign directory (same science hash)")
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("smoke", help="end-to-end run on synthetic data (no MIMIC needed)")
    p.add_argument("--workdir", default=None)
    p.add_argument("--n-stays", type=int, default=2500)
    p.add_argument("--keep", action="store_true", help="keep the smoke work directory")
    p.set_defaults(func=cmd_smoke)

    p = sub.add_parser("estimate", help="project the main-campaign cost from a pilot campaign")
    _common(p)
    p.add_argument("--pilot", required=True, help="pilot campaign directory")
    p.add_argument("--workers", type=int, default=8)
    p.set_defaults(func=cmd_estimate)
    return parser


def main(argv: list[str] | None = None) -> int:
    if os.name == "posix":
        os.umask(0o077)  # DUA: everything we create is readable by the owner only
    args = build_parser().parse_args(argv)
    setup_logging()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
