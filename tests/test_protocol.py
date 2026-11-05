"""Evaluation protocol: test partition used once, selection on validation only, crash-resume of
the HPO journal, and golden regression of run_task. SYNTHETIC data only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests._helpers import comparable, make_cfg, make_ctx, metrics_digest, prepare, trial_indices
from triagebench.evaluation import protocol
from triagebench.evaluation import test_guard as tg  # alias: pytest must not collect TestAccessError
from triagebench.evaluation.protocol import run_task
from triagebench.runner.tasks import Task
from triagebench.utils.io import read_json, read_jsonl

N_CONFIGS = 4


@pytest.fixture(scope="module")
def env(tmp_path_factory, synthetic_zip):
    root = tmp_path_factory.mktemp("proto")
    cfg = make_cfg(root, synthetic_zip, overrides=[f"hpo.n_configs={N_CONFIGS}"])
    ingest, prepared = prepare(cfg)
    return {"cfg": cfg, "prepared": prepared, "ingest": ingest}


def _run(env, campaign_dir: Path, model="dtree", strategy="none", seed=1, variant="A_keep_encode"):
    task = Task(variant, seed, model, strategy)
    return task, run_task(task, make_ctx(env["cfg"], env["prepared"], campaign_dir))


class Interrupted(BaseException):
    """Simulates SIGKILL/OOM inside a worker: NOT an Exception, so run_task cannot journal it."""


# --------------------------------------------------------------------------- 5. guard

def test_guard_first_access_creates_record(tmp_path):
    rec = tg.guard_test_access(tmp_path, "a" * 64)
    assert rec["frozen_config_hash"] == "a" * 64
    assert rec["reaccess_same_config"] == 0
    assert read_json(tmp_path / "test_access.json")["frozen_config_hash"] == "a" * 64


def test_guard_allows_reaccess_with_same_hash_and_counts_it(tmp_path):
    tg.guard_test_access(tmp_path, "h1")
    rec = tg.guard_test_access(tmp_path, "h1")
    rec = tg.guard_test_access(tmp_path, "h1")
    assert rec["reaccess_same_config"] == 2
    assert "last_access_at" in rec


def test_guard_refuses_a_different_configuration_and_keeps_the_record(tmp_path):
    tg.guard_test_access(tmp_path, "h1")
    before = (tmp_path / "test_access.json").read_bytes()
    with pytest.raises(tg.TestAccessError):
        tg.guard_test_access(tmp_path, "h2")
    assert (tmp_path / "test_access.json").read_bytes() == before


def test_run_task_writes_test_access_and_outputs(env, tmp_path):
    task, res = _run(env, tmp_path, model="logreg")
    tdir = tmp_path / "tasks" / task.id
    access = read_json(tdir / "test_access.json")
    assert access["frozen_config_hash"] == res["frozen_config_hash"]
    assert res["test_access"]["reaccess_same_config"] == 0
    assert sorted(trial_indices(tdir / "trials.jsonl")) == list(range(N_CONFIGS))
    preds = pd.read_parquet(tdir / "private" / "predictions.parquet")
    assert len(preds) == res["data"]["n_val"] + res["data"]["n_test"]
    assert {f"proba_{k}" for k in range(1, 6)} <= set(preds.columns)
    np.testing.assert_allclose(preds[[f"proba_{k}" for k in range(1, 6)]].sum(axis=1), 1.0, atol=1e-5)
    # the frozen config is the journaled best trial
    best = next(t for t in read_jsonl(tdir / "trials.jsonl") if t["index"] == res["best_trial_index"])
    assert best["params"] == res["frozen_config"]["params"]
    ok = [t for t in read_jsonl(tdir / "trials.jsonl") if t["status"] == "ok"]
    assert best["val"]["macro_f1"] == max(t["val"]["macro_f1"] for t in ok)


def test_rerun_of_finished_task_reuses_journal_and_same_frozen_config(env, tmp_path, monkeypatch):
    task, first = _run(env, tmp_path)
    calls = []
    original = protocol._fit_predict
    monkeypatch.setattr(protocol, "_fit_predict", lambda *a: calls.append(len(a[-2])) or original(*a))
    _, second = _run(env, tmp_path)
    assert calls == [1]                        # no HPO trial re-run: only the final refit (val; test is predicted after the guard)
    assert second["test_access"]["reaccess_same_config"] == 1
    assert comparable(first) == comparable(second)


def test_journal_tampering_that_changes_the_winner_is_refused_by_the_guard(env, tmp_path):
    task, first = _run(env, tmp_path)
    path = tmp_path / "tasks" / task.id / "trials.jsonl"
    rows = read_jsonl(path)
    loser = next(t for t in rows if t["index"] != first["best_trial_index"] and t["params"] != first["frozen_config"]["params"])
    loser["val"]["macro_f1"] = 2.0
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    with pytest.raises(tg.TestAccessError):
        _run(env, tmp_path)


def test_selection_ignores_the_test_partition(env, tmp_path, monkeypatch):
    """Scramble test labels AND test features: the selected trial, frozen config and every
    validation number must not move; only test metrics may."""
    _, clean = _run(env, tmp_path / "clean")
    original = protocol.load_task_data

    def scrambled(ctx, variant, seed):
        parts = original(ctx, variant, seed)
        te = parts["test"].copy()
        rng = np.random.default_rng(0)
        te["acuity"] = 6 - te["acuity"]
        te["heartrate"] = rng.normal(200, 50, len(te))
        te["sbp"] = np.nan
        parts["test"] = te
        return parts

    monkeypatch.setattr(protocol, "load_task_data", scrambled)
    _, dirty = _run(env, tmp_path / "dirty")
    assert dirty["best_trial_index"] == clean["best_trial_index"]
    assert dirty["frozen_config_hash"] == clean["frozen_config_hash"]
    assert dirty["hpo"]["best_val"] == clean["hpo"]["best_val"]
    assert comparable(dirty)["val"] == comparable(clean)["val"]
    assert dirty["test"]["confusion"] != clean["test"]["confusion"]


def test_hpo_trials_never_see_the_test_partition(env, tmp_path, monkeypatch):
    calls: list[int] = []
    original = protocol._fit_predict

    def spy(*args):
        calls.append(len(args[-2]))           # number of evaluation sets passed
        return original(*args)

    monkeypatch.setattr(protocol, "_fit_predict", spy)
    original_metrics = protocol.compute_metrics
    order: list[str] = []
    monkeypatch.setattr(protocol, "compute_metrics", lambda y, p: order.append(f"metrics:{len(y)}") or original_metrics(y, p))
    original_guard = protocol.guard_test_access
    monkeypatch.setattr(protocol, "guard_test_access", lambda d, h: order.append("guard") or original_guard(d, h))
    _, res = _run(env, tmp_path)
    assert calls == [1] * N_CONFIGS + [1]      # trials: [val]; final refit: [val]; test predicted only after the guard
    # test metrics are computed only after the guard accepted the frozen configuration
    n_val, n_test = res["data"]["n_val"], res["data"]["n_test"]
    assert order.count("guard") == 1
    g = order.index("guard")
    assert order[:g] == [f"metrics:{n_val}"] * N_CONFIGS          # HPO: validation only
    assert order[g + 1:] == [f"metrics:{n_val}", f"metrics:{n_test}"]


def test_failing_configuration_is_journaled_and_task_still_finishes(env, tmp_path, monkeypatch):
    original = protocol._fit_predict
    state = {"n": 0}

    def flaky(*args):
        state["n"] += 1
        if state["n"] == 2:
            raise ValueError("synthetic config failure")
        return original(*args)

    monkeypatch.setattr(protocol, "_fit_predict", flaky)
    task, res = _run(env, tmp_path)
    rows = {t["index"]: t for t in read_jsonl(tmp_path / "tasks" / task.id / "trials.jsonl")}
    assert rows[1]["status"] == "error" and "synthetic config failure" in rows[1]["error"]
    assert res["hpo"]["n_error"] == 1 and res["hpo"]["n_ok"] == N_CONFIGS - 1
    assert res["best_trial_index"] != 1


def test_all_configurations_failing_raises(env, tmp_path, monkeypatch):
    def boom(*args):
        raise ValueError("nope")

    monkeypatch.setattr(protocol, "_fit_predict", boom)
    with pytest.raises(RuntimeError, match="configurations failed"):
        _run(env, tmp_path)
    assert not (tmp_path / "tasks" / Task("A_keep_encode", 1, "dtree", "none").id / "test_access.json").exists()


def test_training_partition_without_all_classes_is_an_error(env, tmp_path, monkeypatch):
    original = protocol.load_task_data

    def drop5(ctx, variant, seed):
        parts = original(ctx, variant, seed)
        parts["train"] = parts["train"][parts["train"]["acuity"] != 5].reset_index(drop=True)
        return parts

    monkeypatch.setattr(protocol, "load_task_data", drop5)
    with pytest.raises(RuntimeError, match="lacks classes"):
        _run(env, tmp_path)


# --------------------------------------------------------------------------- 6a/6b. resume

@pytest.mark.parametrize(("model", "strategy"), [("dtree", "none"), ("logreg", "oversample")])
def test_interrupted_task_resumes_without_redoing_trials_and_matches_clean_run(env, tmp_path, monkeypatch,
                                                                               model, strategy):
    _, clean = _run(env, tmp_path / "clean", model=model, strategy=strategy)

    original = protocol._fit_predict
    state = {"n": 0}

    def die_on_second(*args):
        state["n"] += 1
        if state["n"] == 2:
            raise Interrupted()
        return original(*args)

    monkeypatch.setattr(protocol, "_fit_predict", die_on_second)
    with pytest.raises(Interrupted):
        _run(env, tmp_path / "resumed", model=model, strategy=strategy)
    task = Task("A_keep_encode", 1, model, strategy)
    tdir = tmp_path / "resumed" / "tasks" / task.id
    assert trial_indices(tdir / "trials.jsonl") == [0]
    assert not (tdir / "test_access.json").exists()

    calls: list[int] = []
    monkeypatch.setattr(protocol, "_fit_predict", lambda *a: calls.append(len(a[-2])) or original(*a))
    _, resumed = _run(env, tmp_path / "resumed", model=model, strategy=strategy)
    assert calls == [1] * (N_CONFIGS - 1) + [1]    # trial 0 skipped, trials 1..N-1, final refit (val only)
    assert trial_indices(tdir / "trials.jsonl") == list(range(N_CONFIGS))
    assert comparable(resumed) == comparable(clean)


def test_truncated_trailing_line_is_ignored_on_resume(env, tmp_path):
    task, clean = _run(env, tmp_path / "clean")
    tdir = tmp_path / "trunc" / "tasks" / task.id
    tdir.mkdir(parents=True)
    lines = (tmp_path / "clean" / "tasks" / task.id / "trials.jsonl").read_text(encoding="utf-8").splitlines(True)
    # trial 0 complete, trial 1 cut in the middle of the write (no newline)
    (tdir / "trials.jsonl").write_text(lines[0] + lines[1][: len(lines[1]) // 2], encoding="utf-8")
    assert trial_indices(tdir / "trials.jsonl") == [0]
    _, resumed = _run(env, tmp_path / "trunc")
    assert comparable(resumed) == comparable(clean)


def test_journal_is_complete_after_resuming_over_a_truncated_line(env, tmp_path):
    task, _ = _run(env, tmp_path / "clean")
    tdir = tmp_path / "trunc" / "tasks" / task.id
    tdir.mkdir(parents=True)
    lines = (tmp_path / "clean" / "tasks" / task.id / "trials.jsonl").read_text(encoding="utf-8").splitlines(True)
    (tdir / "trials.jsonl").write_text(lines[0] + lines[1][:20], encoding="utf-8")
    _run(env, tmp_path / "trunc")
    # every configuration evaluated in the resumed run must be readable from the journal
    assert sorted(trial_indices(tdir / "trials.jsonl")) == list(range(N_CONFIGS))


# --------------------------------------------------------------------------- 7. golden / regression

GOLDEN_TRIAGE_GZ_SHA256 = "2cfd1173808d500bc1af3dba8c98d965671c71c9d178185d64ee60d551cb85bc"
GOLDEN_DTREE_DIGEST = "9ac03423c61367142ecf5561e730b503082cf775c6f0b0947d613ff78c80d69a"


def test_synthetic_generator_is_byte_stable(env):
    """The generated triage table (gzip mtime=0) is pinned: if numpy's RNG stream or the generator
    change, every golden number below is invalidated and must be re-pinned on purpose."""
    root = Path(env["cfg"]["dataset"]["extract_dir"]) / "mimic-iv-ed-2.2" / "ed" / "triage.csv.gz"
    assert hashlib.sha256(root.read_bytes()).hexdigest() == GOLDEN_TRIAGE_GZ_SHA256


@pytest.mark.parametrize("model", ["dtree", "logreg", "gnb", "dummy_prior"])
def test_two_runs_give_identical_metrics(env, tmp_path, model):
    _, a = _run(env, tmp_path / "a", model=model)
    _, b = _run(env, tmp_path / "b", model=model)
    assert comparable(a) == comparable(b)
    assert metrics_digest(a) == metrics_digest(b)


def test_golden_digest_dtree(env, tmp_path):
    _, res = _run(env, tmp_path, model="dtree", seed=1)
    assert metrics_digest(res) == GOLDEN_DTREE_DIGEST


def test_metrics_are_consistent_with_saved_predictions(env, tmp_path):
    from triagebench.evaluation.metrics import compute_metrics

    task, res = _run(env, tmp_path, model="gnb", strategy="class_weight")
    preds = pd.read_parquet(tmp_path / "tasks" / task.id / "private" / "predictions.parquet")
    for part in ("val", "test"):
        sub = preds[preds["partition"] == part]
        again = compute_metrics(sub["y_true"].to_numpy(), sub["y_pred"].to_numpy())
        assert again["confusion"] == res[part]["confusion"]
        assert again["macro_f1"] == res[part]["macro_f1"]
