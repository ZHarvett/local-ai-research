#!/usr/bin/env bash
# Start a long job detached from this session and return immediately.
#
#   scripts/run-detached.sh [--gpu] <job-name> -- <command...>
#
# Creates data/logs/jobs/<job-name>-<UTC timestamp>/ with job.log (stdout+stderr), status.json
# (command, start/end time, exit code, state running|done|failed) and pid, and prints that
# directory. The job runs under setsid + nohup, so it survives the calling session.
# With --gpu the command runs through scripts/with-gpu-lock.sh, and the job is refused up front
# if the GPU lock is currently held (the check is repeated atomically by the wrapper itself).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

usage() {
  echo "usage: $(basename "$0") [--gpu] <job-name> -- <command...>" >&2
  exit 2
}

gpu=0
if [ "${1:-}" = "--gpu" ]; then
  gpu=1
  shift
fi
[ $# -ge 3 ] || usage
name="$1"
shift
[ "$1" = "--" ] || usage
shift
[[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || die "job name must match [A-Za-z0-9._-]+: $name"

if [ "$gpu" = 1 ]; then
  mkdir -p "$(dirname "$GPU_LOCK_FILE")"
  # Probe the lock on a throwaway fd; released again when the subshell exits.
  if ! (
    exec 8>"$GPU_LOCK_FILE"
    flock -n 8
  ); then
    echo "$(basename "$0"): refusing to start: the GPU lock is held ($GPU_LOCK_FILE)" >&2
    exit 75
  fi
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
jobs_root="${SMALLPC_JOBS_ROOT:-$LOG_ROOT/jobs}"
jobdir="$jobs_root/$name-$stamp"
mkdir -p "$jobdir"
jobdir="$(cd "$jobdir" && pwd)"

if [ "$gpu" = 1 ]; then
  set -- "$here/with-gpu-lock.sh" "$@"
fi

cmd_json="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "$@")"
start_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 - "$jobdir/status.json" "$name" "$cmd_json" "$start_iso" "$gpu" <<'PY'
import json, sys
path, name, cmd, start, gpu = sys.argv[1:]
status = {"job": name, "command": json.loads(cmd), "gpu": gpu == "1", "start": start,
          "end": None, "exit_code": None, "state": "running"}
open(path, "w").write(json.dumps(status, indent=2) + "\n")
PY

# Runner: executes the command, then rewrites status.json with the outcome.
# Written as a function body passed to bash -c so quoting of the user command is preserved.
# shellcheck disable=SC2016  # the single quotes are deliberate: expanded by the inner bash
runner='
jobdir=$1; shift
cd "$SMALLPC_JOB_CWD"
"$@" >"$jobdir/job.log" 2>&1
rc=$?
python3 - "$jobdir/status.json" "$rc" <<"PY"
import datetime, json, sys
path, rc = sys.argv[1], int(sys.argv[2])
s = json.load(open(path))
s["end"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
s["exit_code"] = rc
s["state"] = "done" if rc == 0 else "failed"
tmp = path + ".tmp"
open(tmp, "w").write(json.dumps(s, indent=2) + "\n")
import os; os.replace(tmp, path)
PY
'

SMALLPC_JOB_CWD="$PWD" setsid nohup bash -c "$runner" _ "$jobdir" "$@" \
  >/dev/null 2>&1 </dev/null 9>&- &
echo "$!" >"$jobdir/pid"
disown
echo "$jobdir"
