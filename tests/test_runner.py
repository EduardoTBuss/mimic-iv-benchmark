"""Runner: task grid, ledger, campaign lock, scheduler (retries, timeouts, skip DONE) and an
end-to-end crash/resume campaign with REAL worker subprocesses on SYNTHETIC data."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import psutil
import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests._helpers import comparable, make_cfg, make_ctx, trial_indices
from tests.conftest import REPO
from triagebench.evaluation.protocol import run_task
from triagebench.runner import scheduler as sched
from triagebench.runner.ledger import Ledger, RunnerLockedError, campaign_lock
from triagebench.runner.pipeline import run_tasks
from triagebench.runner.status import campaign_status
from triagebench.runner.tasks import Task, build_grid, filter_tasks
from triagebench.utils.config import load_config
from triagebench.utils.io import atomic_write_json, read_json, read_jsonl

MAIN = load_config(REPO / "configs" / "main.yaml")


# --------------------------------------------------------------------------- tasks / grid

name = st.from_regex(r"[A-Za-z][A-Za-z0-9]*(_[A-Za-z0-9]+)*", fullmatch=True)


@given(variant=name, seed=st.integers(0, 999), model=name, strategy=name)
def test_task_id_round_trip(variant, seed, model, strategy):
    t = Task(variant, seed, model, strategy)
    assert Task.from_id(t.id) == t


def test_grid_is_complete_unique_and_respects_applicability():
    tasks, na = build_grid(MAIN)
    ids = [t.id for t in tasks]
    assert len(ids) == len(set(ids))
    for t in tasks:
        if t.model in MAIN["models"]["reference"]:
            assert t.strategy == "none"
        if t.variant == "C_values_only":
            assert t.strategy == "none"
    assert not any(t.model == "knn" and t.strategy == "class_weight" for t in tasks)
    assert {(d["model"], d["strategy"]) for d in na} >= {("knn", "class_weight"), ("dummy_prior", "oversample")}
    n_models = len(MAIN["models"]["primary"]) + len(MAIN["models"]["extra"]) + len(MAIN["models"]["reference"])
    per_seed_ab = n_models * 3 - len({(d["model"], d["strategy"]) for d in na if d["variant"] == "A_keep_encode"
                                      and d["seed"] == 1})
    assert len(tasks) == 10 * (2 * per_seed_ab + n_models)


def test_grid_priority_order():
    tasks, _ = build_grid(MAIN)
    n_prio = MAIN["split"]["priority_seeds"]
    prio_seeds = set(MAIN["split"]["seeds"][:n_prio])
    first_late = next(i for i, t in enumerate(tasks) if t.seed not in prio_seeds)
    assert all(t.seed not in prio_seeds for t in tasks[first_late:])     # complete priority seeds first
    assert tasks[0].variant == "A_keep_encode"                            # primary variant first
    from triagebench.models.registry import get_spec

    block = [t for t in tasks if t.variant == "A_keep_encode" and t.seed == 1]
    ranks = [get_spec(t.model).cost_rank for t in block]
    assert ranks == sorted(ranks, reverse=True)                           # expensive models first


def test_filter_tasks():
    tasks, _ = build_grid(MAIN)
    out = filter_tasks(tasks, {"variants": ["B_pain_numeric_only"], "seeds": [3], "models": ["gnb"],
                               "strategies": ["class_weight"]})
    assert [t.id for t in out] == ["B_pain_numeric_only__s03__gnb__class_weight"]
    assert filter_tasks(tasks, None) == tasks
    assert filter_tasks(tasks, {"models": ["nope"]}) == []


# --------------------------------------------------------------------------- ledger / lock

def test_ledger_done_requires_both_files(tmp_path):
    led = Ledger(tmp_path)
    d = led.task_dir("t")
    d.mkdir(parents=True)
    (d / "DONE").write_text("x")
    assert not led.is_done("t")
    atomic_write_json(d / "result.json", {})
    assert led.is_done("t")
    (d / "DONE").unlink()
    assert not led.is_done("t")


def test_ledger_state_transitions_and_corrupt_state(tmp_path):
    led = Ledger(tmp_path)
    assert led.state("t") == {"state": "pending", "attempts": 0, "history": []}
    led.mark_running("t", pid=123)
    led.mark_finished("t", "pending", 1, "exit code 1", 1.0)
    st_ = led.mark_running("t", pid=124)
    assert st_["attempts"] == 2 and st_["pid"] == 124
    st_ = led.mark_finished("t", "done", 0, "ok", 2.0)
    assert st_["state"] == "done" and "pid" not in st_
    assert [h["exit_code"] for h in st_["history"]] == [1, 0]
    (led.task_dir("t") / "state.json").write_text('{"state": "runn', encoding="utf-8")   # torn write
    assert led.state("t")["state"] == "pending"


def _dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_campaign_lock_lifecycle(tmp_path):
    with campaign_lock(tmp_path) as me:
        assert read_json(tmp_path / "runner.lock")["pid"] == me["pid"]
    assert not (tmp_path / "runner.lock").exists()


def test_campaign_lock_takes_over_a_stale_lock(tmp_path):
    import socket

    atomic_write_json(tmp_path / "runner.lock", {"pid": _dead_pid(), "host": socket.gethostname()})
    with campaign_lock(tmp_path):
        pass


def test_campaign_lock_refuses_a_live_owner_and_another_host(tmp_path):
    import socket

    owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        atomic_write_json(tmp_path / "runner.lock", {"pid": owner.pid, "host": socket.gethostname()})
        with pytest.raises(RunnerLockedError, match="already running"):
            with campaign_lock(tmp_path):
                pass
        assert read_json(tmp_path / "runner.lock")["pid"] == owner.pid    # not stolen
    finally:
        owner.kill()
        owner.wait()
    atomic_write_json(tmp_path / "runner.lock", {"pid": 1, "host": "other-host"})
    with pytest.raises(RunnerLockedError, match="another host"):
        with campaign_lock(tmp_path):
            pass


def test_corrupt_lock_file_does_not_block(tmp_path):
    (tmp_path / "runner.lock").write_text("{garbage", encoding="utf-8")
    with campaign_lock(tmp_path):
        pass


# --------------------------------------------------------------------------- scheduler with fake workers

FAST_RES = {"max_workers": 2, "threads_per_worker": 1, "reserve_cpus": None, "min_free_ram_gb": 0,
            "min_free_disk_gb": 0, "max_cpu_temp_c": None, "nice": 0, "task_timeout_hours": 24,
            "max_attempts": 2, "poll_seconds": 0.05, "launch_interval_seconds": 0}

FAKE_WORKER = textwrap.dedent("""
    import json, os, sys, time
    tdir, behaviour = sys.argv[1], sys.argv[2]
    with open(os.path.join(tdir, "runs.log"), "a") as fh:
        fh.write(f"start {time.time()}\\n")
    if behaviour == "ok":
        time.sleep(0.2)
        with open(os.path.join(tdir, "result.json"), "w") as fh:
            json.dump({"ok": True}, fh)
        open(os.path.join(tdir, "DONE"), "w").close()
    elif behaviour == "exit0_without_done":
        pass
    elif behaviour == "hang":
        time.sleep(60)
    with open(os.path.join(tdir, "runs.log"), "a") as fh:
        fh.write(f"end {time.time()}\\n")
    sys.exit(0 if behaviour in ("ok", "exit0_without_done") else 3)
""")


@pytest.fixture()
def fake_spawn(monkeypatch, tmp_path):
    script = tmp_path / "fake_worker.py"
    script.write_text(FAKE_WORKER, encoding="utf-8")
    behaviours: dict[str, str] = {}
    spawned: list[str] = []

    def spawn(task, cdir, prepared, ledger, res):
        tdir = ledger.task_dir(task.id)
        tdir.mkdir(parents=True, exist_ok=True)
        logfile = open(tdir / "worker.log", "ab")
        proc = subprocess.Popen([sys.executable, str(script), str(tdir), behaviours.get(task.id, "ok")],
                                stdout=logfile, stderr=subprocess.STDOUT)
        ledger.mark_running(task.id, proc.pid)
        spawned.append(task.id)
        return sched.Running(task, proc, time.time(), logfile)

    monkeypatch.setattr(sched, "_spawn", spawn)
    return behaviours, spawned


def _tasks(n, model="dtree"):
    return [Task("A_keep_encode", s, model, "none") for s in range(1, n + 1)]


def test_scheduler_runs_everything_and_skips_done_on_rerun(tmp_path, fake_spawn):
    _, spawned = fake_spawn
    tasks = _tasks(3)
    s1 = sched.run_scheduler(tmp_path, tmp_path, tasks, FAST_RES)
    assert s1["done"] == 3 and s1["failed"] == 0 and not s1["interrupted"]
    led = Ledger(tmp_path)
    assert all(led.is_done(t.id) and led.state(t.id)["state"] == "done" for t in tasks)
    spawned.clear()
    s2 = sched.run_scheduler(tmp_path, tmp_path, tasks, FAST_RES)
    assert s2["skipped_done"] == 3 and s2["done"] == 0 and spawned == []
    assert not (tmp_path / "runner.lock").exists()


def test_scheduler_retries_then_marks_failed_and_never_retries_across_sessions(tmp_path, fake_spawn):
    behaviours, spawned = fake_spawn
    tasks = _tasks(2)
    behaviours[tasks[0].id] = "crash"
    s = sched.run_scheduler(tmp_path, tmp_path, tasks, FAST_RES)
    assert s["done"] == 1 and s["failed"] == 1 and s["failed_ids"] == [tasks[0].id]
    st_ = Ledger(tmp_path).state(tasks[0].id)
    assert st_["state"] == "failed" and st_["attempts"] == FAST_RES["max_attempts"]
    assert [h["exit_code"] for h in st_["history"]] == [3, 3]
    assert spawned.count(tasks[0].id) == FAST_RES["max_attempts"]
    spawned.clear()
    s = sched.run_scheduler(tmp_path, tmp_path, tasks, FAST_RES)
    assert spawned == [] and s["failed"] == 1 and s["skipped_done"] == 1


def test_scheduler_treats_exit0_without_done_as_failure(tmp_path, fake_spawn):
    behaviours, _ = fake_spawn
    t = _tasks(1)
    behaviours[t[0].id] = "exit0_without_done"
    s = sched.run_scheduler(tmp_path, tmp_path, t, FAST_RES)
    assert s["failed"] == 1 and not Ledger(tmp_path).is_done(t[0].id)


def test_scheduler_kills_a_hung_worker_on_timeout(tmp_path, fake_spawn):
    behaviours, _ = fake_spawn
    t = _tasks(1)
    behaviours[t[0].id] = "hang"
    res = {**FAST_RES, "task_timeout_hours": 0.5 / 3600, "max_attempts": 1}
    t0 = time.time()
    s = sched.run_scheduler(tmp_path, tmp_path, t, res)
    assert time.time() - t0 < 30
    st_ = Ledger(tmp_path).state(t[0].id)
    assert s["failed"] == 1 and st_["state"] == "failed"
    assert st_["history"][-1]["reason"].startswith("timeout")
    log = (Ledger(tmp_path).task_dir(t[0].id) / "runs.log").read_text()
    assert "end" not in log                      # really killed, did not finish its sleep


def test_scheduler_recovers_stale_running_state_from_a_crashed_scheduler(tmp_path, fake_spawn):
    t = _tasks(1)
    led = Ledger(tmp_path)
    led.mark_running(t[0].id, pid=_dead_pid())
    s = sched.run_scheduler(tmp_path, tmp_path, t, FAST_RES)
    st_ = led.state(t[0].id)
    assert s["done"] == 1 and st_["state"] == "done"
    assert st_["history"][0]["reason"] == "interrupted (scheduler restart)"


def test_scheduler_respects_max_workers(tmp_path, fake_spawn):
    tasks = _tasks(4)
    sched.run_scheduler(tmp_path, tmp_path, tasks, {**FAST_RES, "max_workers": 1})
    spans = []
    for t in tasks:
        lines = (Ledger(tmp_path).task_dir(t.id) / "runs.log").read_text().split()
        spans.append((float(lines[1]), float(lines[3])))
    spans.sort()
    assert all(spans[i][1] <= spans[i + 1][0] for i in range(len(spans) - 1)), spans


def test_scheduler_pause_via_control_file_launches_nothing(tmp_path, fake_spawn):
    _, spawned = fake_spawn
    (tmp_path / "control.yaml").write_text("pause: true\n", encoding="utf-8")

    seen_while_paused: list[list[str]] = []

    def unpause():
        time.sleep(1.0)
        seen_while_paused.append(list(spawned))
        (tmp_path / "control.yaml").write_text("pause: false\n", encoding="utf-8")

    th = threading.Thread(target=unpause)
    th.start()
    s = sched.run_scheduler(tmp_path, tmp_path, _tasks(1), FAST_RES)
    th.join()
    assert seen_while_paused == [[]]           # asserted in the main thread (thread asserts are lost)
    assert s["done"] == 1


def test_status_counts(tmp_path, fake_spawn):
    behaviours, _ = fake_spawn
    tasks = _tasks(3)
    behaviours[tasks[2].id] = "crash"
    atomic_write_json(tmp_path / "grid.json", {"tasks": [t.as_dict() for t in tasks + _tasks(4)[3:]],
                                               "not_applicable": []})
    sched.run_scheduler(tmp_path, tmp_path, tasks, FAST_RES)
    st_ = campaign_status(tmp_path)
    assert (st_["total"], st_["done"], st_["failed"], st_["pending"]) == (4, 2, 1, 1)


# --------------------------------------------------------------------------- end-to-end with real workers

SLOW_HOOK = textwrap.dedent("""
    # Test-only hook (loaded via PYTHONPATH in worker subprocesses): sleep after each journaled
    # HPO trial so that a test can kill a worker deterministically between two trials.
    import os
    if os.environ.get("TRIAGEBENCH_TEST_TRIAL_SLEEP"):
        import time
        from triagebench.evaluation import protocol as _p
        _orig = _p.append_jsonl
        def _slow(path, obj):
            _orig(path, obj)
            time.sleep(float(os.environ["TRIAGEBENCH_TEST_TRIAL_SLEEP"]))
        _p.append_jsonl = _slow
""")

E2E_FILTERS = {"variants": ["A_keep_encode"], "seeds": [1], "models": ["logreg", "dtree"]}
E2E_OVERRIDES = ["split.seeds=[1]", "split.priority_seeds=1", "hpo.n_configs=2", "resources.reserve_cpus=null",
                 "resources.min_free_ram_gb=0", "resources.min_free_disk_gb=0", "resources.max_workers=2",
                 "resources.poll_seconds=0.2", "resources.max_attempts=3",
                 "evaluation.cost_benchmark.enabled=false"]


@pytest.fixture()
def e2e(tmp_path, synthetic_zip, monkeypatch):
    hook = tmp_path / "hook"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(SLOW_HOOK, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(hook))
    monkeypatch.setenv("TRIAGEBENCH_TEST_TRIAL_SLEEP", "1.5")
    # Short root on purpose: pyarrow is not long-path aware on Windows (MAX_PATH = 260) and a task's
    # ".../tasks/<task id>/private/.predictions.parquet.tmp-<pid>" already uses ~130 characters.
    work = Path(tempfile.mkdtemp(prefix="tb-"))
    try:
        yield make_cfg(work, synthetic_zip, overrides=E2E_OVERRIDES)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _campaign_tasks(cdir: Path) -> list[Path]:
    return sorted(p for p in (cdir / "tasks").iterdir() if p.is_dir())


def _wait_for(pred, timeout=120.0, every=0.05):
    t0 = time.time()
    while time.time() - t0 < timeout:
        out = pred()
        if out:
            return out
        time.sleep(every)
    raise TimeoutError("condition not reached")


def _mid_task_worker(cdir: Path):
    """(task_dir, pid) of a worker that journaled exactly one trial and has not finished."""
    root = cdir / "tasks"
    if not root.exists():
        return None
    for d in root.iterdir():
        try:
            if (d / "DONE").exists() or len(read_jsonl(d / "trials.jsonl")) != 1:
                continue
            st_ = read_json(d / "state.json")
        except (OSError, ValueError):
            continue
        if st_.get("state") == "running" and st_.get("pid"):
            return d, int(st_["pid"])
    return None


def _kill_tree(pid: int) -> None:
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    procs = [*root.children(recursive=True), root]
    for p in procs:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(procs, timeout=15)


def _assert_campaign_complete(cdir: Path, n_tasks: int, n_configs: int = 2) -> None:
    dirs = _campaign_tasks(cdir)
    assert len(dirs) == n_tasks
    for d in dirs:
        assert (d / "DONE").exists() and (d / "result.json").exists(), d.name
        idx = trial_indices(d / "trials.jsonl")
        assert len(idx) == len(set(idx)), f"duplicated trial in {d.name}: {idx}"
        assert set(idx) <= set(range(n_configs))
        res = read_json(d / "result.json")
        assert res["task"]["id"] == d.name
        assert read_json(d / "test_access.json")["frozen_config_hash"] == res["frozen_config_hash"]


@pytest.mark.slow
def test_e2e_worker_killed_mid_task_is_retried_and_rerun_skips_done(e2e, tmp_path):
    cfg = e2e
    cdir_box: dict = {}
    killed: dict = {}

    def killer():
        def find():
            camps = Path(cfg["paths"]["outputs"]) / "campaigns"
            if not camps.exists():
                return None
            for c in camps.iterdir():
                hit = _mid_task_worker(c)
                if hit:
                    cdir_box["cdir"] = c
                    return hit
            return None

        try:
            d, pid = _wait_for(find)
        except TimeoutError:
            return
        _kill_tree(pid)
        killed.update(task=d.name, pid=pid)

    th = threading.Thread(target=killer, daemon=True)
    th.start()
    summary = run_tasks(cfg, filters=E2E_FILTERS)
    th.join(timeout=5)
    assert killed, "the test never managed to kill a worker mid-task"
    cdir = Path(summary["campaign"])
    assert summary["done"] == 6 and summary["failed"] == 0 and not summary["interrupted"]
    _assert_campaign_complete(cdir, 6)

    st_ = Ledger(cdir).state(killed["task"])
    assert st_["state"] == "done" and st_["attempts"] == 2
    assert st_["history"][0]["exit_code"] not in (0, None)
    # resumed from the journal: trial 0 written once, trial 1 by the second attempt
    assert trial_indices(cdir / "tasks" / killed["task"] / "trials.jsonl") == [0, 1]

    # the retried task gives exactly the result of an uninterrupted in-process run
    task = Task.from_id(killed["task"])
    meta = read_json(cdir / "campaign.json")
    prepared = Path(cfg["paths"]["outputs"]) / "prepared" / meta["prepared_id"]
    clean = run_task(task, make_ctx(cfg, prepared, tmp_path / "clean"))
    assert comparable(read_json(cdir / "tasks" / killed["task"] / "result.json")) == json.loads(
        json.dumps(comparable(clean)))

    # relaunch: everything is DONE -> nothing re-run, nothing rewritten
    before = {d.name: (d / "result.json").read_bytes() for d in _campaign_tasks(cdir)}
    again = run_tasks(cfg, filters=E2E_FILTERS)
    assert again["skipped_done"] == 6 and again["done"] == 0
    assert {d.name: (d / "result.json").read_bytes() for d in _campaign_tasks(cdir)} == before
    assert len(read_json(cdir / "manifest.json")["sessions"]) == 2
    status = campaign_status(cdir)
    assert status["failed"] == 0 and status["running"] == 0


RUNNER_SCRIPT = textwrap.dedent("""
    import json, sys
    from triagebench.utils.config import load_config
    from triagebench.runner.pipeline import run_tasks
    args = json.loads(sys.argv[1])
    cfg = load_config(args["config"], "smoke", args["overrides"])
    run_tasks(cfg, filters=args["filters"])
""")


@pytest.mark.slow
def test_e2e_whole_campaign_killed_then_relaunched_completes_without_duplicates(e2e, tmp_path, monkeypatch):
    cfg = e2e
    script = tmp_path / "run_campaign.py"
    script.write_text(RUNNER_SCRIPT, encoding="utf-8")
    overrides = [*cfg["_meta"]["overrides"]]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO / "src"), os.environ["PYTHONPATH"]])}
    proc = subprocess.Popen([sys.executable, str(script),
                             json.dumps({"config": str(REPO / "configs" / "main.yaml"), "overrides": overrides,
                                         "filters": E2E_FILTERS})], env=env)
    camps = Path(cfg["paths"]["outputs"]) / "campaigns"
    try:
        def ready():
            if not camps.exists():
                return None
            for c in camps.iterdir():
                if not (c / "tasks").exists():
                    continue
                done = [d for d in (c / "tasks").iterdir() if (d / "DONE").exists()]
                if done and _mid_task_worker(c):
                    return c
            return None

        cdir = _wait_for(ready, timeout=180)
    finally:
        _kill_tree(proc.pid)                          # kill -9 the scheduler AND its workers
    done_before = {d.name: (d / "result.json").read_bytes() for d in _campaign_tasks(cdir) if (d / "DONE").exists()}
    assert 1 <= len(done_before) < 6
    assert (cdir / "runner.lock").exists()           # stale lock left behind by the dead scheduler

    monkeypatch.delenv("TRIAGEBENCH_TEST_TRIAL_SLEEP")
    summary = run_tasks(cfg, filters=E2E_FILTERS)     # relaunch in-process (no slow-down hook)
    assert summary["failed"] == 0 and not summary["interrupted"]
    assert summary["skipped_done"] == len(done_before)
    assert summary["done"] == 6 - len(done_before)
    _assert_campaign_complete(cdir, 6)
    for name, data in done_before.items():            # DONE tasks untouched
        assert (cdir / "tasks" / name / "result.json").read_bytes() == data
    for d in _campaign_tasks(cdir):
        access = read_json(d / "test_access.json")
        assert access["reaccess_same_config"] <= 1
