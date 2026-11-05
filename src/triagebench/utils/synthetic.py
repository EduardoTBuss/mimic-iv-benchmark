"""Synthetic MIMIC-IV-ED-shaped archive for tests, CI and server pre-flight.

Same folder layout, file names and column schema as the PhysioNet v2.2 zip, but every value
is generated from simple distributions: it contains NO real data and can be committed/shared.
It deliberately includes the messy cases the pipeline must survive: missing acuity, free-text
pain ("unable", ranges, fractions, out-of-range numbers), Celsius-typed temperatures,
impossible vitals, dbp >= sbp and patients with many visits.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from triagebench.data.schema import EDSTAYS_COLUMNS, TRIAGE_COLUMNS

ACUITY_P = np.array([0.06, 0.33, 0.53, 0.07, 0.01])
PAIN_TEXT = ["unable", "UTA", "u/a", "denies", "crit", "sleeping", "pt unable to rate", "ok", "8 out of 10", "10+"]


def make_synthetic_tables(n_stays: int = 3000, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    n_subjects = max(10, int(n_stays * 0.5))
    subjects = 10_000_000 + rng.choice(np.arange(1, 50 * n_subjects), size=n_subjects, replace=False)
    weights = rng.pareto(1.5, size=n_subjects) + 1.0
    subject_id = rng.choice(subjects, size=n_stays, p=weights / weights.sum())
    stay_id = 30_000_000 + rng.choice(np.arange(1, 20 * n_stays), size=n_stays, replace=False)
    acuity = rng.choice([1, 2, 3, 4, 5], size=n_stays, p=ACUITY_P).astype(float)
    sev = 3.0 - acuity  # > 0 means more urgent

    temperature = 98.1 + 0.4 * np.clip(sev, 0, None) + rng.normal(0, 0.9, n_stays)
    heartrate = 84 + 7 * sev + rng.normal(0, 14, n_stays)
    resprate = 17.5 + 1.2 * sev + rng.normal(0, 2.5, n_stays)
    o2sat = np.minimum(100, 98.2 - 1.2 * np.clip(sev, 0, None) + rng.normal(0, 1.8, n_stays))
    sbp = 134 + 3 * sev + rng.normal(0, 22, n_stays)
    dbp = 78 + rng.normal(0, 13, n_stays)
    vitals = {"temperature": temperature, "heartrate": heartrate, "resprate": resprate,
              "o2sat": o2sat, "sbp": sbp, "dbp": dbp}
    for name, arr in vitals.items():
        arr[:] = np.round(arr, 1 if name == "temperature" else 0)
        miss = rng.random(n_stays) < (0.03 + 0.10 * (acuity == 1))
        arr[miss] = np.nan

    celsius = rng.random(n_stays) < 0.01
    temperature[celsius] = np.round((temperature[celsius] - 32) * 5 / 9, 1)
    bad = rng.random(n_stays) < 0.004
    heartrate[bad] = 0
    bad = rng.random(n_stays) < 0.002
    sbp[bad] = 999
    bad = rng.random(n_stays) < 0.002
    o2sat[bad] = 120
    swap = rng.random(n_stays) < 0.003
    dbp[swap] = sbp[swap] + 5

    pain = np.round(np.clip(rng.normal(4 + 0.5 * np.clip(sev, 0, None), 3.2, n_stays), 0, 10)).astype(int).astype(str).astype(object)
    u = rng.random(n_stays)
    unable = u < np.where(acuity <= 2, 0.12, 0.02)
    pain[unable] = rng.choice(PAIN_TEXT[:3], size=int(unable.sum()))
    other = (u >= 0.97)
    pain[other] = rng.choice(PAIN_TEXT[3:], size=int(other.sum()))
    pain[(u >= 0.95) & (u < 0.96)] = "5-6"
    pain[(u >= 0.96) & (u < 0.965)] = "7.5"
    pain[(u >= 0.965) & (u < 0.97)] = "13"
    pain[rng.random(n_stays) < 0.03] = None

    acuity[rng.random(n_stays) < 0.015] = np.nan

    triage = pd.DataFrame({
        "subject_id": subject_id, "stay_id": stay_id, **vitals, "pain": pain,
        "acuity": acuity, "chiefcomplaint": "SYNTHETIC",
    })[list(TRIAGE_COLUMNS)]

    intime = pd.Timestamp("2150-01-01") + pd.to_timedelta(rng.integers(0, 3650 * 24, n_stays), unit="h")
    edstays = pd.DataFrame({
        "subject_id": subject_id,
        "hadm_id": np.where(rng.random(n_stays) < 0.4, 20_000_000 + np.arange(n_stays), np.nan),
        "stay_id": stay_id,
        "intime": intime.strftime("%Y-%m-%d %H:%M:%S"),
        "outtime": (intime + pd.to_timedelta(rng.integers(1, 24, n_stays), unit="h")).strftime("%Y-%m-%d %H:%M:%S"),
        "gender": rng.choice(["F", "M"], n_stays),
        "race": "UNKNOWN",
        "arrival_transport": rng.choice(["WALK IN", "AMBULANCE", "UNKNOWN", "OTHER", "HELICOPTER"], n_stays),
        "disposition": rng.choice(["HOME", "ADMITTED", "TRANSFER", "OTHER"], n_stays),
    })[list(EDSTAYS_COLUMNS)]
    # a few ED stays without a triage row (exists in the real data structure)
    extra = edstays.sample(n=max(1, n_stays // 200), random_state=seed).copy()
    extra["stay_id"] = extra["stay_id"] + 10_000_000
    edstays = pd.concat([edstays, extra], ignore_index=True)
    return triage, edstays


def _gz_csv(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(df.to_csv(index=False).encode("utf-8"))
    return buf.getvalue()


def write_synthetic_zip(out_dir: str | Path, n_stays: int = 3000, seed: int = 0,
                        version: str = "2.2") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    root = f"mimic-iv-ed-{version}"
    triage, edstays = make_synthetic_tables(n_stays, seed)
    files = {
        "LICENSE.txt": b"SYNTHETIC DATA - not MIMIC-IV-ED\n",
        "README.txt": b"Synthetic archive generated by triagebench.utils.synthetic\n",
        "ed/triage.csv.gz": _gz_csv(triage),
        "ed/edstays.csv.gz": _gz_csv(edstays),
    }
    sums = "".join(f"{hashlib.sha256(data).hexdigest()} {rel}\n" for rel, data in sorted(files.items()))
    files["SHA256SUMS.txt"] = sums.encode("utf-8")
    zip_path = out_dir / f"{root}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for rel, data in files.items():
            zf.writestr(f"{root}/{rel}", data)
    return zip_path
