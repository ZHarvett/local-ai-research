# shellcheck shell=bash
# Shared helpers, sourced by the launch/stop/lock scripts. Defines functions and variables only.

SMALLPC_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Overridable for tests; the defaults live inside the repo (both are gitignored).
# shellcheck disable=SC2034  # used by the scripts that source this file
GPU_LOCK_FILE="${SMALLPC_GPU_LOCK_FILE:-$SMALLPC_REPO/.locks/gpu.lock}"
# shellcheck disable=SC2034
LOG_ROOT="${SMALLPC_LOG_ROOT:-$SMALLPC_REPO/data/logs}"

die() {
  echo "$(basename "$0"): error: $*" >&2
  exit 1
}

# proc_fields <pid>: print "<state> <starttime>" from /proc/<pid>/stat (fields 3 and 22).
# The command name (field 2) may contain spaces and parentheses, so cut at the last ") ".
proc_fields() {
  local stat rest
  stat="$(cat "/proc/$1/stat" 2>/dev/null)" || return 1
  rest="${stat##*) }"
  read -r -a _f <<<"$rest"
  echo "${_f[0]} ${_f[19]}"
}

# proc_alive <pid> <starttime>: true if that exact process (not a recycled pid) is running.
proc_alive() {
  local fields state start
  fields="$(proc_fields "$1")" || return 1
  read -r state start <<<"$fields"
  [ "$state" != "Z" ] && [ "$start" = "$2" ]
}
