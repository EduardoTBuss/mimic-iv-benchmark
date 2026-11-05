"""Worker process: runs ONE task and exits (0 = done, 1 = failed).

Started by the scheduler as ``python -m triagebench.runner.worker``. Thread-count environment
variables are set by the scheduler BEFORE this interpreter imports numpy.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

import yaml

from triagebench.utils.io import atomic_write_json, read_json, touch_atomic, utc_now


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="triagebench.runner.worker")
    p.add_argument("--campaign", required=True)
    p.add_argument("--prepared", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--nice", type=int, default=0)
    args = p.parse_args(argv)

    if os.name == "posix":
        os.umask(0o077)
        if args.nice:
            try:
                os.nice(args.nice)
            except OSError:
                pass

    cdir = Path(args.campaign)
    from triagebench.evaluation.protocol import TaskContext, run_task
    from triagebench.runner.tasks import Task

    task = Task.from_id(args.task)
    task_dir = cdir / "tasks" / task.id
    task_dir.mkdir(parents=True, exist_ok=True)
    try:
        cfg = yaml.safe_load((cdir / "config.resolved.yaml").read_text(encoding="utf-8"))
        meta = read_json(cdir / "campaign.json")
        ctx = TaskContext(cfg=cfg, campaign_dir=cdir, prepared_dir=Path(args.prepared), threads=args.threads,
                          science_hash=meta["science_hash"])
        result = run_task(task, ctx)
        result["campaign_id"] = meta["campaign_id"]
        atomic_write_json(task_dir / "result.json", result)
        touch_atomic(task_dir / "DONE")
        return 0
    except Exception as exc:
        atomic_write_json(task_dir / "error.json", {
            "at": utc_now(), "error": f"{type(exc).__name__}: {exc}"[:2000], "traceback": traceback.format_exc()[-8000:],
        })
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
