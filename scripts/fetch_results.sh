#!/usr/bin/env bash
# Bring a campaign's AGGREGATE results from a server to the notebook (never the private/ dirs).
#   scripts/fetch_results.sh <ssh-alias> <campaign-id>
#   SSH=/c/Windows/System32/OpenSSH/ssh.exe scripts/fetch_results.sh qflex main-xxxxxxxxxx
# outputs/remote/<host>/campaigns/<id>/ (gitignored) + reports/campaigns/<id>/ (masked, committable)
set -euo pipefail
HOST="${1:?usage: fetch_results.sh <ssh-alias> <campaign-id>}"
CID="${2:?campaign id}"
SSH="${SSH:-ssh}"
cd "$(git rev-parse --show-toplevel)"
dest="outputs/remote/$HOST"
mkdir -p "$dest" reports/campaigns
"$SSH" "$HOST" "cd mimic-iv-benchmark && tar czf - --exclude='*/private' --exclude='*/private/*' outputs/campaigns/$CID" \
  | tar xzf - -C "$dest" --strip-components=1
"$SSH" "$HOST" "cd mimic-iv-benchmark && test -d reports/campaigns/$CID && tar czf - -C reports/campaigns $CID" \
  | tar xzf - -C reports/campaigns
if find "$dest" reports/campaigns/"$CID" -path '*private*' | grep -q .; then
  echo "ERROR: a private path was copied; removing it" >&2
  find "$dest" reports/campaigns/"$CID" -path '*private*' -prune -exec rm -rf {} +
  exit 1
fi
echo "fetched $CID from $HOST -> $dest/campaigns/$CID and reports/campaigns/$CID"
