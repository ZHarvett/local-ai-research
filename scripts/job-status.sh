#!/usr/bin/env bash
# Print status.json and the last 20 lines of the log of a detached job.
#
#   scripts/job-status.sh <job-dir>
#
# If the recorded pid is gone while the state still says "running" (job killed, e.g. by the
# OOM killer or a reboot), says so instead of reporting "running" forever.
set -euo pipefail

[ $# -eq 1 ] && [ -d "$1" ] || {
  echo "usage: $(basename "$0") <job-dir>" >&2
  exit 2
}
dir="$1"
echo "== status.json"
cat "$dir/status.json"
if grep -q '"state": "running"' "$dir/status.json" && [ -f "$dir/pid" ]; then
  pid="$(cat "$dir/pid")"
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "!! state is 'running' but pid $pid is gone: the job died without recording an exit code"
  fi
fi
echo "== job.log (last 20 lines)"
tail -n 20 "$dir/job.log" 2>/dev/null || echo "(no log yet)"
