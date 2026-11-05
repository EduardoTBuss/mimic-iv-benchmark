"""Documented MIMIC-IV-ED v2.2 schema (https://physionet.org/content/mimic-iv-ed/2.2/)."""

from __future__ import annotations

DATASET_VERSION = "2.2"

TRIAGE_COLUMNS = (
    "subject_id",
    "stay_id",
    "temperature",
    "heartrate",
    "resprate",
    "o2sat",
    "sbp",
    "dbp",
    "pain",
    "acuity",
    "chiefcomplaint",
)
EDSTAYS_COLUMNS = (
    "subject_id",
    "hadm_id",
    "stay_id",
    "intime",
    "outtime",
    "gender",
    "race",
    "arrival_transport",
    "disposition",
)
VITALS = ("temperature", "heartrate", "resprate", "o2sat", "sbp", "dbp")

# chiefcomplaint (free text, may contain residual PHI markers) is never loaded.
TRIAGE_LOAD_COLUMNS = tuple(c for c in TRIAGE_COLUMNS if c != "chiefcomplaint")
EDSTAYS_LOAD_COLUMNS = ("subject_id", "stay_id")

ACUITY_LEVELS = (1, 2, 3, 4, 5)


class SchemaMismatchError(RuntimeError):
    """Files diverge from the documented v2.2 schema. Stop and ask (mission rule)."""


class IntegrityError(RuntimeError):
    """A SHA256 check failed or the archive is malformed."""


class DataConsistencyError(RuntimeError):
    """Structural inconsistency (duplicated stay_id, subject mismatch...). Stop and ask."""
