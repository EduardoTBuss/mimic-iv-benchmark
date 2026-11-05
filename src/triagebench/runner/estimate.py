"""Project the cost of the main campaign from a pilot campaign (same data, fewer configs/seeds)."""

from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path

from triagebench.reporting.tables import md_table
from triagebench.runner.tasks import build_grid
from triagebench.utils.io import read_json, read_jsonl


def estimate_from_pilot(cfg: dict, pilot_dir: Path, workers: int = 8) -> str:
    per_trial: dict[tuple, list[float]] = defaultdict(list)
    final: dict[tuple, list[float]] = defaultdict(list)
    for d in sorted((Path(pilot_dir) / "tasks").glob("*")):
        variant, _, model, strategy = d.name.split("__")
        for t in read_jsonl(d / "trials.jsonl"):
            if t.get("status") == "ok":
                per_trial[(model, strategy)].append(t["fit_seconds"] + t["predict_val_seconds"])
        if (d / "result.json").exists():
            r = read_json(d / "result.json")["timing"]
            final[(model, strategy)].append(r["final_fit_seconds"] + r["predict_val_seconds"] + r["predict_test_seconds"])

    n_configs = int(cfg["hpo"]["n_configs"])
    tasks, _ = build_grid(cfg)
    by_key: dict[tuple, int] = defaultdict(int)
    for t in tasks:
        by_key[(t.model, t.strategy)] += 1
    rows, total, longest, missing = [], 0.0, 0.0, []
    for key, n_tasks in sorted(by_key.items()):
        if key not in per_trial:
            missing.append(f"{key[0]}/{key[1]}")
            continue
        trial = statistics.mean(per_trial[key])
        fin = statistics.mean(final[key]) if final.get(key) else trial
        task_s = n_configs * trial + fin
        total += task_s * n_tasks
        longest = max(longest, task_s)
        rows.append([f"{key[0]}/{key[1]}", n_tasks, f"{trial:.1f}", f"{task_s / 3600:.2f}", f"{task_s * n_tasks / 3600:.1f}"])
    rows.sort(key=lambda r: -float(r[-1]))
    wall = max(total / max(workers, 1), longest)
    head = (f"Projeção da campanha a partir do piloto `{Path(pilot_dir).name}` (média por trial; {n_configs} configs + ajuste final; "
            f"{len(tasks)} tarefas):\n\n")
    tail = (f"\n\n**Total ≈ {total / 3600:.0f} horas de núcleo** → com {workers} workers ≈ **{wall / 3600:.1f} h de parede** "
            f"(limite inferior = tarefa mais longa {longest / 3600:.1f} h).")
    if missing:
        tail += f"\n\nSem medida no piloto (não incluídos): {', '.join(missing)}."
    return head + md_table(["modelo/estratégia", "tarefas", "s por trial", "h por tarefa", "h totais"], rows) + tail
