"""Scheduler: keeps up to N worker processes busy, with retries, timeouts and resource guards.

* one subprocess per task (an OOM-killed or crashed worker only loses its own task);
* limited retries (``max_attempts``), failures recorded in ``state.json`` + ``error.json``;
* guards before every launch: free RAM, 1-min load (``n_cpus - reserve_cpus``), CPU temperature;
* thermal emergency: above ``max_cpu_temp_c + 10`` all workers are suspended until it cools down;
* live control without restart: ``control.yaml`` (``max_workers``, ``pause``) is re-read every poll;
* SIGTERM/SIGINT: stop launching, terminate workers; their tasks resume on the next run.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import psutil
import yaml

from triagebench.runner.ledger import Ledger, campaign_lock
from triagebench.runner.tasks import Task
from triagebench.utils.io import atomic_write_json, utc_now
from triagebench.utils.logging import get_logger

log = get_logger("scheduler")
THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
               "VECLIB_MAXIMUM_THREADS")
_SRC = str(Path(__file__).resolve().parents[2])


@dataclass
class Running:
    task: Task
    proc: subprocess.Popen
    started: float
    logfile: object
    suspended: bool = False


@dataclass
class Summary:
    done: int = 0
    failed: int = 0
    pending: int = 0
    skipped_done: int = 0
    interrupted: bool = False
    failed_ids: list = field(default_factory=list)


def cpu_temperature() -> float | None:
    """CPU package temperature (Intel "Package id", AMD "Tctl"/"Tdie"); falls back to the hottest
    core. Single-core turbo spikes make per-core readings jump 35 <-> 90 C within seconds."""
    try:
        sensors = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return None
    cpu = {k: v for k, v in (sensors or {}).items() if k in ("coretemp", "k10temp", "zenpower", "cpu_thermal")}
    package = [t.current for entries in cpu.values() for t in entries
               if t.current and (t.label or "").startswith(("Package", "Tctl", "Tdie"))]
    if package:
        return max(package)
    temps = [t.current for entries in cpu.values() for t in entries if t.current]
    return max(temps) if temps else None


class SmoothedTemperature:
    """Mean of the last ``window`` readings (one per scheduler poll)."""

    def __init__(self, window: int = 6):
        self.window, self.values = window, []

    def update(self) -> float | None:
        t = cpu_temperature()
        if t is not None:
            self.values = (self.values + [t])[-self.window:]
        return sum(self.values) / len(self.values) if self.values else None


def load_average() -> float:
    try:
        return os.getloadavg()[0]
    except (AttributeError, OSError):
        return psutil.getloadavg()[0]


def resources_ok(res: dict, path: Path | None = None, temp: float | None = None) -> tuple[bool, str]:
    if path is not None and res.get("min_free_disk_gb"):
        free = psutil.disk_usage(str(path)).free / 2**30
        if free < float(res["min_free_disk_gb"]):
            return False, f"free disk {free:.1f} GB < {res['min_free_disk_gb']}"
    avail = psutil.virtual_memory().available / 2**30
    if avail < float(res.get("min_free_ram_gb", 0)):
        return False, f"free RAM {avail:.1f} GB < {res['min_free_ram_gb']}"
    reserve = res.get("reserve_cpus")
    if reserve is not None:
        ncpu = psutil.cpu_count() or 1
        load = load_average()
        if load > ncpu - float(reserve):
            return False, f"load {load:.1f} > {ncpu} - {reserve}"
    limit = res.get("max_cpu_temp_c")
    if limit and temp is not None and temp > float(limit):
        return False, f"CPU {temp:.0f} C (1-min mean) > {limit} C"
    return True, ""


def read_control(cdir: Path, default_workers: int) -> dict:
    path = cdir / "control.yaml"
    ctrl = {"max_workers": default_workers, "pause": False}
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if data.get("max_workers") is not None:
                ctrl["max_workers"] = int(data["max_workers"])
            ctrl["pause"] = bool(data.get("pause", False))
        except (OSError, ValueError, yaml.YAMLError):
            pass
    return ctrl


def _spawn(task: Task, cdir: Path, prepared: Path, ledger: Ledger, res: dict) -> Running:
    threads = int(res.get("threads_per_worker", 1))
    env = os.environ.copy()
    for var in THREAD_VARS:
        env[var] = str(threads)
    env["PYTHONPATH"] = _SRC + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    tdir = ledger.task_dir(task.id)
    tdir.mkdir(parents=True, exist_ok=True)
    logfile = open(tdir / "worker.log", "ab")
    cmd = [sys.executable, "-m", "triagebench.runner.worker", "--campaign", str(cdir), "--prepared", str(prepared),
           "--task", task.id, "--threads", str(threads), "--nice", str(int(res.get("nice", 0)))]
    kwargs = {"start_new_session": True} if os.name == "posix" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    proc = subprocess.Popen(cmd, stdout=logfile, stderr=subprocess.STDOUT, env=env, **kwargs)
    ledger.mark_running(task.id, proc.pid)
    log.info("start %s (pid %d)", task.id, proc.pid)
    return Running(task, proc, time.time(), logfile)


def _kill(r: Running) -> None:
    try:
        if os.name == "posix":
            os.killpg(r.proc.pid, signal.SIGTERM)
        else:
            r.proc.terminate()
        r.proc.wait(timeout=30)
    except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
        try:
            r.proc.kill()
        except OSError:
            pass


def _set_suspended(running: dict[str, Running], suspend: bool) -> None:
    for r in running.values():
        if r.suspended == suspend:
            continue
        try:
            proc = psutil.Process(r.proc.pid)
            for p in [proc, *proc.children(recursive=True)]:
                p.suspend() if suspend else p.resume()
            r.suspended = suspend
        except psutil.Error:
            pass


def run_scheduler(cdir: Path, prepared: Path, tasks: list[Task], res: dict) -> dict:
    cdir = Path(cdir)
    ledger = Ledger(cdir)
    summary = Summary()
    max_attempts = int(res.get("max_attempts", 3))
    timeout_s = float(res.get("task_timeout_hours", 24)) * 3600
    poll = float(res.get("poll_seconds", 10))
    interval = float(res.get("launch_interval_seconds", 5))
    hard_temp = float(res["max_cpu_temp_c"]) + 10 if res.get("max_cpu_temp_c") else None
    stop = {"flag": False}

    def _handler(signum, frame):  # noqa: ARG001
        stop["flag"] = True
        log.warning("signal %s received: stopping after terminating workers", signum)

    old = {s: signal.signal(s, _handler) for s in (signal.SIGINT, signal.SIGTERM)}
    with campaign_lock(cdir):
        pending: list[Task] = []
        for t in tasks:
            if ledger.is_done(t.id):
                summary.skipped_done += 1
                continue
            st = ledger.state(t.id)
            if st.get("state") == "failed":
                summary.failed += 1
                summary.failed_ids.append(t.id)
                continue
            if st.get("state") == "running":  # stale from a crashed scheduler
                ledger.mark_finished(t.id, "pending", None, "interrupted (scheduler restart)", 0.0)
            pending.append(t)
        running: dict[str, Running] = {}
        last_launch, guard = 0.0, ""
        thermo = SmoothedTemperature(int(res.get("temp_window_polls", 6)))
        log.info("campaign %s: %d to run, %d already done, %d failed earlier", cdir.name, len(pending),
                 summary.skipped_done, summary.failed)

        while (pending or running) and not stop["flag"]:
            for tid, r in list(running.items()):
                code = r.proc.poll()
                elapsed = time.time() - r.started
                if code is None and elapsed > timeout_s:
                    _kill(r)
                    code, reason = -9, f"timeout after {elapsed / 3600:.1f} h"
                elif code is None:
                    continue
                else:
                    reason = "ok" if code == 0 else f"exit code {code}"
                r.logfile.close()
                del running[tid]
                if code == 0 and ledger.is_done(tid):
                    ledger.mark_finished(tid, "done", code, reason, elapsed)
                    summary.done += 1
                    log.info("done  %s (%.0f s)", tid, elapsed)
                    continue
                attempts = ledger.state(tid).get("attempts", 0)
                final = attempts >= max_attempts
                ledger.mark_finished(tid, "failed" if final else "pending", code, reason, elapsed)
                log.warning("%s %s (%s, attempt %d/%d)", "FAILED" if final else "retry", tid, reason, attempts, max_attempts)
                if final:
                    summary.failed += 1
                    summary.failed_ids.append(tid)
                else:
                    pending.append(r.task)

            temp = thermo.update() if res.get("max_cpu_temp_c") else None
            if hard_temp and temp is not None:
                if temp > hard_temp and not any(r.suspended for r in running.values()):
                    log.warning("thermal emergency %.0f C > %.0f C: suspending %d workers", temp, hard_temp, len(running))
                    _set_suspended(running, True)
                elif temp < float(res["max_cpu_temp_c"]) - 5 and any(r.suspended for r in running.values()):
                    log.info("temperature %.0f C: resuming workers", temp)
                    _set_suspended(running, False)

            ctrl = read_control(cdir, int(res.get("max_workers", 1)))
            if (not ctrl["pause"] and pending and len(running) < ctrl["max_workers"]
                    and time.time() - last_launch >= interval and not any(r.suspended for r in running.values())):
                ok, guard = resources_ok(res, cdir, temp)
                limits = res.get("max_concurrent_per_model") or {}
                active = [r.task.model for r in running.values()]
                idx = next((i for i, t in enumerate(pending)
                            if t.model not in limits or active.count(t.model) < int(limits[t.model])), None)
                if ok and idx is not None:
                    task = pending.pop(idx)
                    running[task.id] = _spawn(task, cdir, prepared, ledger, res)
                    last_launch = time.time()
                elif ok:
                    guard = "per-model concurrency limit"
            atomic_write_json(cdir / "scheduler.json", {
                "pid": os.getpid(), "host": socket.gethostname(), "updated_at": utc_now(),
                "running": {tid: {"pid": r.proc.pid, "elapsed_s": round(time.time() - r.started), "suspended": r.suspended}
                            for tid, r in running.items()},
                "pending": len(pending), "done_this_session": summary.done, "failed_total": summary.failed,
                "max_workers": ctrl["max_workers"], "paused": ctrl["pause"], "guard": guard,
                "cpu_temp_c": temp, "load1": round(load_average(), 2),
            })
            time.sleep(poll)

        if stop["flag"]:
            summary.interrupted = True
            for tid, r in list(running.items()):
                _kill(r)
                r.logfile.close()
                ledger.mark_finished(tid, "pending", None, "interrupted (signal)", time.time() - r.started)
        summary.pending = len(pending) + (len(running) if stop["flag"] else 0)
    for s, h in old.items():
        signal.signal(s, h)
    return summary.__dict__
