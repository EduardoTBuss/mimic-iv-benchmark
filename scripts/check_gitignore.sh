#!/usr/bin/env bash
# Plants bait files that must NEVER be committed (PhysioNet DUA) and checks that git ignores
# every one of them, both via `git check-ignore` and via `git add --dry-run -A`.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
baits=(
  data/triage.csv
  x.csv
  x.csv.gz
  mimic-iv-ed-2.2.zip
  outputs/campaigns/c/private/predictions.parquet
  outputs/campaigns/c/tables/metrics.json
  reports/tables/x.csv
  reports/x.parquet
  model.joblib
  model.pkl
  predictions_test.json
  foo/private/rows.json
  excluded_rows.json
  datasets/mimic/triage.feather
  src/triagebench/data/leak.csv
  src/triagebench/data/leak.parquet
  outputs/prepared/x/private/A.parquet
)
created=()
cleanup() { for f in "${created[@]}"; do rm -f "$f"; d=$(dirname "$f"); while [ "$d" != "." ] && rmdir "$d" 2>/dev/null; do d=$(dirname "$d"); done; done; }
trap cleanup EXIT
for f in "${baits[@]}"; do
  if [ ! -e "$f" ]; then mkdir -p "$(dirname "$f")"; echo bait > "$f"; created+=("$f"); fi
done
fail=0
for f in "${baits[@]}"; do
  if ! git check-ignore -q "$f"; then echo "NOT IGNORED: $f"; fail=1; fi
done
would_stage=$(git add --dry-run -A 2>/dev/null || true)
for f in "${baits[@]}"; do
  if grep -qF "'$f'" <<<"$would_stage"; then echo "git add would stage: $f"; fail=1; fi
done
if [ "$fail" -eq 0 ]; then echo "gitignore OK: ${#baits[@]} bait files ignored"; else echo "gitignore FAILED"; exit 1; fi
