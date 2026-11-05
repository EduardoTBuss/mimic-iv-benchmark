"""Deterministic seed derivation: one master seed per split, sub-seeds by purpose."""

from __future__ import annotations

import hashlib


def derive_seed(*parts: object) -> int:
    """Stable 31-bit seed from arbitrary parts (independent of PYTHONHASHSEED and platform)."""
    text = "|".join(str(p) for p in parts)
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) & 0x7FFFFFFF
