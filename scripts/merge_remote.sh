#!/usr/bin/env bash
# Move the DONE tasks of a campaign from one server to another (same campaign id), e.g. the
# values-only variant computed on the x299 into the Q-FLEX campaign before the final analysis.
#   scripts/merge_remote.sh <src-alias> <dst-alias> <campaign-id> [task-glob]
#   DST_SSH=/c/Windows/System32/OpenSSH/ssh.exe scripts/merge_remote.sh x299 qflex main-38c9f7c0a8 'C_values_only__*'
# Task folders include private per-stay predictions: they stream server -> pipe -> server
# (owner-only dirs on both ends) and are never written on the notebook.
set -euo pipefail
SRC="${1:?src}"; DST="${2:?dst}"; CID="${3:?campaign id}"; GLOB="${4:-*}"
SRC_SSH="${SRC_SSH:-ssh}"; DST_SSH="${DST_SSH:-ssh}"; DST_CODE="${DST_CODE:-code}"
STAGE="mimic-iv-benchmark/outputs/incoming/$CID-from-$SRC"
"$SRC_SSH" "$SRC" "cd mimic-iv-benchmark/outputs/campaigns/$CID && tar czf - campaign.json manifest.json \$(ls -d tasks/$GLOB)" \
  | "$DST_SSH" "$DST" "umask 077; rm -rf $STAGE; mkdir -p $STAGE && tar xzf - -C $STAGE && cd mimic-iv-benchmark/$DST_CODE && \
      PYTHONPATH=src .venv/bin/python -m triagebench merge --campaign ../outputs/campaigns/$CID --from ../outputs/incoming/$CID-from-$SRC"
