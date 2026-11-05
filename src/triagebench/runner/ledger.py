"""File-based task ledger and campaign lock.

A task is DONE iff ``tasks/<id>/DONE`` and ``result.json`` exist (both written atomically by
the worker, DONE last). ``state.json`` is written only by the scheduler (single writer, guarded
by the campaign lock), so there are no races between processes.
"""

from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from pathlib import Path

import psutil

from triagebench.utils.io import atomic_write_json, read_json, utc_now


class RunnerLockedError(RuntimeError):
    """Another live scheduler already owns this campaign."""


class Ledger:
    def __init__(self, campaign_dir: Path):
        self.root = Path(campaign_dir) / "tasks"

    def task_dir(self, task_id: str) -> Path:
        return self.root / task_id

    def is_done(self, task_id: str) -> bool:
        d = self.task_dir(task_id)
        return (d / "DONE").exists() and (d / "result.json").exists()

    def state(self, task_id: str) -> dict:
        path = self.task_dir(task_id) / "state.json"
        if path.exists():
            try:
                return read_json(path)
            except ValueError:
                pass
        return {"state": "pending", "attempts": 0, "history": []}

    def write_state(self, task_id: str, state: dict) -> None:
        atomic_write_json(self.task_dir(task_id) / "state.json", state)

    def mark_running(self, task_id: str, pid: int) -> dict:
        st = self.state(task_id)
        st["state"] = "running"
        st["attempts"] = int(st.get("attempts", 0)) + 1
        st["pid"] = pid
        st["host"] = socket.gethostname()
        st["started_at"] = utc_now()
        self.write_state(task_id, st)
        return st

    def mark_finished(self, task_id: str, state: str, exit_code: int | None, reason: str,
                      seconds: float) -> dict:
        st = self.state(task_id)
        st.setdefault("history", []).append({
            "attempt": st.get("attempts", 0), "started_at": st.get("started_at"), "ended_at": utc_now(),
            "exit_code": exit_code, "reason": reason, "seconds": round(seconds, 2), "host": socket.gethostname(),
        })
        st["state"] = state
        st.pop("pid", None)
        self.write_state(task_id, st)
        return st


@contextmanager
def campaign_lock(campaign_dir: Path):
    """Exclusive lock: refuses to start if a live scheduler on this host owns the campaign."""
    path = Path(campaign_dir) / "runner.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    me = {"pid": os.getpid(), "host": socket.gethostname(), "started_at": utc_now()}
    if path.exists():
        try:
            other = read_json(path)
        except ValueError:
            other = {}
        if other.get("host") == me["host"] and other.get("pid") and psutil.pid_exists(int(other["pid"])) \
                and int(other["pid"]) != me["pid"]:
            raise RunnerLockedError(f"campaign already running (pid {other['pid']} since {other.get('started_at')})")
        if other.get("host") and other.get("host") != me["host"]:
            raise RunnerLockedError(f"campaign lock held by another host ({other['host']}); remove {path} if stale")
    atomic_write_json(path, me)
    try:
        yield me
    finally:
        try:
            if read_json(path).get("pid") == me["pid"]:
                path.unlink()
        except (OSError, ValueError):
            pass
