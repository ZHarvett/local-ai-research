#!/usr/bin/env bash
# Run a command while holding the GPU lock (one GPU job at a time; CLAUDE.md hard rule).
#
#   scripts/with-gpu-lock.sh COMMAND [ARGS...]
#
# Takes a non-blocking flock on <repo>/.locks/gpu.lock (fd 9) and exits 75 if another job holds
# it. The command is exec'd with SMALLPC_GPU_LOCK_HELD=<pid> set, which tells launch-server.sh
# that the lock is already held on its behalf. fd 9 stays open in everything the command starts,
# so a server that outlives launch-server.sh keeps the lock until it exits.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

if [ $# -lt 1 ]; then
  echo "usage: $(basename "$0") COMMAND [ARGS...]" >&2
  exit 2
fi

mkdir -p "$(dirname "$GPU_LOCK_FILE")"
exec 9>"$GPU_LOCK_FILE"
if ! flock -n 9; then
  echo "$(basename "$0"): the GPU lock is held by another job ($GPU_LOCK_FILE)" >&2
  exit 75
fi
export SMALLPC_GPU_LOCK_HELD="$$"
exec "$@"
