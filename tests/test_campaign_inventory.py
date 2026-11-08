"""Entirely synthetic filesystem fixtures: no campaign/data/reports are consulted."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "campaign_inventory.py"
SPEC = importlib.util.spec_from_file_location("campaign_inventory_under_test", SCRIPT)
INV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INV)
TASK = "A_missingness__s01__rf__none"
OTHER_TASK = "A_missingness__s02__rf__none"


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload if isinstance(payload, bytes) else json.dumps(payload).encode())


def add_task(campaign, task=TASK):
    directory = campaign / "tasks" / task
    for filename, value in {
        "DONE": b"", "result.json": {"frozen_config": {"params": {}}, "test": {"SECRET_METRIC": 0.123456}},
        "trials.jsonl": b'{"SECRET_TRIAL_METRIC":42}\n', "test_access.json": {"frozen_config_hash": "fake"},
        "state.json": {"state": "done", "pid": 987654321},
        "private/predictions.parquet": b"synthetic patient and probability sentinel; not a real parquet",
        "private/model.joblib": b"model-excluded",
    }.items():
        write(directory / filename, value)
    return directory


@pytest.fixture
def campaign(tmp_path):
    root = tmp_path / "synthetic-campaign"
    for filename, value in {
        "campaign.json": {"campaign_id": "synthetic-only", "irrelevant": "SECRET_METADATA_VALUE"},
        "grid.json": {"tasks": [{"id": TASK, **INV._taskkey(TASK)}], "not_applicable": []},
        "config.resolved.yaml": b"synthetic_frozen_config: SECRET_CONFIG_VALUE\n",
        "manifest.json": {"sessions": []},
    }.items():
        write(root / filename, value)
    add_task(root)
    return root


def snapshot(campaign, tmp_path, **kwargs):
    destination = tmp_path / "captured"
    digest = INV.capture(campaign, destination, **kwargs)
    path = destination / "inventory.json"
    return path, digest, json.loads(path.read_bytes())


def check(campaign, tmp_path, path, digest):
    destination = tmp_path / "verification"
    matched = INV.verify(campaign, path, digest, destination)
    return matched, json.loads((destination / "verification.json").read_bytes())


def test_capture_roundtrip_receipt_code_scope_and_no_contents(campaign, tmp_path):
    path, digest, manifest = snapshot(campaign, tmp_path)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert path.with_name("inventory.sha256").read_text().strip() == digest
    assert manifest["code"]["sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert manifest["input_scope"]["include_private"] is False
    assert manifest["input_scope"]["prediction_binding"] is False
    assert not any("private/" in f["path"] for f in manifest["files"])
    assert manifest["tasks"][0]["prediction_file_present"] is None
    assert manifest["structure"]["content_validated"] is False
    assert manifest["structure"]["final_prefix_certified"] is False
    assert manifest["tasks"][0]["ledger_done_markers_present"] is True
    for field in ("started_at_utc", "ended_at_utc"):
        assert datetime.fromisoformat(manifest[field]).utcoffset() == timedelta(0)
    assert manifest["duration_monotonic_ns"] >= 0
    raw = path.read_text()
    assert str(campaign) not in raw
    assert not any(secret in raw for secret in (
        "SECRET_METRIC", "0.123456", "SECRET_METADATA_VALUE", "SECRET_CONFIG_VALUE", "SECRET_TRIAL_METRIC",
        "987654321", "patient and probability sentinel",
    ))
    matched, details = check(campaign, tmp_path, path, digest)
    assert matched and details["matched"]
    assert details["time_evidence"] == "untrusted_local_clock_not_external_timestamp"


def test_default_never_descends_private(campaign, tmp_path, monkeypatch):
    original = INV.SafeTree.listing

    def forbid(tree, relative=""):
        assert not relative.endswith("/private"), "default must not inspect private descendants"
        return original(tree, relative)

    monkeypatch.setattr(INV.SafeTree, "listing", forbid)
    path, digest, _ = snapshot(campaign, tmp_path)
    write(campaign / "tasks" / TASK / "private" / "predictions.parquet", b"changed excluded private file")
    assert check(campaign, tmp_path, path, digest)[0]


def test_explicit_private_scope_binds_bytes_and_verify_preserves_it(campaign, tmp_path):
    path, digest, manifest = snapshot(campaign, tmp_path, include_private=True)
    expected = f"tasks/{TASK}/private/predictions.parquet"
    assert manifest["input_scope"]["prediction_binding"] is True
    assert expected in {f["path"] for f in manifest["files"]}
    assert manifest["tasks"][0]["prediction_file_present"] is True
    write(campaign / expected, b"mutated synthetic bytes")
    matched, details = check(campaign, tmp_path, path, digest)
    assert not matched and details["changes"]["mutated"] == [expected]


@pytest.mark.parametrize("relative", ["campaign.json", "grid.json", "config.resolved.yaml", "manifest.json",
                                     f"tasks/{TASK}/result.json", f"tasks/{TASK}/trials.jsonl",
                                     f"tasks/{TASK}/test_access.json", f"tasks/{TASK}/DONE"])
def test_changed_bytes_are_detected_even_invalid_json(campaign, tmp_path, relative):
    path, digest, _ = snapshot(campaign, tmp_path)
    write(campaign / relative, b"deliberately invalid JSON or changed opaque bytes")
    matched, details = check(campaign, tmp_path, path, digest)
    assert not matched and details["changes"]["mutated"] == [relative]


@pytest.mark.parametrize("relative", ["campaign.json", "grid.json", f"tasks/{TASK}/DONE",
                                     f"tasks/{TASK}/result.json"])
def test_missing_files_are_reported(campaign, tmp_path, relative):
    path, digest, _ = snapshot(campaign, tmp_path)
    (campaign / relative).unlink()
    matched, details = check(campaign, tmp_path, path, digest)
    assert not matched and details["changes"]["missing"] == [relative]


def test_added_task_outside_grid_is_detected(campaign, tmp_path):
    path, digest, _ = snapshot(campaign, tmp_path)
    add_task(campaign, OTHER_TASK)
    matched, details = check(campaign, tmp_path, path, digest)
    assert not matched and details["changes"]["task_structure_changed"]
    assert any(OTHER_TASK in p for p in details["changes"]["added"])


def test_added_empty_task_directory_is_detected(campaign, tmp_path):
    path, digest, _ = snapshot(campaign, tmp_path)
    (campaign / "tasks" / OTHER_TASK).mkdir()
    matched, details = check(campaign, tmp_path, path, digest)
    assert not matched and details["changes"]["task_structure_changed"]
    assert details["changes"]["added"] == []


def test_removed_task_directory_is_detected(campaign, tmp_path):
    path, digest, _ = snapshot(campaign, tmp_path)
    # Move synthetic task to another synthetic directory, no recursive deletion.
    (campaign / "tasks" / TASK).rename(tmp_path / "removed-synthetic-task")
    matched, details = check(campaign, tmp_path, path, digest)
    assert not matched and details["changes"]["task_structure_changed"]
    assert f"tasks/{TASK}/DONE" in details["changes"]["missing"]


def test_optional_extras_are_bound_analysis_regeneration_is_ignored(campaign, tmp_path):
    for relative in ("cost_benchmark.jsonl", f"importance/{TASK}.json",
                     "tables/cost_benchmark.parquet", "tables/importance.parquet"):
        write(campaign / relative, b"synthetic cost or importance")
    path, digest, _ = snapshot(campaign, tmp_path)
    write(campaign / "tables" / "stats.json", {"generated": "irrelevant"})
    write(campaign / "control.yaml", b"pause: false\n")
    write(campaign / "logs" / "runner.log", b"not inventoried")
    assert check(campaign, tmp_path, path, digest)[0]
    write(campaign / "cost_benchmark.jsonl", b"different optional evidence")
    different = tmp_path / "different-verification"
    assert not INV.verify(campaign, path, digest, different)
    changes = json.loads((different / "verification.json").read_bytes())["changes"]
    assert changes["mutated"] == ["cost_benchmark.jsonl"]


def test_new_optional_evidence_is_detected(campaign, tmp_path):
    path, digest, _ = snapshot(campaign, tmp_path)
    write(campaign / "tables" / "cost_benchmark.parquet", b"new synthetic evidence")
    matched, details = check(campaign, tmp_path, path, digest)
    assert not matched and details["changes"]["added"] == ["tables/cost_benchmark.parquet"]


def test_partial_is_explicitly_structural_not_validated(campaign, tmp_path):
    (campaign / "tasks" / TASK / "test_access.json").unlink()
    _, _, manifest = snapshot(campaign, tmp_path)
    assert manifest["tasks"][0]["ledger_done_markers_present"] is True
    assert manifest["tasks"][0]["missing_structural_artifacts"] == ["test_access.json"]
    assert manifest["structure"]["content_validated"] is False
    assert manifest["policy"]["completeness"] == "structural_presence_only_not_scientific_or_final_prefix"


def test_empty_grid_is_not_declared_complete(campaign, tmp_path):
    write(campaign / "grid.json", {"tasks": []})
    _, _, manifest = snapshot(campaign, tmp_path)
    assert manifest["structure"]["grid_task_count"] == 0
    assert manifest["structure"]["all_grid_tasks_have_ledger_markers"] is False
    assert manifest["structure"]["unexpected_task_directories"] == 1


@pytest.mark.parametrize("mutation", ["duplicate", "key_mismatch", "path_escape"])
def test_invalid_grid_is_rejected_without_publishing(campaign, tmp_path, mutation):
    entry = {"id": TASK, **INV._taskkey(TASK)}
    tasks = [entry]
    if mutation == "duplicate":
        tasks.append(entry)
    elif mutation == "key_mismatch":
        entry["seed"] = 99
    else:
        entry["id"] = "../escape"
    write(campaign / "grid.json", {"tasks": tasks})
    destination = tmp_path / "invalid-grid"
    with pytest.raises(INV.InventoryError, match="invalid_grid|invalid_taskkey"):
        INV.capture(campaign, destination)
    assert not (destination / "inventory.json").exists()


def test_wrong_external_digest_is_rejected_before_destination(campaign, tmp_path):
    path, _, _ = snapshot(campaign, tmp_path)
    destination = tmp_path / "bad-receipt"
    with pytest.raises(INV.InventoryError, match="inventory_receipt_mismatch"):
        INV.verify(campaign, path, "0" * 64, destination)
    assert not destination.exists()


def test_modified_manifest_and_adjacent_receipt_do_not_replace_external_digest(campaign, tmp_path):
    path, digest, manifest = snapshot(campaign, tmp_path)
    manifest["tasks"] = []
    path.write_bytes(INV._json_bytes(manifest))
    path.with_name("inventory.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(INV.InventoryError, match="inventory_receipt_mismatch"):
        check(campaign, tmp_path, path, digest)


def test_no_cutoff_or_falsifiable_asof_option(campaign, tmp_path, monkeypatch, capsys):
    # A forged local OS clock can still lie; the manifest must never sell this as
    # proof that a future deadline was met, nor evaluate a preregistration gate.
    monkeypatch.setattr(INV, "_utc_now", lambda: datetime(2000, 1, 1, tzinfo=UTC))
    _, _, manifest = snapshot(campaign, tmp_path)
    assert manifest["policy"]["time_evidence"] == "untrusted_local_clock_not_external_timestamp"
    assert "eligible" not in manifest and "cutoff" not in manifest
    assert INV.main(["capture", "--campaign", str(campaign), "--destination", str(tmp_path / "unused"),
                   "--as-of", "1999-01-01T00:00:00Z"]) == 2
    output = capsys.readouterr()
    assert str(campaign) not in output.out + output.err
    assert "1999" not in output.out + output.err


def test_clock_rollback_fails_without_publishing_inventory(campaign, tmp_path, monkeypatch):
    times = iter([datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)])
    monkeypatch.setattr(INV, "_utc_now", lambda: next(times))
    destination = tmp_path / "clock-failed"
    with pytest.raises(INV.InventoryError, match="local_clock_inconsistent"):
        INV.capture(campaign, destination)
    assert not (destination / "inventory.json").exists()


@pytest.mark.parametrize("inside", [True, False])
def test_destination_inside_campaign_or_existing_is_rejected(campaign, tmp_path, inside):
    destination = campaign / "inventory" if inside else tmp_path / "existing"
    if not inside:
        destination.mkdir()
        write(destination / "sentinel.txt", b"preserve existing")
    with pytest.raises((INV.InventoryError, FileExistsError)):
        INV.capture(campaign, destination)
    if not inside:
        assert (destination / "sentinel.txt").read_bytes() == b"preserve existing"


def test_existing_snapshot_cannot_be_overwritten(campaign, tmp_path):
    path, _, _ = snapshot(campaign, tmp_path)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        INV.capture(campaign, path.parent)
    assert path.read_bytes() == before


def test_concurrent_capture_has_exactly_one_winner(campaign, tmp_path):
    destination = tmp_path / "exclusive"

    def run():
        try:
            INV.capture(campaign, destination)
            return "ok"
        except FileExistsError:
            return "exists"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(results) == ["exists", "ok"]
    assert (destination / "inventory.json").is_file()


def link_or_skip(link, target, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError:
        pytest.skip("OS does not permit synthetic symlinks in this session")


@pytest.mark.parametrize("kind", ["file", "task_directory", "root", "output_parent"])
def test_symlinks_are_refused(campaign, tmp_path, kind):
    destination = tmp_path / "symlink-refused"
    if kind == "file":
        target = tmp_path / "outside.json"
        write(target, b"must not read")
        source = campaign / "campaign.json"
        source.unlink()
        link_or_skip(source, target)
    elif kind == "task_directory":
        link_or_skip(campaign / "tasks" / OTHER_TASK, tmp_path, directory=True)
    elif kind == "root":
        alias = tmp_path / "alias"
        link_or_skip(alias, campaign, directory=True)
        campaign = alias
    else:
        alias = tmp_path / "parent-alias"
        link_or_skip(alias, tmp_path, directory=True)
        destination = alias / "new-output"
    with pytest.raises((INV.InventoryError, OSError)):
        INV.capture(campaign, destination)
    assert not (destination / "inventory.json").exists()


def test_synthetic_windows_reparse_attribute_is_always_rejected():
    class Reparse:
        st_mode = stat.S_IFDIR | 0o700
        st_file_attributes = 0x400

    assert INV._is_link(Reparse())


def test_racing_file_change_during_hash_is_refused(campaign, tmp_path, monkeypatch):
    original = INV.SafeTree.regular

    @contextmanager
    def racing(tree, relative):
        with original(tree, relative) as stream:
            if relative == "campaign.json":
                original_read = stream.read

                def read(*args):
                    result = original_read(*args)
                    if result:
                        with (campaign / relative).open("ab") as writer:
                            writer.write(b"race")
                        stream.read = original_read
                    return result

                stream.read = read
            yield stream

    monkeypatch.setattr(INV.SafeTree, "regular", racing)
    with pytest.raises(INV.InventoryError, match="file_changed_during_hash"):
        INV.capture(campaign, tmp_path / "racing-file")
    assert not (tmp_path / "racing-file" / "inventory.json").exists()


def test_added_task_during_capture_is_detected_by_relisting(campaign, tmp_path, monkeypatch):
    original = INV._hash_file

    def racing(tree, relative, *args, **kwargs):
        result = original(tree, relative, *args, **kwargs)
        if relative == "grid.json":
            (campaign / "tasks" / OTHER_TASK).mkdir()
        return result

    monkeypatch.setattr(INV, "_hash_file", racing)
    with pytest.raises(INV.InventoryError, match="campaign_changed_during_capture"):
        INV.capture(campaign, tmp_path / "racing-task")


def test_operational_errors_do_not_echo_private_paths(campaign, tmp_path, monkeypatch, capsys):
    def denied(*args, **kwargs):
        raise OSError("SECRET_PRIVATE_PATH patient contents must not be printed")

    monkeypatch.setattr(INV, "_inventory", denied)
    assert INV.main(["capture", "--campaign", str(campaign), "--destination", str(tmp_path / "denied")]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "ERROR unsafe_unreadable_or_invalid_input\n"


def test_unexpected_parser_failure_does_not_emit_traceback(campaign, tmp_path, monkeypatch, capsys):
    def bad(*args, **kwargs):
        raise RecursionError("SECRET_CONTENT")

    monkeypatch.setattr(INV, "_inventory", bad)
    assert INV.main(["capture", "--campaign", str(campaign), "--destination", str(tmp_path / "parser-error")]) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "ERROR operational_failure\n"


def test_cli_status_only_success_difference_and_receipt_error(campaign, tmp_path, capsys):
    destination = tmp_path / "cli-capture"
    assert INV.main(["capture", "--campaign", str(campaign), "--destination", str(destination)]) == 0
    assert capsys.readouterr().out == "CAPTURED\n"
    digest = (destination / "inventory.sha256").read_text().strip()
    command = ["verify", "--campaign", str(campaign), "--inventory", str(destination / "inventory.json"),
               "--expected-sha256", digest]
    assert INV.main([*command, "--destination", str(tmp_path / "cli-verify")]) == 0
    assert capsys.readouterr().out == "VERIFIED\n"
    write(campaign / "campaign.json", b"changed")
    assert INV.main([*command, "--destination", str(tmp_path / "cli-different")]) == 1
    assert capsys.readouterr().out == "DIFFERENT\n"
    command[command.index(digest)] = "0" * 64
    assert INV.main([*command, "--destination", str(tmp_path / "cli-error")]) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "ERROR inventory_receipt_mismatch\n"


@pytest.mark.skipif(os.name != "posix", reason="Windows ACLs must be provisioned by the local operator")
def test_posix_restricted_modes(campaign, tmp_path):
    path, _, _ = snapshot(campaign, tmp_path)
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.with_name("inventory.sha256").stat().st_mode) == 0o600


@pytest.mark.parametrize("bad", ["../escape", "/absolute", "a/../b", "a\\b", "C:escape", "a//b", "./a"])
def test_unsafe_manifest_relative_paths_are_rejected(bad):
    with pytest.raises(INV.InventoryError, match="unsafe_relative_path"):
        INV._safe_parts(bad)
