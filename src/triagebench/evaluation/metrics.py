"""Nominal and ordinal metrics for acuity (1 = most urgent ... 5).

Ordinal conventions: d = y_pred - y_true. d > 0 means the prediction is LESS urgent than the
recorded label (under-triage); d < 0 means more urgent (over-triage). Descriptive only: no
clinical-safety claim is attached to these rates.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)

LABELS = (1, 2, 3, 4, 5)


def compute_metrics(y_true, y_pred, labels: tuple[int, ...] = LABELS) -> dict:
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    labels = list(labels)
    n = int(y_true.size)
    if n == 0:
        nan = float("nan")
        out = {"n": 0, **{k: nan for k in ("accuracy", "balanced_accuracy", "macro_f1", "weighted_f1", "qwk",
                                            "mae_ordinal", "under_triage_rate", "over_triage_rate",
                                            "severe_under_triage_rate", "under_triage_rate_urgent",
                                            "adjacent_error_share")}}
        for lab in labels:
            out.update({f"precision_{lab}": nan, f"recall_{lab}": nan, f"f1_{lab}": nan,
                        f"support_{lab}": 0, f"predicted_{lab}": 0})
        out["confusion"] = [[0] * len(labels) for _ in labels]
        out["abs_error_counts"] = {str(k): 0 for k in range(len(labels))}
        return out
    d = y_pred - y_true
    errors = d != 0
    prec, rec, f1, sup = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    pred_counts = np.array([(y_pred == lab).sum() for lab in labels])
    out: dict = {
        "n": n,
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)) if n else float("nan"),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0)),
        "qwk": float(cohen_kappa_score(y_true, y_pred, labels=labels, weights="quadratic")),
        "mae_ordinal": float(np.abs(d).mean()) if n else float("nan"),
        "under_triage_rate": float((d > 0).mean()) if n else float("nan"),
        "over_triage_rate": float((d < 0).mean()) if n else float("nan"),
        "severe_under_triage_rate": float((d >= 2).mean()) if n else float("nan"),
        "under_triage_rate_urgent": float((d[y_true <= 2] > 0).mean()) if (y_true <= 2).any() else float("nan"),
        "adjacent_error_share": float((np.abs(d) == 1).sum() / errors.sum()) if errors.any() else float("nan"),
    }
    for i, lab in enumerate(labels):
        out[f"precision_{lab}"] = float(prec[i])
        out[f"recall_{lab}"] = float(rec[i])
        out[f"f1_{lab}"] = float(f1[i])
        out[f"support_{lab}"] = int(sup[i])
        out[f"predicted_{lab}"] = int(pred_counts[i])
    out["confusion"] = confusion_matrix(y_true, y_pred, labels=labels).tolist()
    out["abs_error_counts"] = {str(k): int((np.abs(d) == k).sum()) for k in range(len(labels))}
    return out


def scalar_metrics(m: dict) -> dict:
    """Drop the non-scalar entries (confusion matrix, error histogram)."""
    return {k: v for k, v in m.items() if not isinstance(v, (list, dict))}
