"""Environment snapshot for manifests: git, Python, library versions, hardware."""

from __future__ import annotations

import importlib.metadata as md
import os
import platform
import socket
import subprocess
import sys
from pathlib import Path

import psutil

from triagebench.utils.io import utc_now

KEY_PACKAGES = (
    "numpy",
    "pandas",
    "pyarrow",
    "scipy",
    "scikit-learn",
    "imbalanced-learn",
    "xgboost-cpu",
    "statsmodels",
    "pyyaml",
    "matplotlib",
    "psutil",
)


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def git_info(cwd: Path | None = None) -> dict:
    cwd = cwd or repo_root()
    commit = _git(["rev-parse", "HEAD"], cwd)
    status = _git(["status", "--porcelain", "--untracked-files=no"], cwd)
    return {
        "commit": commit,
        "short": commit[:7] if commit else None,
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd),
        "dirty": bool(status) if status is not None else None,
    }


def library_versions(packages: tuple[str, ...] = KEY_PACKAGES) -> dict:
    versions = {}
    for pkg in packages:
        try:
            versions[pkg] = md.version(pkg)
        except md.PackageNotFoundError:
            versions[pkg] = None
    return versions


def all_distributions() -> dict:
    return dict(sorted((d.metadata["Name"], d.version) for d in md.distributions() if d.metadata["Name"]))


def cpu_model() -> str:
    if sys.platform.startswith("linux"):
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def hardware_info() -> dict:
    vm = psutil.virtual_memory()
    return {
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "cpu_model": cpu_model(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cpus": psutil.cpu_count(logical=True),
        "ram_total_gb": round(vm.total / 2**30, 2),
        "gpu": "not used (CPU-only benchmark)",
    }


def environment_snapshot(include_all_packages: bool = True) -> dict:
    snap = {
        "captured_at": utc_now(),
        "git": git_info(),
        "packages": library_versions(),
        "hardware": hardware_info(),
        "pid": os.getpid(),
    }
    if include_all_packages:
        snap["all_packages"] = all_distributions()
    return snap
