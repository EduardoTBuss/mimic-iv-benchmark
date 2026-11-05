"""Model registry: how to build each estimator from (fixed params + sampled params, seed, threads).

Labels are always encoded 0..K-1 before ``fit`` (XGBoost requires it) and decoded afterwards.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sklearn.dummy import DummyClassifier
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier


@dataclass(frozen=True)
class ModelSpec:
    name: str
    factory: Callable[[dict, int, int], Any]
    needs_scaling: bool
    class_weight_mode: str | None  # "param" | "sample_weight" | None (strategy not applicable)
    cost_rank: int                 # scheduling: expensive tasks start first within a block
    has_proba: bool = True


def _mlp(p: dict, seed: int, threads: int) -> MLPClassifier:
    p = dict(p)
    if "hidden_layer_sizes" in p:
        p["hidden_layer_sizes"] = tuple(p["hidden_layer_sizes"])
    return MLPClassifier(random_state=seed, **p)


def _xgb(p: dict, seed: int, threads: int) -> Any:
    from xgboost import XGBClassifier

    return XGBClassifier(random_state=seed, n_jobs=threads, **p)


def _ordinal(p: dict, seed: int, threads: int) -> Any:
    from triagebench.models.ordinal import OrdinalLogisticRegression

    return OrdinalLogisticRegression(**p)


REGISTRY: dict[str, ModelSpec] = {
    "logreg": ModelSpec("logreg", lambda p, s, t: LogisticRegression(random_state=s, **p), True, "param", 4),
    "gnb": ModelSpec("gnb", lambda p, s, t: GaussianNB(**p), True, "sample_weight", 1),
    "knn": ModelSpec("knn", lambda p, s, t: KNeighborsClassifier(n_jobs=t, **p), True, None, 6),
    "dtree": ModelSpec("dtree", lambda p, s, t: DecisionTreeClassifier(random_state=s, **p), False, "param", 2),
    "rf": ModelSpec("rf", lambda p, s, t: RandomForestClassifier(random_state=s, n_jobs=t, **p), False, "param", 9),
    "svm_rbf": ModelSpec("svm_rbf", lambda p, s, t: SVC(kernel="rbf", random_state=s, **p), True, "param", 10,
                         has_proba=False),
    "xgb": ModelSpec("xgb", _xgb, False, "sample_weight", 7),
    "mlp": ModelSpec("mlp", _mlp, True, "sample_weight", 8),
    "hgb": ModelSpec("hgb", lambda p, s, t: HistGradientBoostingClassifier(random_state=s, **p), False, "param", 5),
    "extratrees": ModelSpec("extratrees", lambda p, s, t: ExtraTreesClassifier(random_state=s, n_jobs=t, **p),
                            False, "param", 8),
    "ordinal_logit": ModelSpec("ordinal_logit", _ordinal, True, "sample_weight", 3),
    "dummy_prior": ModelSpec("dummy_prior", lambda p, s, t: DummyClassifier(random_state=s, **p), False, None, 0),
    "dummy_stratified": ModelSpec("dummy_stratified", lambda p, s, t: DummyClassifier(random_state=s, **p),
                                  False, None, 0),
}


def get_spec(name: str) -> ModelSpec:
    if name not in REGISTRY:
        raise KeyError(f"unknown model {name!r}; known: {sorted(REGISTRY)}")
    return REGISTRY[name]


def make_estimator(name: str, cfg: dict, params: dict, seed: int, threads: int) -> Any:
    fixed = (cfg["models"].get("fixed") or {}).get(name) or {}
    return get_spec(name).factory({**fixed, **params}, seed, threads)


def model_kind(name: str, cfg: dict) -> str:
    for kind in ("primary", "extra", "reference"):
        if name in cfg["models"].get(kind, []):
            return kind
    raise KeyError(name)


def model_group(name: str, cfg: dict) -> str | None:
    for group, members in (cfg["models"].get("groups") or {}).items():
        if name in members:
            return group
    return None
