"""Data layer: archive integrity, schema checks, cleaning rules, prepared outputs, crash-safe I/O.
SYNTHETIC data only (triagebench.utils.synthetic)."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests._helpers import make_cfg, prepare
from tests.conftest import REPO
from triagebench.data.ingest import verify_and_extract
from triagebench.data.load import load_triage
from triagebench.data.schema import DataConsistencyError, IntegrityError, SchemaMismatchError
from triagebench.preprocessing.cleaning import CleanResult, apply_value_rules
from triagebench.runner.data_stages import prepared_dir, stage_ingest, stage_prepare
from triagebench.utils import io as tio
from triagebench.utils.config import load_config
from triagebench.utils.synthetic import make_synthetic_tables, write_synthetic_zip

ROOT = "mimic-iv-ed-2.2"
CLEANING = load_config(REPO / "configs" / "main.yaml")["cleaning"]
PREPARED_COLUMNS = ["stay_id", "subject_id", "acuity", "temperature", "heartrate", "resprate", "o2sat", "sbp", "dbp",
                    "pain_value", "pain_status", "pain_kind", "pain_raw"]


def _rewrite_zip(src: Path, dst: Path, edit) -> Path:
    """Copy ``src`` to ``dst`` applying ``edit(name, data) -> (name, data) | None`` to every member."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for name in zin.namelist():
            out = edit(name, zin.read(name))
            if out is not None:
                zout.writestr(out[0], out[1])
    return dst


def _gz(text: str) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as fh:
        fh.write(text.encode("utf-8"))
    return buf.getvalue()


def _with_sums(files: dict[str, bytes]) -> dict[str, bytes]:
    sums = "".join(f"{hashlib.sha256(d).hexdigest()} {rel}\n" for rel, d in sorted(files.items()))
    return {**files, "SHA256SUMS.txt": sums.encode()}


def _zip_from(dst: Path, files: dict[str, bytes], root: str = ROOT) -> Path:
    with zipfile.ZipFile(dst, "w") as zf:
        for rel, data in files.items():
            zf.writestr(f"{root}/{rel}", data)
    return dst


def _members(zip_path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(zip_path) as zf:
        return {n.split("/", 1)[1]: zf.read(n) for n in zf.namelist() if n != f"{ROOT}/SHA256SUMS.txt"}


# --------------------------------------------------------------------------- ingest / integrity

def test_ingest_verifies_every_listed_file(cfg):
    rec = stage_ingest(cfg)
    assert rec["files"] and all(r["ok"] for r in rec["files"].values())
    assert {"ed/triage.csv.gz", "ed/edstays.csv.gz"} <= set(rec["files"])
    assert rec["zip_sha256"] == tio.sha256_file(cfg["dataset"]["zip_path"])
    assert "SYNTHETIC" not in json.dumps(rec)   # record holds names/hashes only, never content


def test_ingest_is_idempotent_and_self_heals_a_corrupted_extraction(cfg):
    rec1 = stage_ingest(cfg)
    triage = Path(cfg["dataset"]["extract_dir"]) / ROOT / "ed" / "triage.csv.gz"
    triage.write_bytes(b"corrupted")
    rec2 = stage_ingest(cfg)
    assert rec2["files"]["ed/triage.csv.gz"]["sha256"] == rec1["files"]["ed/triage.csv.gz"]["sha256"]
    assert tio.sha256_file(triage) == rec1["files"]["ed/triage.csv.gz"]["expected"]


def test_ingest_rejects_tampered_member(tmp_path, synthetic_zip):
    bad = _rewrite_zip(synthetic_zip, tmp_path / "bad.zip",
                       lambda n, d: (n, d + b"x") if n.endswith("edstays.csv.gz") else (n, d))
    with pytest.raises(IntegrityError, match="SHA256 mismatch"):
        verify_and_extract(bad, tmp_path / "x", "2.2")


def test_ingest_requires_sha256sums(tmp_path, synthetic_zip):
    bad = _rewrite_zip(synthetic_zip, tmp_path / "bad.zip", lambda n, d: None if n.endswith("SHA256SUMS.txt") else (n, d))
    with pytest.raises(IntegrityError, match="SHA256SUMS"):
        verify_and_extract(bad, tmp_path / "x", "2.2")


def test_ingest_rejects_wrong_version_root(tmp_path, synthetic_zip):
    with pytest.raises(SchemaMismatchError):
        verify_and_extract(synthetic_zip, tmp_path / "x", "2.1")


def test_ingest_rejects_zip_slip_and_writes_nothing_outside(tmp_path, synthetic_zip):
    files = _with_sums({**_members(synthetic_zip), "../../evil.txt": b"pwned"})
    bad = _zip_from(tmp_path / "slip.zip", files)
    target = tmp_path / "deep" / "x"
    with pytest.raises(IntegrityError, match="unsafe path"):
        verify_and_extract(bad, target, "2.2")
    assert not (tmp_path / "deep" / "evil.txt").exists() and not (tmp_path / "evil.txt").exists()


def test_ingest_missing_zip(tmp_path):
    with pytest.raises(FileNotFoundError):
        verify_and_extract(tmp_path / "nope.zip", tmp_path / "x", "2.2")


def test_load_rejects_schema_drift(tmp_path):
    triage, _ = make_synthetic_tables(50, seed=1)
    path = tmp_path / "triage.csv.gz"
    path.write_bytes(_gz(triage.rename(columns={"pain": "pain_score"}).to_csv(index=False)))
    with pytest.raises(SchemaMismatchError):
        load_triage(path)


def test_load_never_keeps_chiefcomplaint_and_coerces_text_vitals(tmp_path):
    triage, _ = make_synthetic_tables(50, seed=1)
    triage["heartrate"] = triage["heartrate"].astype(object)
    triage.loc[0, "heartrate"] = "abc"
    path = tmp_path / "triage.csv.gz"
    path.write_bytes(_gz(triage.to_csv(index=False)))
    df, report = load_triage(path)
    assert "chiefcomplaint" not in df.columns
    assert np.isnan(df.loc[0, "heartrate"])
    assert report["non_numeric_coerced"]["heartrate"] == 1


def test_prepare_stops_on_duplicated_stay_id(tmp_path):
    triage, edstays = make_synthetic_tables(300, seed=2)
    triage = pd.concat([triage, triage.iloc[[0]]], ignore_index=True)
    files = _with_sums({"LICENSE.txt": b"SYNTHETIC", "ed/triage.csv.gz": _gz(triage.to_csv(index=False)),
                        "ed/edstays.csv.gz": _gz(edstays.to_csv(index=False))})
    zip_path = _zip_from(tmp_path / f"{ROOT}.zip", files)
    cfg = make_cfg(tmp_path, zip_path)
    ingest = stage_ingest(cfg)
    with pytest.raises(DataConsistencyError, match="triage_duplicated_stay_id"):
        stage_prepare(cfg, ingest)


# --------------------------------------------------------------------------- cleaning rules

def _frame(**cols):
    n = len(next(iter(cols.values())))
    base = {"temperature": [98.0] * n, "heartrate": [80.0] * n, "resprate": [16.0] * n, "o2sat": [98.0] * n,
            "sbp": [120.0] * n, "dbp": [80.0] * n, "acuity": [3] * n}
    base.update(cols)
    return pd.DataFrame(base)


def test_celsius_like_temperatures_are_converted():
    out = apply_value_rules(_frame(temperature=[37.0, 25.0, 45.0, 98.6, 24.9]), CLEANING, CleanResult(pd.DataFrame()))
    # 37 C -> 98.6 F; 25 C -> 77 F lies between outlier_low (57.56) and valid_low (78.8): clipped;
    # 45 C -> 113 F == valid_high; 98.6 is already Fahrenheit
    np.testing.assert_allclose(out["temperature"].iloc[:4], [98.6, 78.8, 113.0, 98.6])
    assert np.isnan(out["temperature"].iloc[4])     # 24.9 F: below outlier_low -> NaN


def test_outliers_become_nan_and_borderline_values_are_clipped():
    out = apply_value_rules(_frame(sbp=[999.0, 375.0, 130.0], o2sat=[151.0, 120.0, 100.0],
                                   heartrate=[0.0, 389.0, 391.0]), CLEANING, CleanResult(pd.DataFrame()))
    assert np.isnan(out["sbp"].iloc[0]) and out["sbp"].iloc[1] == 375.0
    assert np.isnan(out["o2sat"].iloc[0]) and out["o2sat"].iloc[1] == 100.0
    assert np.isnan(out["heartrate"].iloc[0])       # zero_to_nan
    assert out["heartrate"].iloc[1] == 350.0 and np.isnan(out["heartrate"].iloc[2])


def test_dbp_ge_sbp_sets_both_to_nan_and_never_drops_rows():
    df = _frame(sbp=[120.0, 100.0, np.nan], dbp=[80.0, 100.0, 90.0])
    res = CleanResult(pd.DataFrame())
    out = apply_value_rules(df, CLEANING, res)
    assert len(out) == len(df)
    assert out.loc[1, ["sbp", "dbp"]].isna().all()
    assert out.loc[0, "sbp"] == 120.0 and out.loc[2, "dbp"] == 90.0
    entry = next(r for r in res.log if r["rule"] == "dbp_ge_sbp")
    assert entry["n_values_affected"] == 1


def test_value_rules_do_not_mutate_input():
    df = _frame(sbp=[999.0])
    apply_value_rules(df, CLEANING, CleanResult(pd.DataFrame()))
    assert df.loc[0, "sbp"] == 999.0


# --------------------------------------------------------------------------- prepared outputs

@pytest.fixture(scope="module")
def prepared(tmp_path_factory, synthetic_zip):
    root = tmp_path_factory.mktemp("prep")
    cfg = make_cfg(root, synthetic_zip)
    ingest, out = prepare(cfg)
    return {"cfg": cfg, "ingest": ingest, "dir": out}


def test_prepared_variant_schema_and_value_domains(prepared):
    r = CLEANING["ranges"]
    for variant in prepared["cfg"]["variants"]:
        df = pd.read_parquet(prepared["dir"] / "private" / f"{variant}.parquet")
        assert list(df.columns) == PREPARED_COLUMNS
        assert "chiefcomplaint" not in df.columns
        assert df["stay_id"].is_unique
        assert set(df["acuity"].unique()) <= {1, 2, 3, 4, 5} and df["acuity"].notna().all()
        pv = df["pain_value"].dropna()
        assert ((pv >= 0) & (pv <= 10)).all()
        assert set(df["pain_status"]) <= set(CLEANING["pain"]["status_categories"])
        for var, b in r.items():
            x = df[var].dropna()
            assert ((x >= b["valid_low"]) & (x <= b["valid_high"])).all(), var
        both = df[["sbp", "dbp"]].dropna()
        assert (both["dbp"] < both["sbp"]).all()


def test_prepared_split_files_schema(prepared):
    for seed in prepared["cfg"]["split"]["seeds"]:
        s = pd.read_parquet(prepared["dir"] / "private" / "splits" / f"seed_{seed}.parquet")
        assert list(s.columns) == ["stay_id", "subject_id", "partition"]
        assert set(s["partition"]) == {"train", "val", "test"}


def test_prepare_is_skipped_when_up_to_date_and_keyed_by_config(prepared, synthetic_zip):
    marker = prepared["dir"] / "PREPARED.json"
    before = marker.read_bytes()
    assert stage_prepare(prepared["cfg"], prepared["ingest"]) == prepared["dir"]
    assert marker.read_bytes() == before
    other = make_cfg(Path(prepared["cfg"]["paths"]["outputs"]).parent, synthetic_zip, overrides=["split.seeds=[1, 3]"])
    # same zip, different split -> different prepared id (old data is never overwritten)
    assert prepared_dir(other, prepared["ingest"]) != prepared["dir"]


def test_public_preparation_report_has_no_identifiers(prepared):
    md = (prepared["dir"] / "data_preparation.md").read_text(encoding="utf-8")
    a = pd.read_parquet(prepared["dir"] / "private" / "A_keep_encode.parquet")
    for ident in pd.concat([a["stay_id"], a["subject_id"]]).unique():
        assert str(ident) not in md and f"{ident:,}" not in md


# --------------------------------------------------------------------------- 6c. crash-safe writes

class Boom(OSError):
    pass


def _boom(*_a, **_k):
    raise Boom("simulated crash")


@pytest.mark.parametrize("writer", ["text", "json", "parquet"])
def test_failed_replace_keeps_previous_content(tmp_path, monkeypatch, writer):
    target = tmp_path / f"f.{writer}"
    old = {"text": lambda: tio.atomic_write_text(target, "old\n"),
           "json": lambda: tio.atomic_write_json(target, {"v": "old"}),
           "parquet": lambda: tio.atomic_write_parquet(pd.DataFrame({"v": [1, 2]}), target)}
    new = {"text": lambda: tio.atomic_write_text(target, "new\n" * 10_000),
           "json": lambda: tio.atomic_write_json(target, {"v": "new" * 1000}),
           "parquet": lambda: tio.atomic_write_parquet(pd.DataFrame({"v": range(10_000)}), target)}
    old[writer]()
    before = target.read_bytes()
    monkeypatch.setattr(tio.os, "replace", _boom)
    with pytest.raises(Boom):
        new[writer]()
    assert target.read_bytes() == before


@pytest.mark.parametrize("fail_at", ["fsync", "replace"])
def test_failed_first_write_leaves_no_target(tmp_path, monkeypatch, fail_at):
    target = tmp_path / "sub" / "result.json"
    monkeypatch.setattr(tio.os, fail_at, _boom)
    with pytest.raises(Boom):
        tio.atomic_write_json(target, {"a": 1})
    assert not target.exists()
    # the reader-side contract: whatever is at the target path is always complete JSON
    monkeypatch.undo()
    tio.atomic_write_json(target, {"a": 2})
    assert tio.read_json(target) == {"a": 2}


def test_failed_write_mid_stream_keeps_previous_content(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    tio.atomic_write_json(target, {"state": "running"})
    class HalfWriter:
        def __init__(self, fh):
            self.fh = fh

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.fh.close()

        def write(self, data):
            self.fh.write(data[: len(data) // 2])
            raise Boom("disk full")

    # shadow open() only inside triagebench.utils.io: the temp file receives half the bytes, then fails
    monkeypatch.setattr(tio, "open", lambda p, m="r", *a, **k: HalfWriter(open(p, m, *a, **k)), raising=False)
    with pytest.raises(Boom):
        tio.atomic_write_json(target, {"state": "done", "pad": "x" * 5000})
    monkeypatch.undo()
    assert tio.read_json(target) == {"state": "running"}


def test_read_jsonl_ignores_truncated_last_line_and_blank_lines(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text('{"index": 0}\n\n{"index": 1}\n{"index": 2, "par', encoding="utf-8")
    assert [r["index"] for r in tio.read_jsonl(path)] == [0, 1]
    assert tio.read_jsonl(tmp_path / "missing.jsonl") == []


def test_append_jsonl_round_trip_with_numpy_and_unicode(tmp_path):
    path = tmp_path / "t.jsonl"
    rows = [{"i": np.int64(1), "x": np.float64(0.5), "s": "dor não numérica 疼"}, {"i": 2, "arr": np.arange(3)}]
    for r in rows:
        tio.append_jsonl(path, r)
    back = tio.read_jsonl(path)
    assert back == [{"i": 1, "x": 0.5, "s": "dor não numérica 疼"}, {"i": 2, "arr": [0, 1, 2]}]


def test_append_after_truncated_line_is_readable(tmp_path):
    path = tmp_path / "trials.jsonl"
    path.write_text('{"index": 0}\n{"index": 1, "par', encoding="utf-8")   # crash mid-write
    tio.append_jsonl(path, {"index": 1, "status": "ok"})
    assert [r["index"] for r in tio.read_jsonl(path)] == [0, 1]


def test_json_writer_maps_float32_nan_to_null(tmp_path):
    tio.atomic_write_json(tmp_path / "a.json", {"x": np.float32("nan"), "y": np.int32(3), "p": Path("a")})
    assert tio.read_json(tmp_path / "a.json") == {"x": None, "y": 3, "p": "a"}


@pytest.mark.parametrize("value", [np.float64("nan"), float("nan")], ids=["float64", "float"])
def test_json_writer_maps_float64_nan_to_null(tmp_path, value):
    tio.atomic_write_json(tmp_path / "a.json", {"x": value})
    assert tio.read_json(tmp_path / "a.json") == {"x": None}


def test_synthetic_zip_has_physionet_layout(tmp_path):
    z = write_synthetic_zip(tmp_path, n_stays=50, seed=3)
    with zipfile.ZipFile(z) as zf:
        names = set(zf.namelist())
    assert {f"{ROOT}/ed/triage.csv.gz", f"{ROOT}/ed/edstays.csv.gz", f"{ROOT}/SHA256SUMS.txt"} <= names
    assert z.name == f"{ROOT}.zip"
