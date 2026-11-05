"""Task grid: one task per (variant, seed, model, strategy), in a priority order chosen so that
an early stop still leaves COMPLETE seeds: priority seeds of every variant first, then the rest;
within a seed, expensive models first (better packing on the worker pool)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from triagebench.models.imbalance import applicability
from triagebench.models.registry import get_spec
from triagebench.utils.config import all_models, primary_variant


@dataclass(frozen=True)
class Task:
    variant: str
    seed: int
    model: str
    strategy: str

    @property
    def id(self) -> str:
        return f"{self.variant}__s{self.seed:02d}__{self.model}__{self.strategy}"

    def as_dict(self) -> dict:
        return {**asdict(self), "id": self.id}

    @classmethod
    def from_id(cls, task_id: str) -> Task:
        variant, seed, model, strategy = task_id.split("__")
        return cls(variant, int(seed.lstrip("s")), model, strategy)


def build_grid(cfg: dict) -> tuple[list[Task], list[dict]]:
    """Return (runnable tasks in priority order, not-applicable combinations with the reason)."""
    seeds = list(cfg["split"]["seeds"])
    n_priority = int(cfg["split"].get("priority_seeds", len(seeds)))
    primary = primary_variant(cfg)
    variants = [primary] + [v for v in cfg["variants"] if v != primary]
    models = all_models(cfg)
    strategies = list(cfg["imbalance"]["strategies"])

    tasks, not_applicable = [], []
    for block in (0, 1):
        block_seeds = seeds[:n_priority] if block == 0 else seeds[n_priority:]
        for variant in variants:
            for seed in block_seeds:
                ordered = sorted(models, key=lambda m: (-get_spec(m).cost_rank, models.index(m)))
                for model in ordered:
                    for strategy in cfg["variants"][variant].get("strategies") or strategies:
                        ok, reason = applicability(model, strategy, cfg)
                        task = Task(variant, seed, model, strategy)
                        if ok:
                            tasks.append(task)
                        else:
                            not_applicable.append({**task.as_dict(), "reason": reason})
    return tasks, not_applicable


def filter_tasks(tasks: list[Task], filters: dict | None) -> list[Task]:
    if not filters:
        return tasks
    out = tasks
    if filters.get("variants"):
        out = [t for t in out if t.variant in filters["variants"]]
    if filters.get("seeds"):
        out = [t for t in out if t.seed in filters["seeds"]]
    if filters.get("models"):
        out = [t for t in out if t.model in filters["models"]]
    if filters.get("strategies"):
        out = [t for t in out if t.strategy in filters["strategies"]]
    return out
