#!/usr/bin/env bash
# Quiet-machine check for Stages 3 and 4 (gate G3, plan v1.7): is any app running that must be closed?
#
#   scripts/check-quiet.sh [options]
#
# Options:
#   --config FILE   blocklist (default configs/quiet-check.toml)
#   --ps-file FILE  read `ps -eo comm=,rss=` output from FILE instead of running ps (tests)
#   --no-cpu        skip the CPU idle line (it takes the 10 s window of the runner's precondition)
#   --json          machine-readable output
#
# Looks at process NAMES only (`ps -eo comm`, plus the resident size): never window titles, URLs,
# command-line arguments or file contents. Prints the blocklisted apps that run, warns about any
# process other than llama-server and claude above 1.5 GiB resident (name and size only), prints the
# CPU idle figure as information, and exits 1 if a blocklisted app is running (0 if quiet, 2 on a
# usage error). It is read-only and does not touch the GPU.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }

ps_file=""
py_args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --config) py_args+=(--config "$(realpath -- "${2:?--config needs a file}")"); shift ;;
    --ps-file) ps_file="$(realpath -- "${2:?--ps-file needs a file}")"; shift ;;
    --no-cpu) py_args+=(--no-cpu) ;;
    --json) py_args+=(--json) ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

cd "$SMALLPC_REPO"
run() { uv run --frozen --quiet python -m smallpc.stage3.quiet "${py_args[@]}" "$@"; }

if [ -n "$ps_file" ]; then
  [ -f "$ps_file" ] || die "no such file: $ps_file"
  run --ps-file "$ps_file"
else
  ps -eo comm=,rss= | run
fi
