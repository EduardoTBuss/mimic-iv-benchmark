"""Small-cell suppression for anything that leaves ``outputs/`` (reports, figures, git).

Counts from 1 to ``k - 1`` are masked (default k = 11, the usual MIMIC/HCUP disclosure rule);
percentages computed from a masked count are masked as well. Zero is not masked.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_K = 11
MASK = "—"


def is_small(n: float | int, k: int = DEFAULT_K) -> bool:
    return 0 < int(n) < k


def mask_count(n: float | int, k: int = DEFAULT_K) -> str:
    n = int(n)
    return f"<{k}" if is_small(n, k) else f"{n:,}"


def mask_pct(n: float | int, denom: float | int, k: int = DEFAULT_K, digits: int = 2) -> str:
    if not denom:
        return MASK
    if is_small(n, k):
        return MASK
    return f"{100.0 * float(n) / float(denom):.{digits}f}%"


def mask_matrix(counts: np.ndarray, k: int = DEFAULT_K) -> np.ndarray:
    """Return a float matrix where small cells are NaN (to be drawn as masked)."""
    arr = np.asarray(counts, dtype=float).copy()
    arr[(arr > 0) & (arr < k)] = np.nan
    return arr


def mask_count_columns(df: pd.DataFrame, columns: list[str], k: int = DEFAULT_K) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        out[col] = out[col].map(lambda v: mask_count(v, k) if pd.notna(v) else MASK)
    return out
