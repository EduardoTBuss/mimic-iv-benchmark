"""Merge finished tasks of the SAME campaign computed on another machine (e.g. x299 -> Q-FLEX).

Only DONE tasks are copied; a task already DONE in the destination is never overwritten.
Requires the same scientific configuration (identical science hash). Idempotent.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from triagebench.runner.ledger import Ledger
from triagebench.utils.io import atomic_write_json, read_json, utc_now


def merge_campaign(dst: Path, src: Path) -> dict:
    dst, src = Path(dst), Path(src)
    a, b = read_json(dst / "campaign.json"), read_json(src / "campaign.json")
    if a["science_hash"] != b["science_hash"]:
        raise RuntimeError(f"different scientific configurations: {a['science_hash'][:12]} vs {b['science_hash'][:12]}")
    ledger = Ledger(dst)
    src_hosts = sorted({s["environment"]["hardware"]["hostname"] for s in read_json(src / "manifest.json").get("sessions", [])
                        if s.get("environment")}) if (src / "manifest.json").exists() else []
    copied, skipped = [], []
    for d in sorted((src / "tasks").glob("*")):
        if not ((d / "DONE").exists() and (d / "result.json").exists()):
            continue
        if ledger.is_done(d.name):
            skipped.append(d.name)
            continue
        target = ledger.task_dir(d.name)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(d, target)
        st = ledger.state(d.name)
        st["state"] = "done"
        st.setdefault("history", []).append({"merged_from": src_hosts, "merged_at": utc_now()})
        ledger.write_state(d.name, st)
        copied.append(d.name)
    if (src / "manifest.json").exists():
        man = read_json(dst / "manifest.json")
        seen = {s.get("started_at") for s in man.get("sessions", [])}
        for s in read_json(src / "manifest.json").get("sessions", []):
            if s.get("started_at") not in seen:
                man["sessions"].append({**s, "merged_from": src_hosts})
        atomic_write_json(dst / "manifest.json", man)
    return {"copied": len(copied), "skipped_already_done": len(skipped), "from_hosts": src_hosts}
