"""Pre-registered statistical analysis of the ED-triage benchmark.

Implements ``docs/analysis_plan.md`` (read it first).  Everything here is a pure function of
the ``metrics`` table (and, optionally, of the PRIVATE ``predictions`` table); nothing reads
files.  Conventions:

* ``acuity`` classes are 1..5 (1 = most urgent); confusion matrices are ``cm[true-1, pred-1]``.
* The primary metric is Macro-F1 on the TEST partition.  Selection of "best of group" uses
  VALIDATION Macro-F1 only, never test.
* Inference over seeds uses the Nadeau-Bengio corrected resampled t-test (the 10 holdout
  splits overlap, so naive t / Wilcoxon over seeds are anti-conservative).
* Counts of 1..10 are rendered as ``"<11"`` in anything that leaves the machine.
"""

from __future__ import annotations

import copy
import math
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sps
from statsmodels.stats.multitest import multipletests

N_CLASSES = 5
SMALL_COUNT = 11  # counts in 1..SMALL_COUNT-1 are masked as "<11"
SMALL_LABEL = "<11"

DEFAULT_CFG: dict[str, Any] = {
    "variant_main": "A_keep_encode",
    "variant_sens": "B_pain_numeric_only",
    "strategies": ["none", "class_weight", "oversample"],
    # (model, strategy) pairs that do not exist by design (NOT failures)
    "not_applicable": [["knn", "class_weight"]],
    # list order is also the deterministic tie-break order for "best of group"
    "simple_models": ["logreg", "gnb", "knn", "dtree"],
    "complex_models": ["rf", "svm_rbf", "xgb", "mlp"],
    "extra_models": ["hgb", "extratrees", "ordinal_logit"],
    "reference_models": ["dummy_prior", "dummy_stratified"],
    "expected_seeds": 10,
    "min_seeds": 5,
    "seed_cap": None,  # optional hard cap on seeds considered (never result-driven)
    "train_frac": 0.70,
    "test_frac": 0.15,
    "alpha": 0.05,
    "h2_metrics": ["recall_1", "macro_f1", "balanced_accuracy"],
    "h2_descriptive_metrics": ["precision_1", "accuracy", "qwk"],
    "anomaly": {"seed_sd_macro_f1": 0.02, "val_test_gap": 0.03, "below_dummy_margin": 0.0},
}

REQUIRED_METRIC_COLS = ["variant", "seed", "model", "strategy", "split", "metric", "value"]
REQUIRED_PRED_COLS = [
    "variant", "seed", "model", "strategy", "stay_id", "subject_id", "partition", "y_true", "y_pred",
]  # fmt: skip

LOW_POWER_WARNING = (
    "Poder baixo: Friedman/Nemenyi usam as seeds como blocos, mas os holdouts se sobrepõem "
    "(blocos não independentes); os p-valores são anticonservadores e o resultado é descritivo."
)


# --------------------------------------------------------------------------------------
# generic helpers
# --------------------------------------------------------------------------------------
def mask_count(n: Any) -> str:
    """Render a count for reports: 1..10 -> '<11'; otherwise the integer."""
    if n is None:
        return "—"
    try:
        if isinstance(n, float) and not math.isfinite(n):
            return "—"
        k = int(round(float(n)))
    except (TypeError, ValueError):
        return str(n)
    if 1 <= k < SMALL_COUNT:
        return SMALL_LABEL
    return str(k)


def _mask_value(n: float) -> int | str:
    """Same as mask_count but returns an int when safe (for JSON results)."""
    k = int(round(float(n)))
    return SMALL_LABEL if 1 <= k < SMALL_COUNT else k


def _merge(base: dict, over: dict | None) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _clean(obj: Any) -> Any:
    """Make an object JSON-serialisable (numpy -> python, NaN/inf -> None, keys -> str)."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _clean(obj.tolist())
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if obj is None or isinstance(obj, str):
        return obj
    return str(obj)


def _fin(x: Any) -> bool:
    try:
        return bool(np.isfinite(x))
    except TypeError:
        return False


# --------------------------------------------------------------------------------------
# confusion-matrix metrics (vectorised over leading axes)
# --------------------------------------------------------------------------------------
def _safe_div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = np.broadcast_arrays(np.asarray(a, float), np.asarray(b, float))
    out = np.zeros(a.shape, dtype=float)
    np.divide(a, b, out=out, where=b > 0)
    return out


def metrics_from_confusion(cm: np.ndarray) -> dict[str, Any]:
    """Metrics from confusion matrices ``cm[..., true, pred]`` (shape ``(..., 5, 5)``).

    Matches sklearn: ``f1_score(average="macro", labels=1..5, zero_division=0)``;
    ``balanced_accuracy_score`` (mean recall over classes with support > 0);
    ``cohen_kappa_score(weights="quadratic")``; ordinal MAE.  Leading axes are preserved, so a
    stack of bootstrap replicates is evaluated in one call.
    """
    cm = np.asarray(cm, dtype=float)
    if cm.shape[-2:] != (N_CLASSES, N_CLASSES):
        raise ValueError(f"cm must have trailing shape (5, 5); got {cm.shape}")
    tp = np.diagonal(cm, axis1=-2, axis2=-1)
    support = cm.sum(-1)
    predicted = cm.sum(-2)
    n = cm.sum((-1, -2))
    recall = _safe_div(tp, support)
    precision = _safe_div(tp, predicted)
    f1 = _safe_div(2 * tp, support + predicted)
    has_support = support > 0
    n_sup = has_support.sum(-1)
    balanced = _safe_div((recall * has_support).sum(-1), n_sup)
    idx = np.arange(N_CLASSES)
    dist = np.abs(idx[:, None] - idx[None, :]).astype(float)
    mae = _safe_div((cm * dist).sum((-1, -2)), n)
    expected = support[..., :, None] * predicted[..., None, :] / np.where(n > 0, n, 1)[..., None, None]
    w = dist**2
    num = (w * cm).sum((-1, -2))
    den = (w * expected).sum((-1, -2))
    qwk = np.where(den > 0, 1.0 - _safe_div(num, den), np.nan)
    return {
        "macro_f1": f1.mean(-1),
        "balanced_accuracy": balanced,
        "accuracy": _safe_div(tp.sum(-1), n),
        "qwk": qwk,
        "mae_ordinal": mae,
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "n": n,
    }


def confusion_matrix_from_labels(y_true: np.ndarray, y_pred: np.ndarray) -> np.ndarray:
    """5x5 confusion matrix (rows = true, cols = pred) for labels in 1..5."""
    yt = np.asarray(y_true, dtype=np.int64) - 1
    yp = np.asarray(y_pred, dtype=np.int64) - 1
    flat = np.bincount(yt * N_CLASSES + yp, minlength=N_CLASSES**2)
    return flat.reshape(N_CLASSES, N_CLASSES).astype(float)


def patient_confusions(
    subject_id: np.ndarray, y_true: np.ndarray, y_pred: np.ndarray, universe: np.ndarray
) -> np.ndarray:
    """One 5x5 confusion matrix per patient: array ``(P, 5, 5)`` indexed like ``universe``.

    ``universe`` is the sorted array of unique subject ids.  Rows whose subject is not in the
    universe are dropped.  Fully vectorised (searchsorted + bincount).
    """
    subject_id = np.asarray(subject_id)
    p = len(universe)
    pos = np.searchsorted(universe, subject_id)
    ok = (pos < p) & (universe[np.minimum(pos, p - 1)] == subject_id)
    yt = np.asarray(y_true, dtype=np.int64)[ok] - 1
    yp = np.asarray(y_pred, dtype=np.int64)[ok] - 1
    flat = pos[ok] * N_CLASSES**2 + yt * N_CLASSES + yp
    return np.bincount(flat, minlength=p * N_CLASSES**2).astype(float).reshape(p, N_CLASSES, N_CLASSES)


# --------------------------------------------------------------------------------------
# inference
# --------------------------------------------------------------------------------------
def corrected_resampled_ttest(
    diffs: Any, n_train: float, n_test: float, alpha: float = 0.05
) -> dict[str, Any]:
    """Nadeau-Bengio (2003) corrected resampled t-test on paired per-split differences.

    Variance of the mean is ``(1/k + n_test/n_train) * s^2`` instead of ``s^2 / k``, accounting
    for the overlap between training sets (only the ratio ``n_test/n_train`` matters).
    Two-sided p and ``(1-alpha)`` CI use a t distribution with ``k-1`` d.o.f.  The naive
    (uncorrected) result is returned under ``"naive"`` for comparison only.
    """
    d = np.asarray(diffs, dtype=float)
    d = d[np.isfinite(d)]
    k = len(d)
    out: dict[str, Any] = {"k": k, "n_train": n_train, "n_test": n_test, "alpha": alpha}
    nan = float("nan")
    if k < 2:
        out.update(mean=float(d.mean()) if k else nan, sd=nan, se=nan, t=nan, df=k - 1, p=nan,
                   p_greater=nan, ci_low=nan, ci_high=nan, dz=nan, naive=None)  # fmt: skip
        return out
    mean = float(d.mean())
    var = float(d.var(ddof=1))
    sd = math.sqrt(var)
    tcrit = float(sps.t.ppf(1 - alpha / 2, k - 1))

    def _one(se: float) -> dict[str, float]:
        if se == 0.0:
            t = 0.0 if mean == 0.0 else math.copysign(math.inf, mean)
            p = 1.0 if mean == 0.0 else 0.0
            pg = 0.5 if mean == 0.0 else (0.0 if mean > 0 else 1.0)
        else:
            t = mean / se
            p = float(2 * sps.t.sf(abs(t), k - 1))
            pg = float(sps.t.sf(t, k - 1))
        return {"se": se, "t": t, "p": p, "p_greater": pg,
                "ci_low": mean - tcrit * se, "ci_high": mean + tcrit * se}  # fmt: skip

    corr = _one(math.sqrt((1.0 / k + n_test / n_train) * var))
    naive = _one(math.sqrt(var / k))
    out.update(mean=mean, sd=sd, df=k - 1, dz=(mean / sd if sd > 0 else nan), naive=naive, **corr)
    return out


def wilcoxon_exact(diffs: Any) -> float:
    """Exact two-sided Wilcoxon signed-rank p (descriptive only; ignores split overlap)."""
    d = np.asarray(diffs, dtype=float)
    d = d[np.isfinite(d)]
    if len(d) < 2 or np.all(d == 0):
        return 1.0 if len(d) >= 2 else float("nan")
    try:
        return float(sps.wilcoxon(d, method="auto").pvalue)
    except ValueError:
        return float("nan")


def holm_adjust(pvals: list[float]) -> list[float]:
    """Holm step-down adjusted p-values (NaN-safe: NaN stays NaN and is excluded)."""
    p = np.asarray(pvals, dtype=float)
    out = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    if ok.any():
        out[ok] = multipletests(p[ok], method="holm")[1]
    return out.tolist()


def _metric_from_cm(cm: np.ndarray, metric: str) -> np.ndarray:
    m = metrics_from_confusion(cm)
    if metric not in m or metric in ("recall", "precision", "f1"):
        raise ValueError(f"unsupported bootstrap metric: {metric}")
    return m[metric]


def cluster_bootstrap_ci(
    patient_cms: dict[str, np.ndarray],
    *,
    metric: str = "macro_f1",
    n_boot: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
    contrasts: list[tuple[str, str]] | None = None,
    chunk: int = 250,
) -> dict[str, Any]:
    """Percentile CI by resampling PATIENTS (cluster bootstrap) from per-patient confusions.

    ``patient_cms[name]`` is ``(P, 5, 5)`` with the same patient axis for every name, so the
    same resample is applied to all models (paired contrasts are valid).  A resample is a
    multinomial draw of P patients with replacement; replicate confusion matrices are
    ``weights @ cms`` (no Python loop over rows).  Reproducible given ``seed``.
    """
    names = list(patient_cms)
    if not names:
        raise ValueError("patient_cms is empty")
    p = patient_cms[names[0]].shape[0]
    if any(patient_cms[k].shape[0] != p for k in names):
        raise ValueError("all patient_cms must share the patient axis")
    m = len(names)
    stack = np.concatenate([patient_cms[k].reshape(p, -1) for k in names], axis=1)
    point = _metric_from_cm(stack.sum(0).reshape(m, N_CLASSES, N_CLASSES), metric)
    rng = np.random.default_rng(seed)
    reps = np.empty((n_boot, m))
    done = 0
    while done < n_boot:
        b = min(chunk, n_boot - done)
        draws = rng.integers(0, p, size=(b, p)) + (np.arange(b) * p)[:, None]
        w = np.bincount(draws.ravel(), minlength=b * p).reshape(b, p).astype(float)
        reps[done : done + b] = _metric_from_cm((w @ stack).reshape(b, m, N_CLASSES, N_CLASSES), metric)
        done += b
    lo, hi = np.nanquantile(reps, [alpha / 2, 1 - alpha / 2], axis=0)
    res: dict[str, Any] = {
        "metric": metric, "n_boot": n_boot, "alpha": alpha, "n_clusters": p,
        "point": {k: float(point[i]) for i, k in enumerate(names)},
        "ci": {k: [float(lo[i]), float(hi[i])] for i, k in enumerate(names)},
        "se": {k: float(np.nanstd(reps[:, i], ddof=1)) for i, k in enumerate(names)},
        "contrasts": {},
    }  # fmt: skip
    for a, b_ in contrasts or []:
        i, j = names.index(a), names.index(b_)
        dr = reps[:, i] - reps[:, j]
        l2, h2 = np.nanquantile(dr, [alpha / 2, 1 - alpha / 2])
        res["contrasts"][f"{a}-{b_}"] = {
            "point": float(point[i] - point[j]), "ci": [float(l2), float(h2)],
            "se": float(np.nanstd(dr, ddof=1)),
        }  # fmt: skip
    return res


# --------------------------------------------------------------------------------------
# data access
# --------------------------------------------------------------------------------------
class _Store:
    """Indexed view of the long metrics table: (variant, model, strategy, split, metric) -> Series(seed)."""

    def __init__(self, metrics: pd.DataFrame) -> None:
        self._d: dict[tuple, pd.Series] = {}
        self.n_duplicates = 0
        self.n_nonfinite = 0
        g = metrics.groupby(["variant", "model", "strategy", "split", "metric"], sort=False)
        for key, sub in g:
            dup = sub.duplicated("seed", keep="last")
            self.n_duplicates += int(dup.sum())
            sub = sub[~dup]
            ser = pd.Series(sub["value"].to_numpy(float), index=sub["seed"].to_numpy(int))
            self.n_nonfinite += int((~np.isfinite(ser.to_numpy())).sum())
            self._d[tuple(str(x) for x in key)] = ser
        self.variants = set(metrics["variant"].astype(str).unique())

    def get(self, variant: str, model: str, strategy: str, split: str, metric: str) -> pd.Series:
        return self._d.get((variant, model, strategy, split, metric), pd.Series(dtype=float))

    def value(self, variant, model, strategy, split, metric, seed) -> float:
        s = self.get(variant, model, strategy, split, metric)
        return float(s[seed]) if seed in s.index else float("nan")


class _Preds:
    """Lazy access to TEST predictions by (variant, seed, strategy, model)."""

    def __init__(self, predictions: pd.DataFrame) -> None:
        df = predictions[predictions["partition"].astype(str) == "test"].reset_index(drop=True)
        self.cols = {
            "stay_id": df["stay_id"].to_numpy(np.int64),
            "subject_id": df["subject_id"].to_numpy(np.int64),
            "y_true": df["y_true"].to_numpy(np.int64),
            "y_pred": df["y_pred"].to_numpy(np.int64),
        }
        keys = [df["variant"].astype(str), df["seed"].astype(int), df["strategy"].astype(str), df["model"].astype(str)]
        self.idx = pd.DataFrame(dict(zip("vsmo", keys, strict=True))).groupby(list("vsmo"), sort=False).indices

    def get(self, variant: str, seed: int, strategy: str, model: str) -> dict[str, np.ndarray] | None:
        ix = self.idx.get((variant, int(seed), strategy, model))
        if ix is None:
            return None
        return {k: v[ix] for k, v in self.cols.items()}


# --------------------------------------------------------------------------------------
# plan pieces
# --------------------------------------------------------------------------------------
def _primary(cfg: dict) -> list[str]:
    return list(cfg["simple_models"]) + list(cfg["complex_models"])


def _is_na(cfg: dict, model: str, strategy: str) -> bool:
    if model in cfg["reference_models"] and strategy != "none":
        return True
    return [model, strategy] in [list(x) for x in cfg["not_applicable"]]


def select_seeds(store: _Store, cfg: dict) -> dict[str, Any]:
    """Seed cut rule (time/completeness only, never result-driven).

    Use all expected seeds if complete; else the largest k >= min_seeds such that seeds 1..k
    are complete (finite val and test Macro-F1) for every primary model x strategy of the main
    variant; else none.
    """
    expected = list(range(1, int(cfg["expected_seeds"]) + 1))
    if cfg.get("seed_cap"):
        expected = [s for s in expected if s <= int(cfg["seed_cap"])]
    v = cfg["variant_main"]
    complete, why = {}, {}
    for s in expected:
        missing = []
        for m in _primary(cfg):
            for st in cfg["strategies"]:
                if _is_na(cfg, m, st):
                    continue
                for sp in ("val", "test"):
                    if not _fin(store.value(v, m, st, sp, "macro_f1", s)):
                        missing.append(f"{m}/{st}/{sp}")
        complete[s] = not missing
        why[s] = missing
    k = 0
    while k < len(expected) and complete[expected[k]]:
        k += 1
    if k == len(expected) and k > 0:
        used, rule = expected, "todas as seeds esperadas completas"
    elif k >= int(cfg["min_seeds"]):
        used, rule = expected[:k], f"maior prefixo completo 1..{k} (>= {cfg['min_seeds']})"
    else:
        used, rule = [], f"prefixo completo 1..{k} < mínimo {cfg['min_seeds']}: análise principal não executada"
    return {
        "used": used, "rule": rule, "expected": expected,
        "complete_seeds": [s for s in expected if complete[s]],
        "incomplete_seeds": [s for s in expected if not complete[s]],
        "n_missing_cells_by_seed": {s: len(why[s]) for s in expected if why[s]},
    }  # fmt: skip


def _select_best(store: _Store, variant: str, models: list[str], strategy: str, seed: int) -> tuple[str | None, float]:
    """Best model of a group on VALIDATION Macro-F1 for one seed (ties -> list order)."""
    best, best_v = None, -np.inf
    for m in models:
        v = store.value(variant, m, strategy, "val", "macro_f1", seed)
        if _fin(v) and v > best_v:
            best, best_v = m, v
    return best, float(best_v) if best is not None else float("nan")


def _verdict(corr: dict, diffs: np.ndarray, delta: float) -> dict[str, Any]:
    all_pos = bool(len(diffs) > 0 and np.all(diffs > 0))
    lo_ok = bool(_fin(corr["ci_low"]) and corr["ci_low"] > delta)
    ok = all_pos and lo_ok
    return {
        "all_positive": all_pos,
        "ci_lower_gt_delta": lo_ok,
        "reverse_direction_ci": bool(_fin(corr["ci_high"]) and corr["ci_high"] < 0),
        "verdict": "consistente" if ok else "sem_superioridade_consistente",
        "verdict_label": (
            "Superioridade consistente do grupo complexo"
            if ok else "Sem superioridade consistente do grupo complexo"
        ),
    }  # fmt: skip


def _h1(store: _Store, cfg: dict, seeds: list[int], delta: float, variant: str) -> dict[str, Any]:
    simple, cplx = cfg["simple_models"], cfg["complex_models"]
    rows = []
    for s in seeds:
        ms, vs = _select_best(store, variant, simple, "none", s)
        mc, vc = _select_best(store, variant, cplx, "none", s)
        ts = store.value(variant, ms, "none", "test", "macro_f1", s) if ms else float("nan")
        tc = store.value(variant, mc, "none", "test", "macro_f1", s) if mc else float("nan")
        rows.append({"seed": s, "simple_model": ms, "complex_model": mc, "val_simple": vs, "val_complex": vc,
                     "test_simple": ts, "test_complex": tc, "diff": tc - ts})  # fmt: skip
    diffs = np.array([r["diff"] for r in rows], dtype=float)
    corr = corrected_resampled_ttest(diffs, cfg["train_frac"], cfg["test_frac"], cfg["alpha"])
    res: dict[str, Any] = {
        "variant": variant, "strategy": "none", "metric": "macro_f1", "delta": delta,
        "seeds": list(seeds), "per_seed": rows,
        "n_seeds_valid": int(np.isfinite(diffs).sum()),
        "mean_diff": corr["mean"], "sd_diff": corr["sd"], "dz": corr["dz"],
        "corrected": {k: corr[k] for k in ("se", "t", "df", "p", "ci_low", "ci_high")},
        "naive": corr["naive"], "wilcoxon_exact_p_descriptive": wilcoxon_exact(diffs),
        "selection_counts": {
            "simple": {m: sum(r["simple_model"] == m for r in rows) for m in simple},
            "complex": {m: sum(r["complex_model"] == m for r in rows) for m in cplx},
        },
    }  # fmt: skip
    res.update(_verdict(corr, diffs[np.isfinite(diffs)], delta))
    # robustness: one fixed model per group, chosen by MEAN validation Macro-F1 across seeds
    fixed = {}
    for g, models in (("simple", simple), ("complex", cplx)):
        means = {m: float(np.nanmean([store.value(variant, m, "none", "val", "macro_f1", s) for s in seeds]))
                 for m in models}  # fmt: skip
        means = {m: v for m, v in means.items() if _fin(v)}
        fixed[g] = max(means, key=means.get) if means else None
    if fixed["simple"] and fixed["complex"]:
        fd = np.array([store.value(variant, fixed["complex"], "none", "test", "macro_f1", s)
                       - store.value(variant, fixed["simple"], "none", "test", "macro_f1", s) for s in seeds])  # fmt: skip
        fc = corrected_resampled_ttest(fd, cfg["train_frac"], cfg["test_frac"], cfg["alpha"])
        res["robustness_fixed_models"] = {"simple": fixed["simple"], "complex": fixed["complex"],
                                          "mean_diff": fc["mean"], "ci_low": fc["ci_low"], "ci_high": fc["ci_high"],
                                          "p": fc["p"], **_verdict(fc, fd[np.isfinite(fd)], delta)}  # fmt: skip
    return res


def _models_present(store: _Store, cfg: dict, variant: str, kinds: tuple[str, ...]) -> list[str]:
    pool: list[str] = []
    if "primary" in kinds:
        pool += _primary(cfg)
    if "extra" in kinds:
        pool += list(cfg["extra_models"])
    if "reference" in kinds:
        pool += list(cfg["reference_models"])
    return [m for m in pool if any(k[0] == variant and k[1] == m for k in store._d)]


def _h2(store: _Store, cfg: dict, seeds: list[int]) -> dict[str, Any]:
    v = cfg["variant_main"]
    confirm = list(cfg["h2_metrics"])
    desc = list(cfg["h2_descriptive_metrics"])
    primaries = set(_primary(cfg))
    rows = []
    for strat in ("class_weight", "oversample"):
        for m in _models_present(store, cfg, v, ("primary", "extra")):
            if _is_na(cfg, m, strat):
                continue
            for metric in confirm + desc:
                a = store.get(v, m, strat, "test", metric)
                b = store.get(v, m, "none", "test", metric)
                used = [s for s in seeds if s in a.index and s in b.index and _fin(a[s]) and _fin(b[s])]
                d = np.array([a[s] - b[s] for s in used], dtype=float)
                c = corrected_resampled_ttest(d, cfg["train_frac"], cfg["test_frac"], cfg["alpha"])
                rows.append({
                    "model": m, "kind": "primary" if m in primaries else "extra", "strategy": strat,
                    "metric": metric, "confirmatory": metric in confirm and m in primaries,
                    "n_pairs": len(used), "mean_diff": c["mean"], "sd_diff": c["sd"], "dz": c["dz"],
                    "ci_low": c["ci_low"], "ci_high": c["ci_high"], "p": c["p"],
                    "wilcoxon_exact_p_descriptive": wilcoxon_exact(d), "p_holm": None,
                    "n_positive_seeds": int((d > 0).sum()),
                })  # fmt: skip
    # Holm across the primary models, within (strategy, confirmatory metric)
    for strat in ("class_weight", "oversample"):
        for metric in confirm:
            fam = [r for r in rows if r["strategy"] == strat and r["metric"] == metric and r["confirmatory"]]
            for r, pa in zip(fam, holm_adjust([r["p"] for r in fam]), strict=True):
                r["p_holm"] = pa
    alpha = cfg["alpha"]
    summary = []
    for strat in ("class_weight", "oversample"):
        for m in _primary(cfg):
            if _is_na(cfg, m, strat):
                continue
            rr = [r for r in rows if r["model"] == m and r["strategy"] == strat and r["confirmatory"]]
            if len(rr) != len(confirm):
                summary.append({"model": m, "strategy": strat, "supported": None, "reason": "dados ausentes"})
                continue
            ok = all(_fin(r["p_holm"]) and r["p_holm"] < alpha and r["mean_diff"] > 0 for r in rr)
            summary.append({"model": m, "strategy": strat, "supported": bool(ok),
                            "metrics_supported": [r["metric"] for r in rr
                                                  if _fin(r["p_holm"]) and r["p_holm"] < alpha and r["mean_diff"] > 0]})  # fmt: skip
    return {"variant": v, "reference_strategy": "none", "rows": rows, "summary": summary,
            "rule": "suportada se as 3 métricas têm diferença média > 0 e p_Holm < alpha (inter-união)"}  # fmt: skip


H3_METRICS = ["under_triage_rate", "over_triage_rate", "severe_under_triage_rate", "adjacent_error_share"]


def _h3(store: _Store, cfg: dict, seeds: list[int]) -> dict[str, Any]:
    v = cfg["variant_main"]
    rows = []
    for m in _models_present(store, cfg, v, ("primary", "extra", "reference")):
        for strat in cfg["strategies"]:
            if _is_na(cfg, m, strat):
                continue
            r: dict[str, Any] = {"model": m, "strategy": strat}
            vals = {}
            for metric in H3_METRICS:
                s = store.get(v, m, strat, "test", metric)
                x = np.array([s[k] for k in seeds if k in s.index and _fin(s[k])], dtype=float)
                vals[metric] = x
                r[metric] = float(x.mean()) if len(x) else None
                r[metric + "_sd"] = float(x.std(ddof=1)) if len(x) > 1 else None
            adj = vals["adjacent_error_share"]
            r["distant_error_share"] = (1.0 - r["adjacent_error_share"]) if r["adjacent_error_share"] is not None else None
            r["adjacent_majority_all_seeds"] = bool(len(adj) > 0 and np.all(adj > 0.5))
            r["n_seeds"] = int(len(adj))
            rows.append(r)
    cand = [r for r in rows if not r["model"].startswith("dummy") and r["n_seeds"] > 0]
    return {"variant": v, "rows": rows,
            "n_models_adjacent_majority": sum(r["adjacent_majority_all_seeds"] for r in cand),
            "n_models_evaluated": len(cand)}  # fmt: skip


def _ranking(store: _Store, cfg: dict, seeds: list[int], notes: list[str]) -> dict[str, Any]:
    v = cfg["variant_main"]
    out: dict[str, Any] = {"variant": v, "metric": "macro_f1", "split": "test", "warning": LOW_POWER_WARNING,
                           "by_strategy": {}}  # fmt: skip
    for strat in cfg["strategies"]:
        cand = [m for m in _models_present(store, cfg, v, ("primary", "extra")) if not _is_na(cfg, m, strat)]
        cols, dropped = {}, []
        for m in cand:
            s = store.get(v, m, strat, "test", "macro_f1")
            if all(k in s.index and _fin(s[k]) for k in seeds):
                cols[m] = np.array([s[k] for k in seeds], dtype=float)
            else:
                dropped.append(m)
        if dropped:
            notes.append(f"Ranking/{strat}: modelos fora do Friedman por seeds incompletas: {', '.join(dropped)}.")
        refs = {}
        for m in cfg["reference_models"]:
            s = store.get(v, m, strat, "test", "macro_f1")
            x = [s[k] for k in seeds if k in s.index and _fin(s[k])]
            if x:
                refs[m] = float(np.mean(x))
        k_models, n = len(cols), len(seeds)
        if k_models < 3 or n < 2:
            notes.append(f"Ranking/{strat}: Friedman não executado (modelos={k_models}, blocos={n}).")
            continue
        names = list(cols)
        mat = np.column_stack([cols[m] for m in names])  # blocks x models
        ranks = np.apply_along_axis(lambda r: sps.rankdata(-r), 1, mat)
        mean_rank = ranks.mean(0)
        try:
            stat, p = sps.friedmanchisquare(*[mat[:, j] for j in range(k_models)])
        except ValueError:
            stat, p = float("nan"), float("nan")
        w = float(stat / (n * (k_models - 1))) if _fin(stat) else float("nan")
        q = float(sps.studentized_range.ppf(1 - cfg["alpha"], k_models, np.inf) / math.sqrt(2))
        cd = q * math.sqrt(k_models * (k_models + 1) / (6.0 * n))
        pairs = [[a, b, float(abs(mean_rank[i] - mean_rank[j]))]
                 for (i, a), (j, b) in combinations(list(enumerate(names)), 2)
                 if abs(mean_rank[i] - mean_rank[j]) > cd]  # fmt: skip
        order = np.argsort(mean_rank)
        out["by_strategy"][strat] = {
            "n_blocks": n, "n_models": k_models,
            "models": [{"model": names[i], "mean_rank": float(mean_rank[i]), "mean_macro_f1": float(mat[:, i].mean()),
                        "sd_macro_f1": float(mat[:, i].std(ddof=1)) if n > 1 else None} for i in order],
            "friedman_statistic": float(stat), "friedman_p": float(p), "kendall_w": w,
            "nemenyi_cd": cd, "nemenyi_q": q, "significant_pairs": pairs, "reference_means": refs,
        }  # fmt: skip
    return out


def _build_bootstrap(preds: _Preds, store: _Store, cfg: dict, seeds: list[int], h1: dict, n_boot: int, seed: int,
                     notes: list[str]) -> dict[str, Any]:  # fmt: skip
    v = cfg["variant_main"]
    models = _primary(cfg)
    sel = {r["seed"]: (r["complex_model"], r["simple_model"]) for r in h1.get("per_seed", [])}
    per_seed, widths, h1_rows = [], {m: [] for m in models}, []
    for s in seeds:
        data = {m: preds.get(v, s, "none", m) for m in models}
        data = {m: d for m, d in data.items() if d is not None}
        if len(data) < 2:
            notes.append(f"Bootstrap: seed {s} sem predições suficientes (estratégia none).")
            continue
        universe = np.unique(np.concatenate([d["subject_id"] for d in data.values()]))
        cms = {m: patient_confusions(d["subject_id"], d["y_true"], d["y_pred"], universe) for m, d in data.items()}
        c, sm = sel.get(s, (None, None))
        contrasts = [(c, sm)] if c in cms and sm in cms else []
        res = cluster_bootstrap_ci(cms, n_boot=n_boot, seed=int(np.random.SeedSequence([seed, s]).generate_state(1)[0]),
                                   alpha=cfg["alpha"], contrasts=contrasts)  # fmt: skip
        entry = {"seed": s, "models": {m: {"point": res["point"][m], "ci_low": res["ci"][m][0], "ci_high": res["ci"][m][1]}
                                       for m in cms}}  # fmt: skip
        for m in cms:
            widths[m].append(res["ci"][m][1] - res["ci"][m][0])
        for cr in res["contrasts"].values():
            hr = {"seed": s, "complex_model": c, "simple_model": sm, "diff": cr["point"], "ci_low": cr["ci"][0],
                  "ci_high": cr["ci"][1], "excludes_zero": bool(cr["ci"][0] > 0 or cr["ci"][1] < 0),
                  "ci_low_gt_delta": bool(cr["ci"][0] > h1["delta"])}  # fmt: skip
            entry["h1_diff"] = hr
            h1_rows.append(hr)
        entry["n_clusters"] = _mask_value(res["n_clusters"])
        per_seed.append(entry)
    return {
        "metric": "macro_f1", "unit": "subject_id (cluster bootstrap)", "variant": v, "strategy": "none",
        "n_boot": n_boot, "alpha": cfg["alpha"], "per_seed": per_seed,
        "summary": {
            "mean_ci_width": {m: (float(np.mean(w)) if w else None) for m, w in widths.items()},
            "h1_n_seeds_ci_excludes_zero": int(sum(r["excludes_zero"] for r in h1_rows)),
            "h1_n_seeds_ci_low_gt_delta": int(sum(r["ci_low_gt_delta"] for r in h1_rows)),
            "h1_n_seeds": len(h1_rows),
        },
        "interpretation": "IC por seed reflete apenas a incerteza de amostragem do conjunto de teste; "
                          "NÃO inclui variabilidade de treino e não é combinado entre seeds.",
    }  # fmt: skip


def _sensitivity(preds: _Preds | None, store: _Store, cfg: dict, seeds: list[int], h1: dict, delta: float,
                 notes: list[str]) -> dict[str, Any]:  # fmt: skip
    va, vb = cfg["variant_main"], cfg["variant_sens"]
    out: dict[str, Any] = {"variant_a": va, "variant_b": vb, "available": False}
    if vb not in store.variants:
        notes.append(f"Sensibilidade: variante {vb} ausente nas métricas.")
        return out
    # own-subset descriptive means (NOT comparable; different test sets)
    own = {}
    for m in _primary(cfg):
        for v in (va, vb):
            x = [store.value(v, m, "none", "test", "macro_f1", s) for s in seeds]
            x = [e for e in x if _fin(e)]
            own.setdefault(m, {})[v] = float(np.mean(x)) if x else None
    out["own_subset_means_none"] = own
    if preds is None:
        notes.append("Sensibilidade B vs A: sem `predictions`; comparação no subconjunto comum NÃO realizada "
                     "(médias de cada variante em seu próprio teste não são comparáveis).")  # fmt: skip
        return out
    models = _models_present(store, cfg, va, ("primary", "extra"))
    cm_common: dict[tuple, np.ndarray] = {}
    rows_seed = []
    rem_acc: dict[int, list[tuple[float, float]]] = {c: [] for c in range(1, 6)}
    for s in seeds:
        removal_done = False
        for strat in cfg["strategies"]:
            for m in models:
                if _is_na(cfg, m, strat):
                    continue
                da, db = preds.get(va, s, strat, m), preds.get(vb, s, strat, m)
                if da is None or db is None:
                    continue
                common = np.intersect1d(da["stay_id"], db["stay_id"])
                ka, kb = np.isin(da["stay_id"], common), np.isin(db["stay_id"], common)
                cma = confusion_matrix_from_labels(da["y_true"][ka], da["y_pred"][ka])
                cmb = confusion_matrix_from_labels(db["y_true"][kb], db["y_pred"][kb])
                cm_common[(va, s, strat, m)], cm_common[(vb, s, strat, m)] = cma, cmb
                ma, mb = metrics_from_confusion(cma), metrics_from_confusion(cmb)
                rows_seed.append({"seed": s, "model": m, "strategy": strat,
                                  **{f"{k}_{t}": float(mm[k]) for t, mm in (("a", ma), ("b", mb))
                                     for k in ("macro_f1", "balanced_accuracy", "qwk")},
                                  "n_common": int(len(common))})  # fmt: skip
                if not removal_done and strat == "none":
                    for c in range(1, 6):
                        ta = int((da["y_true"] == c).sum())
                        kept = int((da["y_true"][ka] == c).sum())
                        rem_acc[c].append((ta, ta - kept))
                    removal_done = True
    if not rows_seed:
        notes.append("Sensibilidade: nenhuma interseção A/B encontrada nas predições.")
        return out
    out["available"] = True
    out["subset_rule"] = "estadias de teste presentes em A e em B (interseção por stay_id), por seed"
    # per model x strategy: paired differences B - A on the common subset
    agg = []
    df = pd.DataFrame(rows_seed)
    for (m, strat), g in df.groupby(["model", "strategy"], sort=False):
        g = g.sort_values("seed")
        for metric in ("macro_f1", "balanced_accuracy", "qwk"):
            d = (g[f"{metric}_b"] - g[f"{metric}_a"]).to_numpy(float)
            c = corrected_resampled_ttest(d, cfg["train_frac"], cfg["test_frac"], cfg["alpha"])
            agg.append({"model": m, "strategy": strat, "metric": metric, "n_seeds": int(len(d)),
                        "mean_a_common": float(g[f"{metric}_a"].mean()), "mean_b_common": float(g[f"{metric}_b"].mean()),
                        "mean_diff_b_minus_a": c["mean"], "ci_low": c["ci_low"], "ci_high": c["ci_high"], "p": c["p"],
                        "dz": c["dz"]})  # fmt: skip
    out["rows"] = agg
    # H1 re-evaluated on the common subset, selection by each variant's own validation
    h1c: dict[str, Any] = {}
    for v in (va, vb):
        diffs = []
        for s in seeds:
            ms, _ = _select_best(store, v, cfg["simple_models"], "none", s)
            mc, _ = _select_best(store, v, cfg["complex_models"], "none", s)
            ca, cs = cm_common.get((v, s, "none", mc)), cm_common.get((v, s, "none", ms))
            if ca is not None and cs is not None:
                diffs.append(float(metrics_from_confusion(ca)["macro_f1"] - metrics_from_confusion(cs)["macro_f1"]))
        d = np.array(diffs, dtype=float)
        c = corrected_resampled_ttest(d, cfg["train_frac"], cfg["test_frac"], cfg["alpha"])
        h1c[v] = {"n_seeds": len(d), "mean_diff": c["mean"], "ci_low": c["ci_low"], "ci_high": c["ci_high"], "p": c["p"],
                  **_verdict(c, d[np.isfinite(d)], delta)}  # fmt: skip
    out["h1_on_common_subset"] = h1c
    removal = {}
    for c, vals in rem_acc.items():
        if not vals:
            continue
        tot = float(np.mean([a for a, _ in vals]))
        rem = float(np.mean([b for _, b in vals]))
        removal[str(c)] = {"n_test_a_mean_per_seed": _mask_value(tot), "n_removed_mean_per_seed": _mask_value(rem),
                           "fraction_removed": (rem / tot) if tot > 0 else None}  # fmt: skip
    out["removal_by_class"] = removal
    return out


def _anomalies(store: _Store, cfg: dict, seeds: list[int], variants: list[str]) -> list[dict[str, Any]]:
    an: list[dict[str, Any]] = []
    thr = cfg["anomaly"]
    expected = list(range(1, int(cfg["expected_seeds"]) + 1))
    for v in variants:
        if v not in store.variants:
            continue
        for m in _primary(cfg) + list(cfg["extra_models"]) + list(cfg["reference_models"]):
            for st in cfg["strategies"]:
                if _is_na(cfg, m, st):
                    continue
                miss = {}
                for sp in ("val", "test"):
                    ser = store.get(v, m, st, sp, "macro_f1")
                    ms = [s for s in expected if not (s in ser.index and _fin(ser[s]))]
                    if ms:
                        miss[sp] = ms
                if miss:
                    kind = "primary" if m in _primary(cfg) else ("extra" if m in cfg["extra_models"] else "reference")
                    an.append({"type": "ausente_ou_falha", "variant": v, "model": m, "strategy": st, "kind": kind,
                               "detail": f"Macro-F1 ausente/não finito (seeds): {miss}"})  # fmt: skip
    v = cfg["variant_main"]
    if v in store.variants and seeds:
        dummy_means = {}
        for st in cfg["strategies"]:
            ds = []
            for dm in cfg["reference_models"]:
                s = store.get(v, dm, "none", "test", "macro_f1")
                x = [s[k] for k in seeds if k in s.index and _fin(s[k])]
                if x:
                    ds.append(float(np.mean(x)))
            dummy_means[st] = max(ds) if ds else None
        for m in _primary(cfg) + list(cfg["extra_models"]):
            for st in cfg["strategies"]:
                if _is_na(cfg, m, st):
                    continue
                t = store.get(v, m, st, "test", "macro_f1")
                x = np.array([t[k] for k in seeds if k in t.index and _fin(t[k])], dtype=float)
                if len(x) == 0:
                    continue
                ref = dummy_means.get("none")
                if ref is not None and x.mean() < ref - thr["below_dummy_margin"]:
                    an.append({"type": "abaixo_do_dummy", "variant": v, "model": m, "strategy": st,
                               "detail": f"Macro-F1 médio de teste {x.mean():.4f} < dummy {ref:.4f}"})  # fmt: skip
                if len(x) > 1 and x.std(ddof=1) > thr["seed_sd_macro_f1"]:
                    an.append({"type": "variancia_alta_entre_seeds", "variant": v, "model": m, "strategy": st,
                               "detail": f"DP entre seeds {x.std(ddof=1):.4f} > {thr['seed_sd_macro_f1']}"})  # fmt: skip
                val = store.get(v, m, st, "val", "macro_f1")
                gap = [val[k] - t[k] for k in seeds if k in val.index and k in t.index and _fin(val[k]) and _fin(t[k])]
                if gap and abs(float(np.mean(gap))) > thr["val_test_gap"]:
                    an.append({"type": "gap_validacao_teste", "variant": v, "model": m, "strategy": st,
                               "detail": f"Macro-F1 val - teste = {np.mean(gap):+.4f}"})  # fmt: skip
                for c in range(1, 6):
                    r = store.get(v, m, st, "test", f"recall_{c}")
                    nz = [k for k in seeds if k in r.index and _fin(r[k]) and r[k] == 0.0]
                    if nz:
                        an.append({"type": "classe_com_recall_zero", "variant": v, "model": m, "strategy": st,
                                   "detail": f"recall_{c} = 0 em {len(nz)} de {len(seeds)} seeds"})  # fmt: skip
    return an


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------
def run_preregistered_analysis(
    metrics: pd.DataFrame,
    predictions: pd.DataFrame | None,
    cfg: dict | None = None,
    *,
    delta: float = 0.01,
    n_boot: int = 1000,
    seed: int = 0,
) -> dict:
    """Run the pre-registered analysis (see ``docs/analysis_plan.md``).

    Returns a JSON-serialisable dict with stable keys: ``seeds_used, h1, h2, h3, ranking,
    sensitivity_b_vs_a, bootstrap_ci, anomalies, notes`` (plus ``meta`` and ``seed_selection``).
    Incomplete data never raise: gaps are reported in ``notes``/``anomalies``.  Schema errors
    (missing columns) do raise ``ValueError``.
    """
    cfg = _merge(DEFAULT_CFG, cfg)
    notes: list[str] = []
    miss = [c for c in REQUIRED_METRIC_COLS if c not in metrics.columns]
    if miss:
        raise ValueError(f"metrics sem colunas obrigatórias: {miss}")
    m = metrics[REQUIRED_METRIC_COLS + [c for c in ("model_kind", "model_group") if c in metrics.columns]].copy()
    m["seed"] = m["seed"].astype(int)
    m["value"] = pd.to_numeric(m["value"], errors="coerce")
    for c in ("variant", "model", "strategy", "split", "metric"):
        m[c] = m[c].astype(str)
    store = _Store(m)
    if store.n_duplicates:
        notes.append(f"{store.n_duplicates} linhas duplicadas em (variant, model, strategy, split, metric, seed): mantida a última.")
    if store.n_nonfinite:
        notes.append(f"{store.n_nonfinite} valores de métrica não finitos (NaN/inf) tratados como ausentes.")

    results: dict[str, Any] = {
        "meta": {"delta": delta, "n_boot": n_boot, "bootstrap_seed": seed, "alpha": cfg["alpha"],
                 "variant_main": cfg["variant_main"], "variant_sens": cfg["variant_sens"],
                 "train_frac": cfg["train_frac"], "test_frac": cfg["test_frac"],
                 "predictions_available": predictions is not None},
        "seeds_used": [], "seed_selection": {}, "h1": {}, "h2": {}, "h3": {}, "ranking": {},
        "sensitivity_b_vs_a": {}, "bootstrap_ci": {}, "anomalies": [], "notes": notes,
    }  # fmt: skip

    def guarded(name: str, fn):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - recorded loudly, never silent
            notes.append(f"ERRO na seção '{name}': {type(exc).__name__}: {exc}")
            return {}

    variants = [cfg["variant_main"], cfg["variant_sens"]]
    sel = select_seeds(store, cfg) if cfg["variant_main"] in store.variants else None
    if sel is None:
        notes.append(f"Variante principal {cfg['variant_main']} ausente: análise principal não executada.")
        results["anomalies"] = []
        return _clean(results)
    seeds = sel["used"]
    results["seeds_used"] = seeds
    results["seed_selection"] = sel
    extra_seeds = sorted({int(s) for s in m["seed"].unique()} - set(seeds))
    if extra_seeds:
        notes.append(f"Seeds presentes mas fora da análise principal (regra de corte): {extra_seeds}.")
    notes.append(f"Regra de corte de seeds: {sel['rule']}.")
    if len(seeds) < int(cfg["expected_seeds"]):
        notes.append(f"Análise com {len(seeds)} < {cfg['expected_seeds']} seeds: poder e precisão do IC reduzidos.")
    results["anomalies"] = guarded("anomalias", lambda: _anomalies(store, cfg, seeds, variants)) or []
    n_ref = store.get(cfg["variant_main"], "logreg", "none", "test", "n")
    if len(n_ref):
        results["meta"]["n_test_stays_mean"] = _mask_value(float(np.nanmean(n_ref.to_numpy())))
    if not seeds:
        return _clean(results)

    v = cfg["variant_main"]
    results["h1"] = guarded("h1", lambda: _h1(store, cfg, seeds, delta, v))
    if cfg["variant_sens"] in store.variants and results["h1"]:
        vb = cfg["variant_sens"]
        ok_b = all(_fin(store.value(vb, mm, "none", sp, "macro_f1", s))
                   for mm in _primary(cfg) for s in seeds for sp in ("val", "test"))  # fmt: skip
        if ok_b:
            results["h1"]["variant_b_descriptive"] = guarded("h1_b", lambda: _h1(store, cfg, seeds, delta, vb))
        else:
            notes.append("H1 descritiva na variante B não calculada: seeds/modelos incompletos em B.")
    results["h2"] = guarded("h2", lambda: _h2(store, cfg, seeds))
    results["h3"] = guarded("h3", lambda: _h3(store, cfg, seeds))
    results["ranking"] = guarded("ranking", lambda: _ranking(store, cfg, seeds, notes))
    preds = None
    if predictions is not None:
        pm = [c for c in REQUIRED_PRED_COLS if c not in predictions.columns]
        if pm:
            notes.append(f"`predictions` sem colunas {pm}: bootstrap e sensibilidade não executados.")
        else:
            preds = _Preds(predictions)
    else:
        notes.append("Sem `predictions`: IC por bootstrap de pacientes e comparação B vs A no subconjunto comum não executados.")
    results["sensitivity_b_vs_a"] = guarded("sensibilidade", lambda: _sensitivity(preds, store, cfg, seeds, results["h1"], delta, notes))
    if preds is not None and n_boot > 0 and results["h1"]:
        results["bootstrap_ci"] = guarded("bootstrap", lambda: _build_bootstrap(preds, store, cfg, seeds, results["h1"], n_boot, seed, notes))
    return _clean(results)


# --------------------------------------------------------------------------------------
# Markdown rendering (Portuguese; tables only)
# --------------------------------------------------------------------------------------
def _f(x: Any, d: int = 4, signed: bool = False) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    s = f"{x:+.{d}f}" if signed else f"{x:.{d}f}"
    return s.replace(".", ",")


def _p(x: Any) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    return "<0,001" if x < 0.001 else f"{x:.3f}".replace(".", ",")


def _ci(lo: Any, hi: Any, d: int = 4) -> str:
    return f"[{_f(lo, d, True)}; {_f(hi, d, True)}]"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_(sem linhas)_\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def _cnt(x: Any) -> str:
    return mask_count(x) if not isinstance(x, str) else x


def render_stats_markdown(results: dict) -> str:
    """Markdown tables (pt-BR) for ``summary.md``.  Counts of 1..10 are masked as '<11'."""
    L: list[str] = ["## Análise estatística pré-registrada\n"]
    meta = results.get("meta", {})
    seeds = results.get("seeds_used", [])
    sel = results.get("seed_selection", {})
    L.append("### Seeds utilizadas\n")
    L.append(_table(["Seeds usadas", "Nº de seeds", "Regra aplicada", "Estadias de teste por seed (média)"],
                    [[", ".join(map(str, seeds)) or "—", str(len(seeds)), str(sel.get("rule", "—")),
                      _cnt(meta.get("n_test_stays_mean"))]]))  # fmt: skip

    h1 = results.get("h1") or {}
    L.append("### H1 — complexo vs. simples (Macro-F1 de teste, estratégia none, variante A)\n")
    if h1:
        L.append(_table(["Seed", "Simples (val)", "Complexo (val)", "F1 teste simples", "F1 teste complexo", "Δ"],
                        [[str(r["seed"]), str(r["simple_model"]), str(r["complex_model"]), _f(r["test_simple"]),
                          _f(r["test_complex"]), _f(r["diff"], 4, True)] for r in h1.get("per_seed", [])]))  # fmt: skip
        c, nv = h1.get("corrected", {}), h1.get("naive") or {}
        L.append(_table(
            ["Δ médio", "DP(Δ)", "dz", "IC95% (Nadeau–Bengio)", "p (corrigido)", "IC95% ingênuo (só comparação)",
             "Δ>0 em todas as seeds", f"LI > δ={_f(h1.get('delta'), 3)}", "Veredito"],
            [[_f(h1.get("mean_diff"), 4, True), _f(h1.get("sd_diff")), _f(h1.get("dz"), 2),
              _ci(c.get("ci_low"), c.get("ci_high")), _p(c.get("p")), _ci(nv.get("ci_low"), nv.get("ci_high")),
              "sim" if h1.get("all_positive") else "não", "sim" if h1.get("ci_lower_gt_delta") else "não",
              str(h1.get("verdict_label"))]]))  # fmt: skip
        rb = h1.get("robustness_fixed_models")
        if rb:
            L.append(f"Robustez (modelo fixo por grupo, escolhido pela F1 de validação média): simples={rb['simple']}, "
                     f"complexo={rb['complex']}, Δ médio={_f(rb['mean_diff'], 4, True)}, "
                     f"IC95% {_ci(rb['ci_low'], rb['ci_high'])}, veredito: {rb['verdict_label']}.\n")  # fmt: skip
        hb = h1.get("variant_b_descriptive")
        if hb:
            L.append(f"Descritivo na variante B: Δ médio={_f(hb['mean_diff'], 4, True)}, "
                     f"IC95% {_ci(hb['corrected']['ci_low'], hb['corrected']['ci_high'])}, veredito: {hb['verdict_label']}.\n")  # fmt: skip

    h2 = results.get("h2") or {}
    L.append("### H2 — estratégias de desbalanceamento vs. none (diferença pareada por seed)\n")
    if h2:
        rows = [[r["model"], r["strategy"], r["metric"], str(r["n_pairs"]), _f(r["mean_diff"], 4, True),
                 _ci(r["ci_low"], r["ci_high"]), _f(r["dz"], 2), _p(r["p"]),
                 _p(r["p_holm"]) if r["p_holm"] is not None else "—",
                 "confirmatória" if r["confirmatory"] else "descritiva"] for r in h2.get("rows", [])]  # fmt: skip
        L.append(_table(["Modelo", "Estratégia", "Métrica", "Pares", "Δ médio", "IC95% (N–B)", "dz", "p", "p Holm", "Papel"], rows))
        L.append(_table(["Modelo", "Estratégia", "H2 suportada"],
                        [[s["model"], s["strategy"], {True: "sim", False: "não", None: "n/d"}[s["supported"]]]
                         for s in h2.get("summary", [])]))  # fmt: skip

    h3 = results.get("h3") or {}
    L.append("### H3 — erros adjacentes e sub/sobretriagem (média entre seeds)\n")
    if h3:
        L.append(_table(["Modelo", "Estratégia", "Erros adjacentes", "Erros com distância ≥ 2", "Subtriagem",
                         "Sobretriagem", "Subtriagem grave", "Adjacentes > 50% em todas as seeds"],
                        [[r["model"], r["strategy"], _f(r["adjacent_error_share"]), _f(r["distant_error_share"]),
                          _f(r["under_triage_rate"]), _f(r["over_triage_rate"]), _f(r["severe_under_triage_rate"]),
                          "sim" if r["adjacent_majority_all_seeds"] else "não"] for r in h3.get("rows", [])]))  # fmt: skip

    rk = results.get("ranking") or {}
    L.append("### Ranking descritivo (Friedman com seeds como blocos, Nemenyi)\n")
    if rk:
        L.append(f"_{rk.get('warning', '')}_\n")
        for st, r in rk.get("by_strategy", {}).items():
            L.append(f"**Estratégia {st}** — Friedman χ²={_f(r['friedman_statistic'], 2)}, p={_p(r['friedman_p'])}, "
                     f"Kendall W={_f(r['kendall_w'], 3)}, DC de Nemenyi={_f(r['nemenyi_cd'], 2)} "
                     f"({r['n_models']} modelos, {r['n_blocks']} blocos).\n")  # fmt: skip
            L.append(_table(["Modelo", "Posto médio", "Macro-F1 médio", "DP entre seeds"],
                            [[x["model"], _f(x["mean_rank"], 2), _f(x["mean_macro_f1"]), _f(x["sd_macro_f1"])]
                             for x in r["models"]]))  # fmt: skip
            if r.get("reference_means"):
                L.append("Referências (Macro-F1 médio): "
                         + "; ".join(f"{k}={_f(v)}" for k, v in r["reference_means"].items()) + ".\n")  # fmt: skip

    sb = results.get("sensitivity_b_vs_a") or {}
    L.append("### Sensibilidade B vs. A (mesmo subconjunto de teste)\n")
    if sb.get("available"):
        L.append(f"Regra do subconjunto: {sb['subset_rule']}.\n")
        L.append(_table(["Modelo", "Estratégia", "Métrica", "A (comum)", "B (comum)", "Δ B−A", "IC95% (N–B)", "p"],
                        [[r["model"], r["strategy"], r["metric"], _f(r["mean_a_common"]), _f(r["mean_b_common"]),
                          _f(r["mean_diff_b_minus_a"], 4, True), _ci(r["ci_low"], r["ci_high"]), _p(r["p"])]
                         for r in sb.get("rows", []) if r["metric"] == "macro_f1"]))  # fmt: skip
        hc = sb.get("h1_on_common_subset", {})
        L.append(_table(["Seleção feita na variante", "Δ médio (complexo−simples)", "IC95% (N–B)", "Veredito (descritivo)"],
                        [[k, _f(x["mean_diff"], 4, True), _ci(x["ci_low"], x["ci_high"]), x["verdict_label"]]
                         for k, x in hc.items()]))  # fmt: skip
        L.append(_table(["Classe", "Teste A (média/seed)", "Removidas em B (média/seed)", "Fração removida"],
                        [[k, _cnt(x["n_test_a_mean_per_seed"]), _cnt(x["n_removed_mean_per_seed"]),
                          _f(x["fraction_removed"], 3)] for k, x in sb.get("removal_by_class", {}).items()]))  # fmt: skip
    else:
        L.append("_Comparação no subconjunto comum não disponível (ver notas)._\n")

    bs = results.get("bootstrap_ci") or {}
    L.append("### IC por bootstrap de pacientes (Macro-F1 de teste, estratégia none, variante A)\n")
    if bs:
        L.append(f"B = {bs['n_boot']} reamostragens; {bs['interpretation']}\n")
        s = bs["summary"]
        L.append(f"Diferença H1 por seed: IC exclui zero em {s['h1_n_seeds_ci_excludes_zero']} de {s['h1_n_seeds']} seeds; "
                 f"limite inferior > δ em {s['h1_n_seeds_ci_low_gt_delta']} de {s['h1_n_seeds']}.\n")  # fmt: skip
        L.append(_table(["Seed", "Complexo", "Simples", "Δ", "IC95% de Δ (bootstrap)"],
                        [[str(e["seed"]), str(e["h1_diff"]["complex_model"]), str(e["h1_diff"]["simple_model"]),
                          _f(e["h1_diff"]["diff"], 4, True), _ci(e["h1_diff"]["ci_low"], e["h1_diff"]["ci_high"])]
                         for e in bs.get("per_seed", []) if "h1_diff" in e]))  # fmt: skip
        L.append(_table(["Modelo", "Largura média do IC95% (por seed)"],
                        [[k, _f(x)] for k, x in s["mean_ci_width"].items()]))  # fmt: skip
    else:
        L.append("_Bootstrap não executado (ver notas)._\n")

    L.append("### Anomalias sinalizadas\n")
    an = results.get("anomalies", [])
    L.append(_table(["Tipo", "Variante", "Modelo", "Estratégia", "Detalhe"],
                    [[a["type"], a["variant"], a["model"], a["strategy"], a["detail"]] for a in an]) if an
             else "Nenhuma anomalia sinalizada.\n")  # fmt: skip
    L.append("### Notas\n")
    L.append("\n".join(f"- {n}" for n in results.get("notes", [])) + "\n" if results.get("notes") else "Sem notas.\n")
    return "\n".join(L)
