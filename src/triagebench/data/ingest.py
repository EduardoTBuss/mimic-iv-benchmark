"""Verify the PhysioNet archive and extract it outside the repository.

PhysioNet ships ``SHA256SUMS.txt`` inside the zip (one hash per file). We verify every
extracted file against it and also record the SHA256 of the zip itself as the dataset
fingerprint used in every manifest.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

from triagebench.data.schema import IntegrityError, SchemaMismatchError
from triagebench.utils.io import sha256_file, utc_now


def parse_sha256sums(text: str) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        digest, rel = parts[0].lower(), parts[-1].lstrip("*")
        sums[rel] = digest
    return sums


def verify_and_extract(zip_path: str | Path, extract_dir: str | Path, expected_version: str) -> dict:
    """Extract ``zip_path`` into ``extract_dir`` (idempotent) and verify every file hash.

    Returns a JSON-serialisable record (file names and hashes only, never content).
    """
    zip_path, extract_dir = Path(zip_path), Path(extract_dir)
    if not zip_path.exists():
        raise FileNotFoundError(f"dataset zip not found: {zip_path}")
    expected_root = f"mimic-iv-ed-{expected_version}"
    zip_sha = sha256_file(zip_path)

    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        roots = {n.split("/", 1)[0] for n in names}
        if roots != {expected_root}:
            raise SchemaMismatchError(f"zip root folder(s) {sorted(roots)} != expected {expected_root!r}")
        sums_name = f"{expected_root}/SHA256SUMS.txt"
        if sums_name not in names:
            raise IntegrityError(f"{sums_name} missing from the archive")
        sums = parse_sha256sums(zf.read(sums_name).decode("utf-8"))

        extract_dir.mkdir(parents=True, exist_ok=True)
        base = extract_dir.resolve()
        for name in names:
            target = (extract_dir / name).resolve()
            if not target.is_relative_to(base):
                raise IntegrityError(f"unsafe path in archive: {name}")
            rel = name.split("/", 1)[1]
            if target.exists() and rel in sums and sha256_file(target) == sums[rel]:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f".{target.name}.tmp-{os.getpid()}")
            with zf.open(name) as src, open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            os.replace(tmp, target)

    files = {}
    for rel, expected in sorted(sums.items()):
        path = extract_dir / expected_root / rel
        actual = sha256_file(path) if path.exists() else None
        files[rel] = {
            "sha256": actual,
            "expected": expected,
            "ok": actual == expected,
            "bytes": path.stat().st_size if path.exists() else None,
        }
    bad = [rel for rel, rec in files.items() if not rec["ok"]]
    if bad:
        raise IntegrityError(f"SHA256 mismatch for {bad}")
    return {
        "zip_name": zip_path.name,
        "zip_sha256": zip_sha,
        "zip_bytes": zip_path.stat().st_size,
        "root": expected_root,
        "files": files,
        "verified_at": utc_now(),
    }
