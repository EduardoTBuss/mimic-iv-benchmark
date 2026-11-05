"""Result figures (diagnostic, not publication styling). Small cells (1..10) are never drawn."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from triagebench.reporting.disclosure import mask_matrix  # noqa: E402


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def fig_metric_box(metrics: pd.DataFrame, variant: str, metric: str, order: list[str], path: Path) -> Path | None:
    d = metrics[(metrics.variant == variant) & (metrics.split == "test") & (metrics.strategy == "none") & (metrics.metric == metric)]
    models = [m for m in order if m in set(d.model)]
    if not models:
        return None
    fig, ax = plt.subplots(figsize=(1.0 + 0.7 * len(models), 4))
    ax.boxplot([d[d.model == m].value.to_numpy() for m in models], tick_labels=models, showmeans=True)
    ax.set_ylabel(f"{metric} (test, one point per seed)")
    ax.set_title(f"{variant} | strategy none")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(alpha=0.3)
    return _save(fig, path)


def fig_strategy_effect(metrics: pd.DataFrame, variant: str, metric: str, order: list[str], strategies: list[str],
                        path: Path) -> Path | None:
    d = metrics[(metrics.variant == variant) & (metrics.split == "test") & (metrics.metric == metric)]
    models = [m for m in order if m in set(d.model)]
    if not models:
        return None
    width = 0.8 / len(strategies)
    fig, ax = plt.subplots(figsize=(1.0 + 0.8 * len(models), 4))
    x = np.arange(len(models))
    for i, s in enumerate(strategies):
        means = [d[(d.model == m) & (d.strategy == s)].value.mean() for m in models]
        ax.bar(x + i * width, means, width, label=s)
    ax.set_xticks(x + width * (len(strategies) - 1) / 2, models, rotation=45)
    ax.set_ylabel(f"mean {metric} (test)")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")
    return _save(fig, path)


def fig_confusion(counts: np.ndarray, title: str, path: Path, k: int = 11) -> Path:
    masked = mask_matrix(counts, k)
    row = np.nansum(np.asarray(counts, float), axis=1, keepdims=True)
    share = np.divide(masked, row, out=np.full_like(masked, np.nan), where=row > 0)
    fig, ax = plt.subplots(figsize=(4.6, 4))
    im = ax.imshow(share, vmin=0, vmax=1, cmap="Blues")
    for i in range(share.shape[0]):
        for j in range(share.shape[1]):
            ax.text(j, i, "<11" if np.isnan(masked[i, j]) else f"{share[i, j]:.2f}", ha="center", va="center", fontsize=8)
    ax.set_xticks(range(5), [str(i) for i in range(1, 6)])
    ax.set_yticks(range(5), [str(i) for i in range(1, 6)])
    ax.set_xlabel("predicted acuity")
    ax.set_ylabel("recorded acuity")
    ax.set_title(title, fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.046)
    return _save(fig, path)


def fig_error_distance(abs_error: pd.DataFrame, variant: str, order: list[str], path: Path, k: int = 11) -> Path | None:
    d = abs_error[(abs_error.variant == variant) & (abs_error.split == "test") & (abs_error.strategy == "none")]
    models = [m for m in order if m in set(d.model)]
    if not models:
        return None
    fig, ax = plt.subplots(figsize=(1.0 + 0.7 * len(models), 4))
    bottom = np.zeros(len(models))
    for dist in range(1, 5):
        vals = []
        for m in models:
            sub = d[d.model == m]
            errors = sub[sub.distance > 0]["count"].sum()
            c = sub[sub.distance == dist]["count"].sum()
            vals.append(0.0 if errors == 0 or 0 < c < k else c / errors)
        ax.bar(models, vals, bottom=bottom, label=f"|error| = {dist}")
        bottom += np.array(vals)
    ax.set_ylabel("share of errors (test, all seeds)")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(fontsize=8)
    return _save(fig, path)
