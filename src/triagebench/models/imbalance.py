"""Imbalance strategies and the full (imblearn) pipeline of one task.

Order inside the pipeline: preprocess -> [random oversampling] -> [stratified subsample] -> model.
Samplers only act during ``fit`` (imblearn skips them at predict time), so validation and test
are never resampled. The subsample step bounds the training size of expensive models (SVM, and
KNN during HPO) and is a documented deviation configured in ``models.subsample``.
"""

from __future__ import annotations

import numpy as np
from imblearn import FunctionSampler
from imblearn.over_sampling import RandomOverSampler
from imblearn.pipeline import Pipeline as ImbPipeline
from sklearn.utils.class_weight import compute_sample_weight

from triagebench.models.registry import get_spec, make_estimator
from triagebench.preprocessing.pipeline import build_preprocessor

STRATEGIES = ("none", "class_weight", "oversample")


def applicability(model: str, strategy: str, cfg: dict) -> tuple[bool, str]:
    if strategy not in STRATEGIES:
        return False, f"unknown strategy {strategy!r}"
    if model in cfg["models"].get("reference", []) and strategy != "none":
        return False, "reference baselines run without rebalancing only"
    if strategy == "class_weight" and get_spec(model).class_weight_mode is None:
        return False, f"{model} supports neither class_weight nor sample_weight"
    return True, ""


def stratified_subsample(X, y, n: int, seed: int):
    """Keep ``n`` rows, preserving class proportions (at least one row per class)."""
    y = np.asarray(y)
    if len(y) <= n:
        return X, y
    rng = np.random.default_rng(seed)
    classes, counts = np.unique(y, return_counts=True)
    quota = np.maximum(1, np.floor(counts / counts.sum() * n).astype(int))
    keep = np.concatenate([rng.choice(np.flatnonzero(y == c), size=min(q, cnt), replace=False)
                           for c, q, cnt in zip(classes, quota, counts, strict=True)])
    keep.sort()
    return X[keep], y[keep]


def subsample_cap(model: str, cfg: dict, phase: str) -> int | None:
    """Training-size cap for ``phase`` in {"hpo", "final"} (None = no cap)."""
    entry = (cfg["models"].get("subsample") or {}).get(model)
    if not entry or not entry.get("n") or not entry.get(phase, False):
        return None
    return int(entry["n"])


def build_pipeline(model: str, params: dict, strategy: str, cfg: dict, variant_cfg: dict, seed: int,
                   threads: int, cap: int | None = None) -> ImbPipeline:
    spec = get_spec(model)
    pain_categories = cfg["cleaning"]["pain"]["status_categories"]
    pre = build_preprocessor(variant_cfg["numeric_features"], variant_cfg["categorical_features"],
                             {"pain_status": pain_categories}, scale=spec.needs_scaling,
                             missing_indicators=bool(variant_cfg.get("missing_indicators", True)))
    est = make_estimator(model, cfg, params, seed, threads)
    if strategy == "class_weight" and spec.class_weight_mode == "param":
        est.set_params(class_weight="balanced")
    steps: list = [("pre", pre)]
    if strategy == "oversample":
        steps.append(("oversample", RandomOverSampler(random_state=seed)))
    if cap is not None:
        steps.append(("subsample", FunctionSampler(func=stratified_subsample, validate=False,
                                                   kw_args={"n": cap, "seed": seed})))
    steps.append(("model", est))
    return ImbPipeline(steps)


def fit_params(model: str, strategy: str, y_encoded: np.ndarray, cap: int | None = None) -> dict:
    """Balanced sample weights for models whose class weighting goes through ``sample_weight``.

    Not combined with a subsample cap (weights would no longer align with the subsampled rows);
    no current model uses both.
    """
    if strategy == "class_weight" and get_spec(model).class_weight_mode == "sample_weight":
        if cap is not None:
            raise ValueError(f"{model}: sample_weight cannot be combined with a subsample cap")
        return {"model__sample_weight": compute_sample_weight("balanced", y_encoded)}
    return {}
