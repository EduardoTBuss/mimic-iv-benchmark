"""Test-set guard: a task may evaluate on its test partition only with ONE frozen configuration.

Re-evaluating the same frozen configuration (e.g. after a crash between test evaluation and the
atomic result write) is allowed and logged; evaluating a different configuration raises.
"""

from __future__ import annotations

from pathlib import Path

from triagebench.utils.io import atomic_write_json, read_json, utc_now


class TestAccessError(RuntimeError):
    """A second, different configuration tried to touch the test partition."""


def guard_test_access(task_dir: Path, frozen_hash: str) -> dict:
    path = Path(task_dir) / "test_access.json"
    if path.exists():
        record = read_json(path)
        if record["frozen_config_hash"] != frozen_hash:
            raise TestAccessError(
                f"test partition already used by configuration {record['frozen_config_hash'][:12]}; "
                f"refusing configuration {frozen_hash[:12]}"
            )
        record["reaccess_same_config"] = record.get("reaccess_same_config", 0) + 1
        record["last_access_at"] = utc_now()
    else:
        record = {"frozen_config_hash": frozen_hash, "first_access_at": utc_now(), "reaccess_same_config": 0}
    atomic_write_json(path, record)
    return record
