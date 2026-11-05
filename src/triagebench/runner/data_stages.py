"""Data stages: ingest -> audit -> prepare (cleaning variants + patient-level splits).

Each stage is idempotent: outputs are keyed by content hashes and a stage that already
finished with the same inputs is skipped.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from triagebench.data.audit import build_audit, render_audit_markdown
from triagebench.data.ingest import verify_and_extract
from triagebench.data.load import assert_consistent, consistency_report, load_edstays, load_triage, table_path
from triagebench.data.split import assign_partitions, split_summary
from triagebench.preprocessing.cleaning import prepare_variant
from triagebench.reporting.disclosure import mask_count, mask_pct
from triagebench.reporting.tables import md_table
from triagebench.utils.config import prepare_hash, primary_variant, stable_hash
from triagebench.utils.io import (
    atomic_write_json,
    atomic_write_parquet,
    atomic_write_text,
    read_json,
    utc_now,
)
from triagebench.utils.logging import get_logger
from triagebench.utils.seeds import derive_seed

log = get_logger("data")


def outputs_dir(cfg: dict) -> Path:
    return Path(cfg["paths"]["outputs"])


def reports_dir(cfg: dict) -> Path:
    return Path(cfg["paths"]["reports"])


def stage_ingest(cfg: dict) -> dict:
    ds = cfg["dataset"]
    record = verify_and_extract(ds["zip_path"], ds["extract_dir"], ds["version"])
    atomic_write_json(outputs_dir(cfg) / "ingest" / f"{record['zip_sha256'][:16]}.json", record)
    log.info("ingest OK: %s (sha256 %s), %d files verified", record["zip_name"], record["zip_sha256"][:16], len(record["files"]))
    return record


def _load_tables(cfg: dict) -> tuple[pd.DataFrame, dict, dict]:
    triage, load_report = load_triage(table_path(cfg, "triage"))
    edstays = load_edstays(table_path(cfg, "edstays"))
    consistency = consistency_report(triage, edstays)
    assert_consistent(consistency)
    return triage, load_report, consistency


def stage_audit(cfg: dict, ingest: dict, force: bool = False) -> dict:
    audit_dir = outputs_dir(cfg) / "audit" / stable_hash({"zip": ingest["zip_sha256"], "cleaning": cfg["cleaning"],
                                                          "k": cfg["evaluation"]["disclosure_min_cell"]}, 16)
    md_path = reports_dir(cfg) / "data_audit.md"
    if not force and (audit_dir / "audit.json").exists() and md_path.exists():
        log.info("audit up to date (%s)", audit_dir.name)
        return read_json(audit_dir / "audit.json")
    triage, load_report, consistency = _load_tables(cfg)
    audit = build_audit(triage, load_report, consistency, ingest, cfg)
    atomic_write_json(audit_dir / "audit.json", audit)
    atomic_write_text(md_path, render_audit_markdown(audit))
    log.info("audit written: %s", md_path)
    return audit


def prepared_dir(cfg: dict, ingest: dict) -> Path:
    return outputs_dir(cfg) / "prepared" / prepare_hash(cfg, ingest["zip_sha256"])[:16]


def _sample_patients(df: pd.DataFrame, fraction: float | None) -> pd.DataFrame:
    if not fraction:
        return df
    patients = np.sort(df["subject_id"].unique())
    rng = np.random.default_rng(derive_seed("prepare.sample_fraction", fraction))
    keep = rng.choice(patients, size=max(1, int(round(len(patients) * fraction))), replace=False)
    return df[df["subject_id"].isin(keep)].reset_index(drop=True)


def _cleaning_md(variant: str, log_rows: list[dict], k: int) -> str:
    rows = []
    for r in log_rows:
        if r["type"] == "row":
            rows.append([r["rule"], "remove stay", "—", mask_count(r["n_rows_before"], k), mask_count(r["n_removed"], k),
                         mask_count(r["n_rows_after"], k), mask_pct(r["n_removed"], r["n_rows_before"], k),
                         mask_count(r["by_acuity"].get("1", 0), k)])
        else:
            rows.append([r["rule"], r["action"], r["variable"], mask_count(r["n_rows"], k), mask_count(r["n_values_affected"], k),
                         "—", mask_pct(r["n_values_affected"], r["n_rows"], k), mask_count(r["by_acuity"].get("1", 0), k)])
    return "\n".join([f"### Variante `{variant}`", "",
                      md_table(["regra", "ação", "variável", "linhas antes", "afetadas", "linhas depois", "% afetadas",
                                "afetadas com acuity 1"], rows), ""])


def _split_md(seed: int, s: dict, k: int) -> list[str]:
    rows = []
    for part, d in s["partitions"].items():
        total = d["n_stays"]
        rows.append([seed, part, mask_count(total, k), mask_count(d["n_patients"], k)]
                    + [mask_pct(d["acuity_counts"].get(str(a), 0), total, k) for a in range(1, 6)])
    return rows


def stage_prepare(cfg: dict, ingest: dict, force: bool = False) -> Path:
    out = prepared_dir(cfg, ingest)
    marker = out / "PREPARED.json"
    if marker.exists() and not force:
        log.info("prepared data up to date (%s)", out.name)
        return out
    k = int(cfg["evaluation"]["disclosure_min_cell"])
    triage, _, consistency = _load_tables(cfg)
    triage = _sample_patients(triage, cfg.get("prepare", {}).get("sample_fraction"))

    private = out / "private"
    md = ["# Preparação dos dados (somente agregados)", "",
          f"Dados preparados `{out.name}`. Contagens de 1 a {k - 1} aparecem como `<{k}`.", "",
          "## Regras de limpeza (antes/depois)", ""]
    variant_stays: dict[str, set] = {}
    data_by_variant: dict[str, pd.DataFrame] = {}
    for name, vcfg in cfg["variants"].items():
        res = prepare_variant(triage, vcfg, cfg["cleaning"])
        atomic_write_parquet(res.data, private / f"{name}.parquet")
        for rule, frame in res.excluded.items():
            atomic_write_parquet(frame.reset_index(drop=True), private / "excluded" / f"{name}__{rule}.parquet")
        atomic_write_json(out / f"cleaning_{name}.json", res.log)
        md.append(_cleaning_md(name, res.log, k))
        variant_stays[name] = set(res.data["stay_id"])
        data_by_variant[name] = res.data
        log.info("variant %s: %d stays kept", name, len(res.data))

    primary = primary_variant(cfg)
    for name, stays in variant_stays.items():
        if not stays <= variant_stays[primary]:
            raise RuntimeError(f"variant {name} is not nested in the primary variant {primary}")

    md += ["## Partições por paciente (calculadas na variante principal; as outras usam o mesmo mapa)", ""]
    split_rows = []
    summaries = {}
    base = data_by_variant[primary]
    for seed in cfg["split"]["seeds"]:
        assign = assign_partitions(base, seed, cfg["split"]["fractions"])
        atomic_write_parquet(assign, private / "splits" / f"seed_{seed}.parquet")
        summ = split_summary(assign, base)
        if any(summ["patient_overlap"].values()):
            raise RuntimeError(f"patient overlap between partitions for seed {seed}: {summ['patient_overlap']}")
        summaries[str(seed)] = summ
        split_rows += _split_md(seed, summ, k)
    atomic_write_json(out / "splits_summary.json", summaries)
    md += [md_table(["seed", "partição", "estadias", "pacientes"] + [f"% acuity {a}" for a in range(1, 6)], split_rows), "",
           "Sobreposição de pacientes entre partições: 0 em todas as seeds (verificado).", ""]
    atomic_write_text(out / "data_preparation.md", "\n".join(md))
    atomic_write_json(marker, {"prepared_at": utc_now(), "zip_sha256": ingest["zip_sha256"],
                               "variants": {n: len(d) for n, d in data_by_variant.items()},
                               "consistency": consistency, "seeds": cfg["split"]["seeds"]})
    return out
