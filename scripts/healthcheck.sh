#!/usr/bin/env bash
# Run the WP5 health suite (src/smallpc/health.py) under the GPU lock.
#
#   scripts/healthcheck.sh [--detach] [--phases A,B,C,D,E] [--run-dir DIR] [--no-aggregate]
#
# --detach       run through scripts/run-detached.sh --gpu (job dir printed; poll it with
#                scripts/job-status.sh). The full suite takes tens of minutes, so it is detached
#                (CLAUDE.md: anything over ~8 minutes). Without it the suite runs in the
#                foreground under scripts/with-gpu-lock.sh, which is fine for a single short phase.
# --phases LIST  comma-separated phases, run in the order given (default A,B,C,D,E)
# --run-dir DIR  reuse a run directory so finished phases (phase-*.json) are kept
# --no-aggregate do not write data/health/endpoints-<date>.json
#
# Writes data/health/endpoints-<UTC date>.json. Every llama-server is started and stopped through
# scripts/launch-server.sh and scripts/stop-server.sh by the Python module.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

detach=0
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --detach) detach=1 ;;
    --phases | --run-dir) args+=("$1" "${2:?$1 needs a value}"); shift ;;
    --no-aggregate) args+=("$1") ;;
    -h | --help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

if pgrep -x llama-server >/dev/null; then
  die "a llama-server process is already running (pgrep -a llama-server)"
fi

cd "$SMALLPC_REPO"
cmd=(uv run --frozen python -m smallpc.health "${args[@]}")
if [ "$detach" = 1 ]; then
  exec "$here/run-detached.sh" --gpu healthcheck -- "${cmd[@]}"
fi
exec "$here/with-gpu-lock.sh" "${cmd[@]}"
