"""Configuration: YAML (+ includes) + profile overlay + CLI overrides, env expansion, hashing.

Scientific settings are hashed into the campaign id; runtime settings (paths, resources)
are not, so that changing the number of workers or the machine never forks a campaign.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

SCIENCE_SECTIONS = (
    "dataset",
    "cleaning",
    "variants",
    "features",
    "prepare",
    "split",
    "models",
    "imbalance",
    "hpo",
    "evaluation",
)
PREPARE_SECTIONS = ("dataset", "cleaning", "variants", "features", "prepare", "split")
RUNTIME_DATASET_KEYS = ("zip_path", "extract_dir", "downloaded_on")
STRATEGIES = ("none", "class_weight", "oversample")
REQUIRED_SECTIONS = (
    "campaign",
    "paths",
    "dataset",
    "features",
    "variants",
    "split",
    "models",
    "imbalance",
    "hpo",
    "evaluation",
    "resources",
    "cleaning",
)

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ConfigError(ValueError):
    """The configuration is incomplete or inconsistent."""


def expand_env(value: Any) -> Any:
    """Expand ``${VAR}`` / ``${VAR:-default}`` recursively in strings."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


def deep_merge(base: dict, override: dict | None) -> dict:
    """Recursive dict merge; ``override`` wins. Lists are replaced, not concatenated."""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _read_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def _load_with_includes(path: Path) -> dict:
    data = _read_yaml(path)
    merged: dict = {}
    for inc in data.pop("include", None) or []:
        merged = deep_merge(merged, _load_with_includes(path.parent / inc))
    return deep_merge(merged, data)


def set_dotted(cfg: dict, dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    node = cfg
    for key in keys[:-1]:
        node = node.setdefault(key, {})
        if not isinstance(node, dict):
            raise ConfigError(f"cannot set {dotted!r}: {key!r} is not a mapping")
    node[keys[-1]] = value


def resolve_profile_path(config_path: Path, profile: str) -> Path:
    candidate = Path(profile)
    if candidate.suffix in {".yaml", ".yml"}:
        return candidate
    return config_path.parent / "profiles" / f"{profile}.yaml"


def load_config(path: str | Path, profile: str | None = None, overrides: tuple[str, ...] | list[str] = ()) -> dict:
    """Load ``path`` (with includes), merge ``profile`` and ``key=value`` overrides, validate."""
    path = Path(path)
    cfg = _load_with_includes(path)
    for name in [p.strip() for p in (profile or "").split(",") if p.strip()]:
        ppath = resolve_profile_path(path, name)
        if not ppath.exists():
            raise ConfigError(f"profile not found: {ppath}")
        cfg = deep_merge(cfg, _load_with_includes(ppath))
    for item in overrides:
        if "=" not in item:
            raise ConfigError(f"override must look like key=value, got {item!r}")
        key, raw = item.split("=", 1)
        set_dotted(cfg, key.strip(), yaml.safe_load(raw))
    cfg = expand_env(cfg)
    cfg["_meta"] = {"config_path": str(path), "profile": profile, "overrides": list(overrides)}
    validate_config(cfg)
    return cfg


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(obj: Any, length: int | None = None) -> str:
    digest = hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()
    return digest[:length] if length else digest


def _view(cfg: dict, sections: tuple[str, ...]) -> dict:
    view = {k: copy.deepcopy(cfg[k]) for k in sections if k in cfg}
    for key in RUNTIME_DATASET_KEYS:
        view.get("dataset", {}).pop(key, None)
    return view


def science_view(cfg: dict) -> dict:
    return _view(cfg, SCIENCE_SECTIONS)


def science_hash(cfg: dict) -> str:
    return stable_hash(science_view(cfg))


def prepare_hash(cfg: dict, zip_sha256: str) -> str:
    """Identity of the prepared data: dataset bytes + cleaning + variants + split."""
    return stable_hash({"zip_sha256": zip_sha256, **_view(cfg, PREPARE_SECTIONS)})


def all_models(cfg: dict) -> list[str]:
    m = cfg["models"]
    return list(m.get("primary", [])) + list(m.get("extra", [])) + list(m.get("reference", []))


def validate_config(cfg: dict) -> None:
    missing = [s for s in REQUIRED_SECTIONS if s not in cfg]
    if missing:
        raise ConfigError(f"missing config sections: {missing}")

    fractions = cfg["split"]["fractions"]
    if set(fractions) != {"train", "val", "test"}:
        raise ConfigError("split.fractions must define exactly train, val and test")
    if abs(sum(fractions.values()) - 1.0) > 1e-9:
        raise ConfigError(f"split.fractions must sum to 1, got {sum(fractions.values())}")
    seeds = cfg["split"]["seeds"]
    if not seeds or len(set(seeds)) != len(seeds) or not all(isinstance(s, int) for s in seeds):
        raise ConfigError("split.seeds must be a non-empty list of unique integers")

    bad = [s for s in cfg["imbalance"]["strategies"] if s not in STRATEGIES]
    if bad:
        raise ConfigError(f"unknown imbalance strategies {bad}; allowed: {STRATEGIES}")

    if int(cfg["hpo"]["n_configs"]) < 1:
        raise ConfigError("hpo.n_configs must be >= 1")

    variants = cfg["variants"]
    primaries = [n for n, v in variants.items() if v.get("role") == "primary"]
    if len(primaries) != 1:
        raise ConfigError(f"exactly one variant must have role: primary (got {primaries})")
    for name, v in variants.items():
        bad_strat = [s for s in v.get("strategies", []) if s not in cfg["imbalance"]["strategies"]]
        if bad_strat:
            raise ConfigError(f"variant {name}: strategies {bad_strat} not in imbalance.strategies")
        if v.get("role") not in {"primary", "sensitivity"}:
            raise ConfigError(f"variant {name}: role must be primary or sensitivity")
        for key in ("numeric_features", "categorical_features", "exclude_non_numeric_pain"):
            if key not in v:
                raise ConfigError(f"variant {name}: missing {key}")
        forbidden = {cfg["features"]["target"], cfg["features"]["group"], cfg["features"]["id"], "chiefcomplaint"}
        leaked = forbidden & set(v["numeric_features"] + v["categorical_features"])
        if leaked:
            raise ConfigError(f"variant {name}: forbidden columns used as features: {sorted(leaked)}")

    models = all_models(cfg)
    if len(set(models)) != len(models):
        raise ConfigError("a model is listed twice in models.primary/extra/reference")
    spaces = cfg["models"].get("spaces", {})
    no_space = [m for m in models if m not in spaces]
    if no_space:
        raise ConfigError(f"models without a search space entry (use {{}} for none): {no_space}")
    for model, space in spaces.items():
        for name, spec in (space or {}).items():
            if spec.get("type") != "choice":
                for bound in ("low", "high"):
                    if not isinstance(spec.get(bound), (int, float)) or isinstance(spec.get(bound), bool):
                        raise ConfigError(f"models.spaces.{model}.{name}.{bound} must be a number, got {spec.get(bound)!r} "
                                          "(PyYAML reads 1.0e3 as text: write 1000.0 or 1.0e+3)")
    groups = cfg["models"].get("groups", {})
    outside = set(groups.get("simple", [])) | set(groups.get("complex", []))
    if not outside <= set(cfg["models"].get("primary", [])):
        raise ConfigError("models.groups may only contain primary models")


def primary_variant(cfg: dict) -> str:
    return next(n for n, v in cfg["variants"].items() if v["role"] == "primary")
