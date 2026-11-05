"""Campaign status: progress per model x strategy, running tasks, failures and ETA.

Works whether or not a scheduler is alive (reads only files)."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from triagebench.runner.ledger import Ledger
from triagebench.runner.scheduler import read_control
from triagebench.utils.io import read_json


def _age_seconds(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return (datetime.now(UTC) - datetime.fromisoformat(iso)).total_seconds()
    except ValueError:
        return None


def campaign_status(cdir: Path) -> dict:
    cdir = Path(cdir)
    if not (cdir / "grid.json").exists():
        return {"campaign": cdir.name, "error": "campaign not initialised (no grid.json)"}
    grid = read_json(cdir / "grid.json")
    ledger = Ledger(cdir)
    sched = read_json(cdir / "scheduler.json") if (cdir / "scheduler.json").exists() else {}
    running_ids = set((sched.get("running") or {}).keys())
    sched_age = _age_seconds(sched.get("updated_at"))
    alive = sched_age is not None and sched_age < 300

    counts = defaultdict(lambda: {"done": 0, "running": 0, "failed": 0, "pending": 0})
    durations: dict[tuple, list[float]] = defaultdict(list)
    failures, pending_tasks = [], []
    for t in grid["tasks"]:
        key = (t["model"], t["strategy"])
        tid = t["id"]
        if ledger.is_done(tid):
            counts[key]["done"] += 1
            try:
                durations[key].append(read_json(ledger.task_dir(tid) / "result.json")["timing"]["task_seconds"])
            except (OSError, KeyError, ValueError):
                pass
            continue
        st = ledger.state(tid)
        if st.get("state") == "failed":
            counts[key]["failed"] += 1
            err = ledger.task_dir(tid) / "error.json"
            failures.append({"task": tid, "attempts": st.get("attempts"),
                             "error": read_json(err).get("error") if err.exists() else (st.get("history") or [{}])[-1].get("reason")})
        elif alive and tid in running_ids:
            counts[key]["running"] += 1
            pending_tasks.append((key, (sched["running"][tid] or {}).get("elapsed_s", 0)))
        else:
            counts[key]["pending"] += 1
            pending_tasks.append((key, 0))

    all_d = [d for v in durations.values() for d in v]
    global_med = statistics.median(all_d) if all_d else None
    by_model: dict[str, list[float]] = defaultdict(list)
    for (model, _), v in durations.items():
        by_model[model] += v
    remaining, unknown = 0.0, 0
    for key, elapsed in pending_tasks:
        est = (statistics.median(durations[key]) if durations.get(key)
               else statistics.median(by_model[key[0]]) if by_model.get(key[0]) else global_med)
        if est is None:
            unknown += 1
            continue
        remaining += max(est - elapsed, 0.1 * est)
    workers = max(1, read_control(cdir, 1)["max_workers"])
    total = sum(sum(c.values()) for c in counts.values())
    done = sum(c["done"] for c in counts.values())
    return {
        "campaign": cdir.name, "scheduler_alive": alive, "scheduler": sched, "total": total, "done": done,
        "failed": sum(c["failed"] for c in counts.values()), "running": sum(c["running"] for c in counts.values()),
        "pending": sum(c["pending"] for c in counts.values()), "progress": done / total if total else 0.0,
        "eta_hours": remaining / workers / 3600 if pending_tasks else 0.0, "eta_unknown_tasks": unknown,
        "by_model_strategy": {f"{m}/{s}": c for (m, s), c in sorted(counts.items())},
        "failures": failures, "not_applicable": len(grid.get("not_applicable", [])),
        "compute_hours_done": sum(all_d) / 3600,
    }


def render_status(st: dict) -> str:
    if "error" in st:
        return f"{st['campaign']}: {st['error']}"
    sched = st["scheduler"] or {}
    lines = [
        f"campaign {st['campaign']}",
        f"  progress  {st['done']}/{st['total']} done ({100 * st['progress']:.1f}%), {st['running']} running, "
        f"{st['pending']} pending, {st['failed']} failed, {st['not_applicable']} not applicable",
        f"  scheduler {'ALIVE' if st['scheduler_alive'] else 'not running'}"
        + (f" on {sched.get('host')} pid {sched.get('pid')}, updated {sched.get('updated_at')}, workers<= {sched.get('max_workers')}"
           f"{' PAUSED' if sched.get('paused') else ''}, load {sched.get('load1')}, cpu {sched.get('cpu_temp_c')} C"
           + (f", guard: {sched['guard']}" if sched.get('guard') else "") if sched else ""),
        f"  ETA       ~{st['eta_hours']:.1f} h at the current worker limit"
        + (f" ({st['eta_unknown_tasks']} tasks without a duration estimate yet)" if st["eta_unknown_tasks"] else ""),
        f"  compute   {st['compute_hours_done']:.1f} task-hours finished",
        "", f"  {'model/strategy':32s} done  run  pend  fail",
    ]
    for key, c in st["by_model_strategy"].items():
        lines.append(f"  {key:32s} {c['done']:4d} {c['running']:4d} {c['pending']:5d} {c['failed']:5d}")
    if st["failures"]:
        lines += ["", "  FAILURES:"] + [f"   - {f['task']} ({f['attempts']} attempts): {str(f['error'])[:160]}" for f in st["failures"]]
    if sched.get("running"):
        lines += ["", "  RUNNING:"] + [f"   - {tid} {v.get('elapsed_s', 0) / 60:.0f} min{' (suspended)' if v.get('suspended') else ''}"
                                       for tid, v in sched["running"].items()]
    return "\n".join(lines)
