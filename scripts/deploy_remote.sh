#!/usr/bin/env bash
# Ship the current commit (and optionally the dataset zip) to a server and build the venv there.
#   scripts/deploy_remote.sh <ssh-alias> [path/to/mimic-iv-ed-2.2.zip]
#   SSH=/c/Windows/System32/OpenSSH/ssh.exe SCP=/c/Windows/System32/OpenSSH/scp.exe scripts/deploy_remote.sh qflex
#
# Server layout (owner-only, mode 700):
#   ~/mimic-iv-benchmark/{code, data/zip, data/extracted, outputs, reports, bundles, launch-logs}
# Code travels as a git bundle (no GitHub credentials on the server). No global installs: a
# .venv inside code/ is built from the hash-pinned requirements-lock.txt.
set -euo pipefail
HOST="${1:?usage: deploy_remote.sh <ssh-alias> [zip]}"
ZIP="${2:-}"
SSH="${SSH:-ssh}"
SCP="${SCP:-scp}"
cd "$(git rev-parse --show-toplevel)"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "working tree has uncommitted changes: commit first" >&2
  exit 1
fi
COMMIT="$(git rev-parse --short HEAD)"
TMP="$(mktemp -d)"
BUNDLE_NAME="mimic-iv-benchmark-$COMMIT.bundle"
git bundle create -q "$TMP/$BUNDLE_NAME" HEAD

"$SSH" "$HOST" 'umask 077; mkdir -p mimic-iv-benchmark/bundles mimic-iv-benchmark/code mimic-iv-benchmark/data/zip mimic-iv-benchmark/data/extracted mimic-iv-benchmark/outputs mimic-iv-benchmark/reports mimic-iv-benchmark/launch-logs; chmod 700 mimic-iv-benchmark'
"$SCP" -q "$TMP/$BUNDLE_NAME" "$HOST:mimic-iv-benchmark/bundles/"

if [ -n "$ZIP" ]; then
  name="$(basename "$ZIP")"
  if ! "$SSH" "$HOST" "test -f mimic-iv-benchmark/data/zip/$name"; then
    echo "copying $name ($(du -h "$ZIP" | cut -f1)) ..."
    "$SCP" -q "$ZIP" "$HOST:mimic-iv-benchmark/data/zip/"
  fi
  local_sha="$(sha256sum "$ZIP" | cut -d' ' -f1)"
  remote_sha="$("$SSH" "$HOST" "sha256sum mimic-iv-benchmark/data/zip/$name" | cut -d' ' -f1)"
  if [ "$local_sha" != "$remote_sha" ]; then
    echo "zip SHA256 mismatch on $HOST" >&2
    exit 1
  fi
  echo "zip OK on $HOST (sha256 ${remote_sha:0:16})"
fi

"$SSH" "$HOST" "set -e; umask 077; cd mimic-iv-benchmark
  B=\$PWD/bundles/$BUNDLE_NAME
  if [ ! -d code/.git ]; then rm -rf code; git clone -q \$B code; fi
  cd code
  git fetch -q \$B '+HEAD:refs/remotes/deploy/head'
  git checkout -q --detach $COMMIT
  if [ ! -x .venv/bin/python ] || ! cmp -s requirements-lock.txt .venv/.lock-installed; then
    rm -rf .venv
    python3.12 -m venv .venv
    .venv/bin/python -m pip install -q --upgrade pip
    nice -n 10 .venv/bin/python -m pip install -q --require-hashes -r requirements-lock.txt
    cp requirements-lock.txt .venv/.lock-installed
  fi
  echo \"deployed \$(git rev-parse --short HEAD) on \$(hostname)\""
rm -rf "$TMP"
