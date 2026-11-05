"""Campaign directory: frozen config, manifest (one entry per run session), live control file.

``outputs/campaigns/<tag>-<science_hash[:10]>/``
    config.resolved.yaml   frozen at creation (science + runtime of the first session)
    campaign.json          id, science hash, dataset fingerprint, prepared data id
    manifest.json          sessions: git commit, versions, hardware, resources, start/end
    control.yaml           live knobs: max_workers, pause (re-read by the scheduler)
    grid.json              tasks + not-applicable combinations
    tasks/<task_id>/       state.json, trials.jsonl, result.json, DONE, worker.log, private/
    tables/, logs/
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from triagebench.runner.tasks import build_grid
from triagebench.utils.config import science_hash
from triagebench.utils.io import atomic_write_json, atomic_write_text, read_json, utc_now
from triagebench.utils.manifest import environment_snapshot


class DirtyTreeError(RuntimeError):
    """The campaign requires a clean git tree (reproducibility)."""


def campaign_id(cfg: dict) -> str:
    return f"{cfg['campaign']['tag']}-{science_hash(cfg)[:10]}"


def resolve_campaign_dir(cfg: dict) -> Path:
    return Path(cfg["paths"]["outputs"]) / "campaigns" / campaign_id(cfg)


def init_campaign(cfg: dict, ingest: dict, prepared_dir: Path) -> tuple[Path, dict]:
    cdir = resolve_campaign_dir(cfg)
    cdir.mkdir(parents=True, exist_ok=True)
    snap = environment_snapshot()
    if cfg["campaign"].get("require_clean_git", False) and snap["git"].get("dirty"):
        raise DirtyTreeError("git working tree has uncommitted changes; commit before launching this campaign")

    frozen = copy.deepcopy({k: v for k, v in cfg.items() if k != "_meta"})
    if not (cdir / "config.resolved.yaml").exists():
        atomic_write_text(cdir / "config.resolved.yaml", yaml.safe_dump(frozen, sort_keys=True, allow_unicode=True))
        atomic_write_json(cdir / "campaign.json", {
            "campaign_id": campaign_id(cfg), "science_hash": science_hash(cfg), "created_at": utc_now(),
            "tag": cfg["campaign"]["tag"], "dataset": {
                "name": cfg["dataset"]["name"], "version": cfg["dataset"]["version"], "doi": cfg["dataset"]["doi"],
                "zip_sha256": ingest["zip_sha256"],
                "files_sha256": {k: v["sha256"] for k, v in ingest["files"].items() if k.startswith("ed/")}},
            "prepared_id": Path(prepared_dir).name, "seeds": cfg["split"]["seeds"],
        })
    meta = read_json(cdir / "campaign.json")
    if meta["science_hash"] != science_hash(cfg):
        raise RuntimeError("campaign directory belongs to a different scientific configuration")

    manifest_path = cdir / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {"campaign_id": meta["campaign_id"], "sessions": []}
    manifest["sessions"].append({"started_at": utc_now(), "environment": snap, "resources": cfg["resources"],
                                 "profile": cfg.get("_meta", {}).get("profile"),
                                 "overrides": cfg.get("_meta", {}).get("overrides"), "prepared_dir": str(prepared_dir)})
    atomic_write_json(manifest_path, manifest)

    if not (cdir / "control.yaml").exists():
        atomic_write_text(cdir / "control.yaml",
                          "# Live controls, re-read every poll by the scheduler (no restart needed).\n"
                          f"max_workers: {int(cfg['resources']['max_workers'])}\npause: false\n")
    tasks, na = build_grid(cfg)
    atomic_write_json(cdir / "grid.json", {"tasks": [t.as_dict() for t in tasks], "not_applicable": na})
    return cdir, meta


def close_session(cdir: Path, summary: dict) -> None:
    path = Path(cdir) / "manifest.json"
    manifest = read_json(path)
    manifest["sessions"][-1].update({"ended_at": utc_now(), "summary": summary})
    atomic_write_json(path, manifest)
