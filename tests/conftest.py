"""Shared fixtures. Tests use SYNTHETIC data only (triagebench.utils.synthetic); never MIMIC."""

from __future__ import annotations

from pathlib import Path

import pytest

from triagebench.utils.config import load_config
from triagebench.utils.synthetic import write_synthetic_zip

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def synthetic_zip(tmp_path_factory) -> Path:
    return write_synthetic_zip(tmp_path_factory.mktemp("zip"), n_stays=3000, seed=0)


@pytest.fixture()
def cfg(tmp_path, synthetic_zip) -> dict:
    return load_config(
        REPO / "configs" / "main.yaml",
        profile="smoke",
        overrides=[
            f"dataset.zip_path={synthetic_zip.as_posix()}",
            f"dataset.extract_dir={(tmp_path / 'extracted').as_posix()}",
            f"paths.outputs={(tmp_path / 'outputs').as_posix()}",
            f"paths.reports={(tmp_path / 'reports').as_posix()}",
        ],
    )
