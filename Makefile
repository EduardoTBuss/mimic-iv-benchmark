# Linux/server entry points (Q-FLEX, x299). On Windows use: uv run python -m triagebench <command>
#   make setup                         # .venv from the hashed lockfile (no global installs)
#   make test smoke                    # synthetic data only
#   make launch-bg PROFILE=qflex       # full pipeline, detached (tmux), resumable
#   make status PROFILE=qflex          # progress / ETA / failures
SHELL := /bin/bash
PY ?= .venv/bin/python
CONFIG ?= configs/main.yaml
PROFILE ?=
TB = PYTHONPATH=src $(PY) -m triagebench
ARGS = --config $(CONFIG) $(if $(PROFILE),--profile $(PROFILE),)

.PHONY: help setup test lint smoke env ingest audit prepare run run-all pilot status analyze launch-bg verify-gitignore

help:  ## list targets
	@grep -E '^[a-z-]+:.*## ' Makefile | sed 's/:.*## /\t/'

setup:  ## create .venv from requirements-lock.txt (hash-pinned) and enable the git hook
	python3.12 -m venv .venv
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet --require-hashes -r requirements-lock.txt
	git config core.hooksPath .githooks || true

test:  ## unit, leakage and resume tests (synthetic data)
	PYTHONPATH=src $(PY) -m pytest

lint:  ## ruff
	$(PY) -m ruff check src tests

smoke:  ## end-to-end run on synthetic data
	$(TB) smoke

env:  ## environment snapshot (versions, hardware, git)
	$(TB) env

ingest:  ## verify SHA256SUMS and extract the zip
	$(TB) ingest $(ARGS)

audit:  ## aggregate-only audit -> reports/data_audit.md
	$(TB) audit $(ARGS)

prepare:  ## cleaning variants + patient-level splits
	$(TB) prepare $(ARGS)

run:  ## run/resume the task grid only
	$(TB) run $(ARGS)

run-all:  ## ingest -> audit -> prepare -> tasks -> analysis -> report (foreground)
	$(TB) run-all $(ARGS)

pilot:  ## cost pilot (1 seed, 3 configs); combine with the machine profile: make pilot PROFILE=qflex
	$(TB) run-all --config $(CONFIG) --profile $(if $(PROFILE),$(PROFILE)$(comma),)pilot

status:  ## progress, ETA and failures
	$(TB) status $(ARGS)

analyze:  ## aggregate + statistics + figures + reports/summary.md
	$(TB) analyze $(ARGS)

launch-bg:  ## run-all detached in tmux (survives SSH drops); log in <outputs>/launch/
	bash scripts/launch_bg.sh "$(PROFILE)"

verify-gitignore:  ## bait files must all be ignored by git
	bash scripts/check_gitignore.sh

comma := ,
