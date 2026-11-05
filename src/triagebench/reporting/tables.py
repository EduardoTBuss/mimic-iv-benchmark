"""Dependency-free Markdown tables."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import pandas as pd


def md_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    def cell(v: object) -> str:
        return str(v).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(cell(h) for h in headers) + " |",
             "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def df_to_md(df: pd.DataFrame, floatfmt: str = "{:.4f}") -> str:
    def fmt(v: object) -> object:
        if isinstance(v, float):
            return "—" if pd.isna(v) else floatfmt.format(v)
        return v

    return md_table(list(df.columns), ([fmt(v) for v in row] for row in df.itertuples(index=False)))
