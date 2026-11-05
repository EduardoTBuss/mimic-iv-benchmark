#!/usr/bin/env bash
# Start `run-all` detached so it survives SSH disconnects.
#   scripts/launch_bg.sh <profile>            e.g. scripts/launch_bg.sh qflex
#   SESSION=name scripts/launch_bg.sh qflex   custom tmux session name
# Safe to call twice: the campaign runner holds a lock and resumes finished work.
set -euo pipefail
cd "$(dirname "$0")/.."
PROFILE="${1:-}"
SESSION="${SESSION:-triagebench}"
PY="${PY:-.venv/bin/python}"
if [ -d ../launch-logs ]; then LOGDIR="${LOGDIR:-../launch-logs}"; else LOGDIR="${LOGDIR:-launch-logs}"; fi   # server layout: ~/mimic-iv-benchmark/launch-logs
mkdir -p "$LOGDIR"
LOG="$LOGDIR/run-all-$(date +%Y%m%d-%H%M%S).log"
PROFILE_ARG=""
[ -n "$PROFILE" ] && PROFILE_ARG="--profile $PROFILE"
CMD="PYTHONPATH=src $PY -m triagebench run-all --config configs/main.yaml $PROFILE_ARG >> '$LOG' 2>&1; echo \"EXIT=\$? \$(date -Is)\" >> '$LOG'"

if command -v tmux >/dev/null 2>&1; then
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "tmux session '$SESSION' already exists -> tmux attach -t $SESSION"
    exit 1
  fi
  tmux new-session -d -s "$SESSION" "bash -c \"$CMD\""
  echo "started in tmux session '$SESSION' | log: $LOG | attach: tmux attach -t $SESSION (detach: Ctrl+B then D)"
else
  nohup setsid bash -c "$CMD" >/dev/null 2>&1 < /dev/null &
  echo "started with nohup (pid $!) | log: $LOG"
fi
