#!/usr/bin/env bash
# Stop a server started by launch-server.sh: SIGINT, wait, then SIGKILL after a timeout.
#
#   scripts/stop-server.sh [--timeout SEC] <run-id | run-dir>
#
# --timeout SEC   seconds to wait after SIGINT before SIGKILL (default 60, or $SMALLPC_STOP_TIMEOUT)
#
# The pid's start time is checked first, so a recycled pid is never signalled. Writes
# <run-dir>/stop-status.json (method, exit code, seconds waited). The exit code is the one the
# supervisor recorded in <run-dir>/exit-code (128+N when the server died of signal N).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

timeout="${SMALLPC_STOP_TIMEOUT:-60}"
target=""
while [ $# -gt 0 ]; do
  case "$1" in
    --timeout) timeout="${2:?--timeout needs a value}"; shift ;;
    -h | --help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) [ -z "$target" ] || die "more than one run given"; target="$1" ;;
  esac
  shift
done
[ -n "$target" ] || die "usage: stop-server.sh [--timeout SEC] <run-id | run-dir>"

if [[ "$target" == */* ]]; then run_dir="$(realpath -- "$target")"; else run_dir="$LOG_ROOT/$target"; fi
[ -d "$run_dir" ] || die "no such run directory: $run_dir"
[ -s "$run_dir/server.pid" ] || die "no pidfile in $run_dir"
pid="$(<"$run_dir/server.pid")"
start="$(<"$run_dir/server.start")"

t0=$SECONDS
method="already_exited"
if proc_alive "$pid" "$start"; then
  method="sigint"
  kill -INT "$pid" 2>/dev/null || true
  deadline=$((SECONDS + timeout))
  while proc_alive "$pid" "$start" && [ "$SECONDS" -lt "$deadline" ]; do sleep 0.2; done
  if proc_alive "$pid" "$start"; then
    echo "$(basename "$0"): still running ${timeout}s after SIGINT; sending SIGKILL" >&2
    method="sigkill"
    kill -KILL "$pid" 2>/dev/null || true
    deadline=$((SECONDS + 10))
    while proc_alive "$pid" "$start" && [ "$SECONDS" -lt "$deadline" ]; do sleep 0.2; done
    ! proc_alive "$pid" "$start" || die "pid $pid is still alive after SIGKILL"
  fi
fi

# The supervisor writes exit-code right after the server ends.
for _ in $(seq 1 50); do
  [ -s "$run_dir/exit-code" ] && break
  sleep 0.1
done
exit_code="null"
[ -s "$run_dir/exit-code" ] && exit_code="$(<"$run_dir/exit-code")"

printf '{\n  "stopped_utc": "%s",\n  "pid": %s,\n  "method": "%s",\n  "exit_code": %s,\n  "waited_s": %s,\n  "sigint_timeout_s": %s\n}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$pid" "$method" "$exit_code" "$((SECONDS - t0))" "$timeout" \
  >"$run_dir/stop-status.json"
echo "stopped: method=$method exit_code=$exit_code ($run_dir/stop-status.json)"
