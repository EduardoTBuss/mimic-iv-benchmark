"""Random-search sampling from the YAML search spaces (same budget for every model)."""

from __future__ import annotations

import copy
import math

import numpy as np


def sample_param(spec: dict, rng: np.random.Generator):
    kind = spec["type"]
    if kind == "choice":
        values = spec["values"]
        return copy.deepcopy(values[int(rng.integers(len(values)))])
    lo, hi = float(spec["low"]), float(spec["high"])
    if kind == "uniform":
        return float(rng.uniform(lo, hi))
    if kind == "loguniform":
        return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))
    if kind == "intuniform":
        return int(rng.integers(int(lo), int(hi) + 1))
    if kind == "intloguniform":
        value = int(math.floor(math.exp(rng.uniform(math.log(lo), math.log(hi + 1)))))
        return int(min(max(value, int(lo)), int(hi)))
    raise ValueError(f"unknown search-space type {kind!r}")


def sample_configs(space: dict, n: int, rng: np.random.Generator, include_defaults: bool = True) -> list[dict]:
    """``n`` configurations; configuration 0 is ``{}`` (library defaults + fixed params) when
    ``include_defaults``. A model without hyper-parameters gets exactly one configuration."""
    if not space:
        return [{}]
    configs: list[dict] = [{}] if include_defaults else []
    while len(configs) < n:
        configs.append({name: sample_param(spec, rng) for name, spec in sorted(space.items())})
    return configs[:n]
