"""Shared helpers for the test-suite (SYNTHETIC data only, never MIMIC).

Fixtures live in each test module (importing fixtures across modules trips ruff F811), so the
heavy lifting is done here by plain functions.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from tests.conftest import REPO
from triagebench.evaluation.metrics import scalar_metrics
from triagebench.evaluation.protocol import TaskContext
from triagebench.runner.data_stages import stage_ingest, stage_prepare
from triagebench.utils.config import load_config, science_hash

FORBIDDEN_FEATURES = ("acuity", "subject_id", "stay_id", "chiefcomplaint")


def make_cfg(root: Path, zip_path: Path, overrides: list[str] | tuple[str, ...] = ()) -> dict:
    """Smoke profile with every path redirected into ``root`` (a pytest tmp dir)."""
    root = Path(root)
    return load_config(
        REPO / "configs" / "main.yaml",
        profile="smoke",
        overrides=[
            f"dataset.zip_path={Path(zip_path).as_posix()}",
            f"dataset.extract_dir={(root / 'extracted').as_posix()}",
            f"paths.outputs={(root / 'outputs').as_posix()}",
            f"paths.reports={(root / 'reports').as_posix()}",
            *overrides,
        ],
    )


def prepare(cfg: dict) -> tuple[dict, Path]:
    ingest = stage_ingest(cfg)
    return ingest, stage_prepare(cfg, ingest)


def make_ctx(cfg: dict, prepared: Path, campaign_dir: Path) -> TaskContext:
    return TaskContext(cfg=cfg, campaign_dir=Path(campaign_dir), prepared_dir=Path(prepared), threads=1,
                       science_hash=science_hash(cfg))


def comparable(result: dict) -> dict:
    """Part of a ``run_task`` result that must be bit-identical between equivalent runs
    (timings, RSS and timestamps excluded)."""
    return {
        "best_trial_index": result["best_trial_index"],
        "frozen_config_hash": result["frozen_config_hash"],
        "best_val": result["hpo"]["best_val"],
        "val": scalar_metrics(result["val"]),
        "test": scalar_metrics(result["test"]),
        "val_confusion": result["val"]["confusion"],
        "test_confusion": result["test"]["confusion"],
        "data": result["data"],
    }


def _nan_to_none(obj):
    if isinstance(obj, dict):
        return {k: _nan_to_none(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nan_to_none(v) for v in obj]
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj


def metrics_digest(result: dict) -> str:
    """SHA-256 of the integer confusion matrices + selected trial: platform-stable golden value
    (every scalar metric is a deterministic function of these counts)."""
    payload = {
        "best_trial_index": result["best_trial_index"],
        "params": result["frozen_config"]["params"],
        "val_confusion": result["val"]["confusion"],
        "test_confusion": result["test"]["confusion"],
    }
    text = json.dumps(_nan_to_none(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def trial_indices(path: Path) -> list[int]:
    from triagebench.utils.io import read_jsonl

    return [int(t["index"]) for t in read_jsonl(path)]


def assert_metrics_equal(a: dict, b: dict) -> None:
    """Exact equality, treating NaN == NaN."""
    assert a.keys() == b.keys()
    for key in a:
        va, vb = a[key], b[key]
        if isinstance(va, float) and isinstance(vb, float) and np.isnan(va) and np.isnan(vb):
            continue
        assert va == vb, f"{key}: {va!r} != {vb!r}"
