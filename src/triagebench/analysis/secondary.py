"""Secondary analyses pre-registered as amendments on 05/11 (DESCRIPTIVE, never replace the primary).

1. Alternative decodings from the saved test probabilities (no new HPO): posterior median (Bayes-
   optimal for MAE) and argmax p_k/pi_k (Bayes-optimal for balanced accuracy). For models trained
   with class weights/oversampling the balanced prior is undone first: p ~ p_tilde * pi.
2. H1 with the strategy chosen on VALIDATION per model and seed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from triagebench.evaluation.metrics import compute_metrics
from triagebench.reporting.tables import md_table
from triagebench.utils.io import read_json

DEC_METRICS = ("macro_f1", "balanced_accuracy", "qwk", "mae_ordinal")


def _median_decode(p: np.ndarray) -> np.ndarray:
    return (np.cumsum(p, axis=1) >= 0.5).argmax(axis=1) + 1


def decodings(cdir: Path, variant: str, *, eligible_tasks: set[tuple] | None = None) -> pd.DataFrame:
    rows = []
    for d in sorted((Path(cdir) / "tasks").glob(f"{variant}__s*")):
        _, seed, model, strategy = d.name.split("__")
        if eligible_tasks is not None and (variant, int(seed.lstrip("s")), model, strategy) not in eligible_tasks:
            continue
        path = d / "private" / "predictions.parquet"
        if not (d / "DONE").exists() or not path.exists():
            continue
        pred = pd.read_parquet(path)
        pcols = [f"proba_{k}" for k in range(1, 6)]
        if not set(pcols) <= set(pred.columns):
            continue
        test = pred[pred["partition"] == "test"]
        res = read_json(d / "result.json")
        counts = np.array([res["data"]["train_class_counts"][str(k)] for k in range(1, 6)], dtype=float)
        if not np.isfinite(counts).all() or not (counts > 0).all():
            raise ValueError("Alternative decodings require finite positive training class counts")
        prior = counts / counts.sum()
        p = test[pcols].to_numpy(dtype=float)
        if not np.isfinite(p).all() or (p < 0).any() or not (p.sum(axis=1) > 0).all():
            raise ValueError("Alternative decodings require finite nonnegative probabilities with positive row sums")
        p = p / p.sum(axis=1, keepdims=True)
        strategy = res["task"]["strategy"]
        if strategy != "none":  # undo the balanced training prior
            p = p * prior
            p = p / p.sum(axis=1, keepdims=True)
        y = test["y_true"].to_numpy(dtype=int)
        decoded = {"argmax": p.argmax(axis=1) + 1, "median": _median_decode(p), "argmax_p_over_prior": (p / prior).argmax(axis=1) + 1}
        for name, yhat in decoded.items():
            m = compute_metrics(y, yhat)
            rows.append({"variant": variant, "model": res["task"]["model"], "strategy": strategy, "seed": res["task"]["seed"],
                         "decoding": name, **{k: m[k] for k in DEC_METRICS}})
    return pd.DataFrame(rows)


def decodings_markdown(df: pd.DataFrame, order: list[str]) -> str:
    if df.empty:
        return "_sem probabilidades salvas_"
    g = df.groupby(["model", "strategy", "decoding"])[list(DEC_METRICS)].mean().reset_index()
    rows = []
    for m in [x for x in order if x in set(g.model)]:
        for s in ("none", "class_weight", "oversample"):
            sub = g[(g.model == m) & (g.strategy == s)]
            if sub.empty:
                continue
            for dec in ("argmax", "median", "argmax_p_over_prior"):
                r = sub[sub.decoding == dec]
                if not r.empty:
                    r = r.iloc[0]
                    rows.append([m, s, dec] + [f"{r[k]:.4f}" for k in DEC_METRICS])
    note = ("Probabilidades de modelos treinados com class_weight/oversample têm o prior balanceado desfeito "
            "antes de decodificar; `argmax` dessas difere da predição original. SVM sem probabilidades: ausente.\n\n")
    return note + md_table(["modelo", "estratégia", "decodificação", *DEC_METRICS], rows)


def h1_validation_selected_strategy(metrics: pd.DataFrame, cfg: dict, variant: str, delta: float = 0.01,
                                    *, seeds: list[int] | None = None) -> dict:
    from triagebench.analysis.stats import (
        DEFAULT_CFG,
        _fin,
        _is_na,
        _merge,
        _Store,
        corrected_resampled_ttest,
        select_seeds,
    )

    groups = cfg["models"].get("groups") or {}
    settings = _merge(DEFAULT_CFG, {
        "variant_main": variant, "simple_models": groups.get("simple", []),
        "complex_models": groups.get("complex", []),
        "strategies": list(cfg["imbalance"]["strategies"]),
        "expected_seeds": len(cfg["split"]["seeds"]), "min_seeds": min(5, len(cfg["split"]["seeds"])),
    })
    m = metrics[(metrics.variant == variant) & (metrics.metric == "macro_f1")]
    store = _Store(m)
    if seeds is None:
        seeds = select_seeds(store, settings)["used"]
    rows, missing = [], []
    for seed in seeds:
        absent = [f"{model}/{strategy}/{split}" for model in groups.get("simple", []) + groups.get("complex", [])
                  for strategy in settings["strategies"] if not _is_na(settings, model, strategy)
                  for split in ("val", "test")
                  if not _fin(store.value(variant, model, strategy, split, "macro_f1", seed))]
        if absent:
            missing.append({"seed": seed, "cells": absent})
            continue
        best = {}
        for group in ("simple", "complex"):
            # Model and strategy configuration order give deterministic validation ties.
            candidates = [(model, strategy) for model in groups.get(group, [])
                          for strategy in settings["strategies"] if not _is_na(settings, model, strategy)]
            if not candidates:
                continue
            model, strategy = max(candidates, key=lambda pair: store.value(
                variant, pair[0], pair[1], "val", "macro_f1", seed))
            best[group] = (model, strategy, store.value(variant, model, strategy, "test", "macro_f1", seed))
        if len(best) == 2:
            simple, complex_ = best["simple"], best["complex"]
            rows.append({"seed": int(seed), "simple": f"{simple[0]}/{simple[1]}",
                         "complex": f"{complex_[0]}/{complex_[1]}", "delta": float(complex_[2] - simple[2])})
    diffs = [r["delta"] for r in rows]
    fr = cfg["split"]["fractions"]
    t = corrected_resampled_ttest(diffs, fr["train"], fr["test"]) if len(diffs) >= 2 else {}
    consistent = bool(diffs) and all(d > 0 for d in diffs) and t.get("ci_low", float("nan")) > delta
    return {"per_seed": rows, "test": t, "consistent": consistent, "delta": delta,
            "seeds_selected": list(seeds), "missing_cells": missing, "role": "descriptive"}


def h1_secondary_markdown(res: dict) -> str:
    if not res.get("per_seed"):
        return "_dados insuficientes_"
    rows = [[r["seed"], r["simple"], r["complex"], f"{r['delta']:+.4f}"] for r in res["per_seed"]]
    t = res["test"]
    head = (f"Δ médio = {t.get('mean', float('nan')):+.4f}, IC95% (t corrigido) = [{t.get('ci_low', float('nan')):+.4f}; "
            f"{t.get('ci_high', float('nan')):+.4f}], p = {t.get('p', float('nan')):.4g}; critério H1 (Δ>0 em todas e "
            f"IC inferior > {res['delta']}): **{'consistente' if res['consistent'] else 'sem superioridade consistente'}** "
            "(descritivo).\n\n")
    return head + md_table(["seed", "melhor simples (val)", "melhor complexo (val)", "Δ Macro-F1 teste"], rows)
