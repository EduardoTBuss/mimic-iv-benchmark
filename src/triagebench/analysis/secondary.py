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


def decodings(cdir: Path, variant: str) -> pd.DataFrame:
    rows = []
    for d in sorted((Path(cdir) / "tasks").glob(f"{variant}__s*")):
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
        prior = counts / counts.sum()
        p = test[pcols].to_numpy(dtype=float)
        p = p / p.sum(axis=1, keepdims=True)
        strategy = res["task"]["strategy"]
        if strategy != "none":  # undo the balanced training prior
            p = p * prior
            p = p / p.sum(axis=1, keepdims=True)
        y = test["y_true"].to_numpy(dtype=int)
        decoded = {"argmax": p.argmax(axis=1) + 1, "median": _median_decode(p), "argmax_p_over_prior": (p / prior).argmax(axis=1) + 1}
        for name, yhat in decoded.items():
            m = compute_metrics(y, yhat)
            rows.append({"model": res["task"]["model"], "strategy": strategy, "seed": res["task"]["seed"],
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


def h1_validation_selected_strategy(metrics: pd.DataFrame, cfg: dict, variant: str, delta: float = 0.01) -> dict:
    from triagebench.analysis.stats import corrected_resampled_ttest

    groups = cfg["models"].get("groups") or {}
    m = metrics[(metrics.variant == variant) & (metrics.metric == "macro_f1")]
    piv = m.pivot_table(index=["seed", "model", "strategy"], columns="split", values="value").reset_index()
    rows = []
    for seed, sub in piv.groupby("seed"):
        best = {}
        for group in ("simple", "complex"):
            cand = sub[sub.model.isin(groups.get(group, []))].dropna(subset=["val", "test"])
            if cand.empty:
                break
            # per model: strategy with the best validation macro-F1; then best model of the group by validation
            per_model = cand.loc[cand.groupby("model")["val"].idxmax()]
            pick = per_model.loc[per_model["val"].idxmax()]
            best[group] = pick
        if len(best) == 2:
            rows.append({"seed": int(seed), "simple": f"{best['simple'].model}/{best['simple'].strategy}",
                         "complex": f"{best['complex'].model}/{best['complex'].strategy}",
                         "delta": float(best["complex"].test - best["simple"].test)})
    diffs = [r["delta"] for r in rows]
    fr = cfg["split"]["fractions"]
    t = corrected_resampled_ttest(diffs, fr["train"], fr["test"]) if len(diffs) >= 2 else {}
    consistent = bool(diffs) and all(d > 0 for d in diffs) and t.get("ci_low", float("nan")) > delta
    return {"per_seed": rows, "test": t, "consistent": consistent, "delta": delta}


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
