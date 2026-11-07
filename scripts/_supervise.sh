#!/usr/bin/env bash
# Internal: runs one server under supervision. Started detached by launch-server.sh.
#
#   _supervise.sh RUN_DIR COMMAND [ARGS...]
#
# Writes server.start and server.pid (once the server is running) and exit-code (when it ends),
# so stop-server.sh can record a real exit status even though the server is not its child.
set -u
set -m # job control: the background server keeps default SIGINT handling

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

rundir="$1"
shift

"$@" >>"$rundir/server.log" 2>&1 &
pid=$!
printf '%s\n' "$(proc_fields "$pid" | cut -d' ' -f2)" >"$rundir/server.start"
printf '%s\n' "$pid" >"$rundir/server.pid"

wait "$pid"
printf '%s\n' "$?" >"$rundir/exit-code"
