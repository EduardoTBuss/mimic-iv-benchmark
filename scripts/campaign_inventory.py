"""Local, stdlib-only campaign byte inventory; never run analysis or copy source data.

For an authorized LOCAL operator only. Capture to a NEW directory outside the campaign:
    python scripts/campaign_inventory.py capture --campaign CAMPAIGN --destination NEW_DIR
Then retain inventory.sha256 independently (the adjacent receipt alone is not independent):
    python scripts/campaign_inventory.py verify --campaign CAMPAIGN \
        --inventory NEW_DIR/inventory.json --expected-sha256 OPERATOR_DIGEST \
        --destination ANOTHER_NEW_DIR

Exit codes: 0 captured/matched; 1 differences; 2 operational/unsafe input error.
Only fixed operational statuses reach stdout/stderr; details stay in restricted output.
POSIX outputs use 0700/0600. On Windows the operator MUST supply a parent with a
restricted ACL: stdlib mode bits cannot establish Windows ACL confidentiality.

Allowlist follows runner/campaign.py, ledger.py, evaluation/protocol.py,
evaluation/costbench.py and analysis/importance.py. Frozen configuration is embedded
in result.json; probabilities are embedded in predictions.parquet. Models are not
needed for statistics and are excluded. Mutable control/log files and regenerated
analysis tables/reports are excluded. Optional cost/importance artifacts are bound
when present; they do not change any seed-selection rule. Private directories are
never descended by default. --include-private explicitly opts into hashing saved
predictions (without parsing them); verify preserves the captured input scope.
No metrics, patient IDs,
prediction rows, configuration values or original absolute paths enter the inventory.

The local clock is untrusted evidence, with no --as-of/cutoff override. Neither a
digest, DONE markers nor this structural inventory proves a deadline, eligibility,
scientific validity, final seed prefix or an externally certified capture time.
Stop all campaign writers first. Stat/relisting checks detect ordinary concurrent
changes; this is not an atomic filesystem snapshot against a malicious writer.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import stat
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

SCHEMA = "triagebench-campaign-inventory-v1"
ROOT_FILES = ("campaign.json", "grid.json", "config.resolved.yaml", "manifest.json", "cost_benchmark.jsonl")
TASK_FILES = ("DONE", "result.json", "trials.jsonl", "test_access.json", "state.json", "error.json")
EXTRA_TABLES = ("cost_benchmark.parquet", "importance.parquet")
POLICY = {
    "root_files": list(ROOT_FILES), "task_files": list(TASK_FILES),
    "private_files": ["predictions.parquet"], "importance": "importance/<taskkey>.json",
    "tables": list(EXTRA_TABLES), "content_validation": False,
    "time_evidence": "untrusted_local_clock_not_external_timestamp",
    "timestamp_interval": "source_inventory_read_not_output_publication",
    "completeness": "structural_presence_only_not_scientific_or_final_prefix",
}
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")


class InventoryError(Exception):
    """A fixed, non-sensitive operational error code."""


def _fail(code):
    raise InventoryError(code)


def _safe_parts(relative):
    if not isinstance(relative, str) or "\\" in relative or ":" in relative:
        _fail("unsafe_relative_path")
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(p in (".", "..") for p in path.parts):
        _fail("unsafe_relative_path")
    if path.as_posix() != relative:
        _fail("unsafe_relative_path")
    return path.parts


def _absolute(path):
    path = Path(path)
    if ".." in path.parts:
        _fail("unsafe_path")
    return Path(os.path.abspath(path))


def _is_link(st):
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)


def _stamp(st):
    # Python 3.12 Windows lstat exposes creation time as ctime, whereas fstat
    # can expose change time. birthtime is consistent between both APIs.
    extra_time = getattr(st, "st_birthtime_ns", st.st_ctime_ns) if os.name == "nt" else st.st_ctime_ns
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, extra_time)


def _win_open(path, directory=False):
    """Open the object itself; deny delete sharing to keep ancestors in place."""
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    handle = create(str(path), 0x80000000, 0x1 | 0x2, None, 3,
                    0x00200000 | (0x02000000 if directory else 0), None)
    if handle == wintypes.HANDLE(-1).value:
        _fail("unsafe_or_unreadable_path")
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    # fstat does not expose reparse attributes consistently; the open handle prevents
    # renaming/deleting the path while lstat inspects the same object.
    try:
        st = os.lstat(path)
        if _is_link(st) or (directory and not stat.S_ISDIR(st.st_mode)):
            _fail("symlink_or_invalid_type")
    except BaseException:
        os.close(fd)
        raise
    return fd


class SafeTree:
    """Anchor directory access, opening every component without following links."""

    def __init__(self, root):
        self.root = _absolute(root)
        self.held = []
        try:
            if os.name == "nt":
                current = Path(self.root.anchor)
                for component in self.root.parts[1:]:
                    current /= component
                    self.held.append(_win_open(current, directory=True))
                self.fd = None
            else:
                current = os.open(self.root.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                self.held.append(current)
                for component in self.root.parts[1:]:
                    current = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=current)
                    self.held.append(current)
                self.fd = current
        except BaseException:
            self.close()
            raise

    def close(self):
        for fd in reversed(self.held):
            os.close(fd)
        self.held.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @contextmanager
    def directory(self, relative=""):
        parts = _safe_parts(relative) if relative else ()
        held = []
        try:
            if os.name == "nt":
                current = self.root
                for component in parts:
                    current /= component
                    held.append(_win_open(current, directory=True))
                yield current
            else:
                current = self.fd
                for component in parts:
                    current = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=current)
                    held.append(current)
                yield current
        finally:
            for fd in reversed(held):
                os.close(fd)

    def listing(self, relative=""):
        with self.directory(relative) as directory:
            with os.scandir(directory) as entries:
                # Windows DirEntry.stat omits dev/inode on Python 3.12; lstat
                # supplies identity comparable with the subsequently opened fd.
                result = {entry.name: (os.lstat(directory / entry.name) if os.name == "nt"
                                      else entry.stat(follow_symlinks=False)) for entry in entries}
            if any(_is_link(st) for st in result.values()):
                _fail("symlink_or_reparse_point")
            return result

    @contextmanager
    def regular(self, relative):
        parts = _safe_parts(relative)
        with self.directory("/".join(parts[:-1])) as parent:
            if os.name == "nt":
                fd = _win_open(parent / parts[-1])
            else:
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    _fail("not_regular_file")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    yield stream
            finally:
                os.close(fd)


def _taskkey(name):
    parts = name.split("__")
    if len(parts) != 4 or not all(_TOKEN.fullmatch(p) for p in (parts[0], parts[2], parts[3])):
        _fail("invalid_taskkey")
    if not re.fullmatch(r"s[0-9]{2,12}", parts[1]):
        _fail("invalid_taskkey")
    key = {"variant": parts[0], "seed": int(parts[1][1:]), "model": parts[2], "strategy": parts[3]}
    if name != f"{key['variant']}__s{key['seed']:02d}__{key['model']}__{key['strategy']}":
        _fail("invalid_taskkey")
    return key


def _scan(tree, include_private=False, strict=True):
    files, task_names = {}, []

    def add(entries, prefix, names):
        for name in names:
            if name in entries:
                if not stat.S_ISREG(entries[name].st_mode):
                    _fail("not_regular_file")
                files[prefix + name] = _stamp(entries[name])

    def sub(entries, name, relative):
        if name not in entries:
            return {}
        if not stat.S_ISDIR(entries[name].st_mode):
            _fail("not_directory")
        return tree.listing(relative)

    root = tree.listing()
    add(root, "", ROOT_FILES)
    if strict and any(name not in files for name in ROOT_FILES[:4]):
        _fail("missing_campaign_metadata")
    if strict and "tasks" not in root:
        _fail("missing_tasks_directory")
    tasks = sub(root, "tasks", "tasks")
    for name, st in sorted(tasks.items()):
        _taskkey(name)
        if not stat.S_ISDIR(st.st_mode):
            _fail("invalid_task_directory")
        task_names.append(name)
        prefix = f"tasks/{name}/"
        entries = tree.listing(prefix[:-1])
        add(entries, prefix, TASK_FILES)
        if include_private:
            private = sub(entries, "private", prefix + "private")
            add(private, prefix + "private/", ("predictions.parquet",))
    importance = sub(root, "importance", "importance")
    for name in importance:
        if name.endswith(".json"):
            _taskkey(name[:-5])
            add(importance, "importance/", (name,))
    tables = sub(root, "tables", "tables")
    add(tables, "tables/", EXTRA_TABLES)
    return files, task_names


def _hash_file(tree, relative, expected=None, keep=False):
    digest, chunks = hashlib.sha256(), []
    with tree.regular(relative) as stream:
        before = _stamp(os.fstat(stream.fileno()))
        if expected is not None and before != expected:
            _fail("campaign_changed_during_read")
        size = 0
        while block := stream.read(1024 * 1024):
            size += len(block)
            digest.update(block)
            if keep:
                if size > 32 * 1024 * 1024:
                    _fail("metadata_too_large")
                chunks.append(block)
        after = _stamp(os.fstat(stream.fileno()))
    if before != after or size != before[3]:
        _fail("file_changed_during_hash")
    return {"path": relative, "bytes": size, "sha256": digest.hexdigest()}, b"".join(chunks)


def _parse_json(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fail("duplicate_json_key")
            result[key] = value
        return result

    return json.loads(payload, object_pairs_hook=unique)


def _grid_keys(payload):
    grid = _parse_json(payload)
    if not isinstance(grid, dict) or not isinstance(grid.get("tasks"), list):
        _fail("invalid_grid")
    keys = {}
    for entry in grid["tasks"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            _fail("invalid_grid")
        name = entry["id"]
        key = _taskkey(name)
        if name in keys or any(entry.get(k) != v for k, v in key.items()) or type(entry.get("seed")) is not int:
            _fail("invalid_grid")
        keys[name] = key
    return keys


def _inventory(tree, include_private=False, grid_keys=None):
    before, directories = _scan(tree, include_private, strict=grid_keys is None)
    files, grid_payload = [], None
    for relative, st in sorted(before.items()):
        record, payload = _hash_file(tree, relative, st, keep=relative == "grid.json" and grid_keys is None)
        files.append(record)
        if relative == "grid.json":
            grid_payload = payload
    keys = _grid_keys(grid_payload) if grid_keys is None else grid_keys
    tasks = []
    for name in sorted(set(keys) | set(directories)):
        present = [f for f in TASK_FILES if f"tasks/{name}/{f}" in before]
        done = "DONE" in present and "result.json" in present
        tasks.append({"taskkey": name, "key": keys.get(name) or _taskkey(name),
                      "in_grid": name in keys, "directory_present": name in directories,
                      "ledger_done_markers_present": done, "present_artifacts": present,
                      "missing_structural_artifacts": [f for f in TASK_FILES[:4] if f not in present],
                      "prediction_file_present": (f"tasks/{name}/private/predictions.parquet" in before
                                                  if include_private else None)})
    after, after_directories = _scan(tree, include_private, strict=grid_keys is None)
    if before != after or directories != after_directories:
        _fail("campaign_changed_during_capture")
    return {"files": files, "tasks": tasks,
            "structure": {"grid_task_count": len(keys), "task_directory_count": len(directories),
                          "all_grid_tasks_have_ledger_markers": bool(keys) and all(
                              t["ledger_done_markers_present"] for t in tasks if t["in_grid"]),
                          "unexpected_task_directories": sum(not t["in_grid"] for t in tasks),
                          "content_validated": False, "final_prefix_certified": False}}


def _utc_now():
    return datetime.now(UTC)


def _new_destination(destination, campaign):
    destination = _absolute(destination)
    campaign = _absolute(campaign)
    if destination == campaign or destination.is_relative_to(campaign):
        _fail("destination_inside_campaign")
    # No mkdir(parents=True): the operator deliberately provisions the secure parent.
    with SafeTree(destination.parent):
        destination.mkdir(mode=0o700, exist_ok=False)
    return destination


def _write_new(destination, filename, payload):
    with SafeTree(destination) as tree:
        if os.name == "nt":
            fd = os.open(destination / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        else:
            fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=tree.fd)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def capture(campaign, destination, *, include_private=False):
    """Return the inventory digest; the caller must retain it independently."""
    started, monotonic = _utc_now(), time.monotonic_ns()
    with SafeTree(campaign) as tree:
        destination = _new_destination(destination, tree.root)
        script = _absolute(__file__)
        with SafeTree(script.parent) as script_tree:
            code, _ = _hash_file(script_tree, script.name)
        inventory = _inventory(tree, include_private)
        ended = _utc_now()
        elapsed = time.monotonic_ns() - monotonic
        if ended < started or elapsed < 0:
            _fail("local_clock_inconsistent")
        manifest = {"schema": SCHEMA, "operation": "capture", "started_at_utc": started.isoformat(),
                    "ended_at_utc": ended.isoformat(), "duration_monotonic_ns": elapsed,
                    "policy": POLICY, "input_scope": {
                        "include_private": include_private,
                        "prediction_binding": include_private,
                        "default_aggregates_metadata_only": not include_private,
                    }, "code": code, **inventory}
        payload = _json_bytes(manifest)
        digest = hashlib.sha256(payload).hexdigest()
        _write_new(destination, "inventory.sha256", (digest + "\n").encode("ascii"))
        _write_new(destination, "inventory.json", payload)
    return digest


def _read_inventory(path, expected_sha256):
    if not isinstance(expected_sha256, str) or not _DIGEST.fullmatch(expected_sha256):
        _fail("invalid_expected_digest")
    path = _absolute(path)
    with SafeTree(path.parent) as tree:
        record, payload = _hash_file(tree, path.name, keep=True)
    if record["sha256"] != expected_sha256:
        _fail("inventory_receipt_mismatch")
    manifest = _parse_json(payload)
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA or manifest.get("policy") != POLICY:
        _fail("unsupported_inventory")
    for field in ("started_at_utc", "ended_at_utc"):
        value = datetime.fromisoformat(manifest[field])
        if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
            _fail("invalid_inventory_time")
    if datetime.fromisoformat(manifest["ended_at_utc"]) < datetime.fromisoformat(manifest["started_at_utc"]):
        _fail("invalid_inventory_time")
    files = manifest.get("files")
    if not isinstance(files, list) or not isinstance(manifest.get("tasks"), list):
        _fail("invalid_inventory")
    scope = manifest.get("input_scope")
    if (not isinstance(scope, dict) or type(scope.get("include_private")) is not bool
            or scope.get("prediction_binding") is not scope["include_private"]
            or scope.get("default_aggregates_metadata_only") is not (not scope["include_private"])):
        _fail("invalid_inventory_scope")
    seen = set()
    for record in files:
        _safe_parts(record["path"])
        if (record["path"] in seen or type(record["bytes"]) is not int or record["bytes"] < 0
                or not _DIGEST.fullmatch(record["sha256"])):
            _fail("invalid_inventory")
        seen.add(record["path"])
    seen_tasks = set()
    for task in manifest["tasks"]:
        name = task["taskkey"]
        if name in seen_tasks or task["key"] != _taskkey(name) or type(task["in_grid"]) is not bool:
            _fail("invalid_inventory")
        seen_tasks.add(name)
    return manifest


def verify(campaign, inventory, expected_sha256, destination):
    """Compare the bound snapshot to the current allowlist; no temporal eligibility claim."""
    started = _utc_now()
    manifest = _read_inventory(inventory, expected_sha256)
    with SafeTree(campaign) as tree:
        destination = _new_destination(destination, tree.root)
        keys = {t["taskkey"]: t["key"] for t in manifest["tasks"] if t["in_grid"]}
        current = _inventory(tree, manifest["input_scope"]["include_private"], grid_keys=keys)
    original = {f["path"]: f for f in manifest["files"]}
    now = {f["path"]: f for f in current["files"]}
    changes = {"missing": sorted(original.keys() - now.keys()),
               "added": sorted(now.keys() - original.keys()),
               "mutated": sorted(p for p in original.keys() & now.keys() if original[p] != now[p]),
               "task_structure_changed": manifest["tasks"] != current["tasks"],
               "campaign_structure_changed": manifest.get("structure") != current["structure"]}
    matched = not any(changes.values())
    ended = _utc_now()
    if ended < started:
        _fail("local_clock_inconsistent")
    _write_new(destination, "verification.json", _json_bytes({"schema": SCHEMA, "operation": "verify",
               "started_at_utc": started.isoformat(), "ended_at_utc": ended.isoformat(),
               "expected_inventory_sha256": expected_sha256, "matched": matched,
               "time_evidence": POLICY["time_evidence"], "changes": changes}))
    return matched


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error echoes operator arguments, including private paths.
        _fail("invalid_arguments")


def main(argv=None):
    try:
        parser = _Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
        sub = parser.add_subparsers(dest="operation", required=True, parser_class=_Parser)
        for operation in ("capture", "verify"):
            command = sub.add_parser(operation)
            command.add_argument("--campaign", required=True)
            command.add_argument("--destination", required=True)
            if operation == "capture":
                command.add_argument("--include-private", action="store_true")
            if operation == "verify":
                command.add_argument("--inventory", required=True)
                command.add_argument("--expected-sha256", required=True)
        args = parser.parse_args(argv)
        if args.operation == "capture":
            capture(args.campaign, args.destination, include_private=args.include_private)
            print("CAPTURED")
            return 0
        matched = verify(args.campaign, args.inventory, args.expected_sha256, args.destination)
        print("VERIFIED" if matched else "DIFFERENT")
        return 0 if matched else 1
    except KeyboardInterrupt:
        print("ERROR interrupted", file=sys.stderr)
        return 2
    except InventoryError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        print("ERROR unsafe_unreadable_or_invalid_input", file=sys.stderr)
        return 2
    except Exception:
        # Includes recursion/parser/native API failures. Never echo exception text,
        # traceback, operator arguments or source paths into a terminal/session log.
        print("ERROR operational_failure", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
