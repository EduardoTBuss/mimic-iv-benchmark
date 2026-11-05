from __future__ import annotations

import pytest

from tests.conftest import REPO
from triagebench.utils.config import ConfigError, load_config, science_hash


def test_main_config_loads_and_is_valid():
    cfg = load_config(REPO / "configs" / "main.yaml")
    assert cfg["features"]["target"] == "acuity"
    assert len(cfg["models"]["primary"]) == 8
    assert cfg["split"]["seeds"] == list(range(1, 11))


def test_runtime_settings_do_not_change_the_campaign_hash():
    base = load_config(REPO / "configs" / "main.yaml")
    moved = load_config(REPO / "configs" / "main.yaml", profile="qflex",
                        overrides=["resources.max_workers=31"])
    assert science_hash(base) == science_hash(moved)


def test_science_settings_change_the_campaign_hash():
    base = load_config(REPO / "configs" / "main.yaml")
    other = load_config(REPO / "configs" / "main.yaml", overrides=["hpo.n_configs=7"])
    assert science_hash(base) != science_hash(other)


def test_target_as_feature_is_rejected():
    with pytest.raises(ConfigError):
        load_config(REPO / "configs" / "main.yaml",
                    overrides=["variants.A_keep_encode.numeric_features=[acuity, heartrate]"])


def test_profiles_can_be_stacked():
    cfg = load_config(REPO / "configs" / "main.yaml", profile="qflex,pilot")
    assert cfg["campaign"]["tag"] == "pilot"
    assert cfg["resources"]["max_workers"] == 8
