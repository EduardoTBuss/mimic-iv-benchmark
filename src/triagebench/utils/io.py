"""Crash-safe file I/O: every result file is written to a temp file and atomically renamed."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def json_default(obj: Any) -> Any:
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (set, tuple)):
        return list(obj)
    raise TypeError(f"not JSON serializable: {type(obj).__name__}")


def _tmp_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp-{os.getpid()}")


def atomic_write_bytes(path: str | Path, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(path)
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def atomic_write_text(path: str | Path, text: str) -> Path:
    return atomic_write_bytes(path, text.encode("utf-8"))


def _finite(obj: Any) -> Any:
    """Replace non-finite floats (NaN/inf, including numpy float64) by None, recursively."""
    if isinstance(obj, float):
        return obj if np.isfinite(obj) else None
    if isinstance(obj, np.floating):
        return float(obj) if np.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    return obj


def dumps_json(obj: Any) -> str:
    return json.dumps(_finite(obj), indent=2, sort_keys=True, default=json_default, allow_nan=False) + "\n"


def atomic_write_json(path: str | Path, obj: Any) -> Path:
    return atomic_write_text(path, dumps_json(obj))


def atomic_write_parquet(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp_path(path)
    df.to_parquet(tmp, index=False)
    with open(tmp, "r+b") as fh:  # fsync needs a writable handle on Windows
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def append_jsonl(path: str | Path, obj: Any) -> None:
    """Append one JSON line and fsync (a crash can only truncate the last line)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(_finite(obj), sort_keys=True, default=json_default) + "\n"
    if path.exists() and path.stat().st_size > 0:
        with open(path, "rb") as fh:
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":  # a crash truncated the last line: start a fresh one
                line = "\n" + line
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def read_jsonl(path: str | Path) -> list[dict]:
    """Read a JSONL file, ignoring a truncated (partially written) trailing line."""
    path = Path(path)
    if not path.exists():
        return []
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return rows


def sha256_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def touch_atomic(path: str | Path, content: str = "") -> Path:
    return atomic_write_text(path, content or utc_now() + "\n")
