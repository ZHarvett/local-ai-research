#!/usr/bin/env bash
# Start llama-server from a server config. The only sanctioned way to start it (CLAUDE.md).
#
#   scripts/launch-server.sh [options] <server.toml>
#
# Options:
#   --dry-run              print the rendered argv and exit (no checks, nothing started)
#   --machine FILE         machine config (default configs/machine.toml)
#   --model-config FILE    model config (default configs/model.toml)
#   --run-id ID            run id (default <UTC timestamp>-<config name>)
#   --health-timeout SEC   seconds to wait for /health (default 300, or $SMALLPC_HEALTH_TIMEOUT)
#
# Renders the argv with `uv run python -m smallpc.render`, refuses to start if the binary is
# missing, the port is busy or the GPU lock is held by another job, then starts the server
# detached with its log, pidfile and exit code in data/logs/<run-id>/ and waits for /health.
#
# GPU lock: under scripts/with-gpu-lock.sh (SMALLPC_GPU_LOCK_HELD set) the lock must really be
# held, otherwise the variable is stale and we refuse. Without the wrapper, this script takes
# the lock itself on fd 9, which the server inherits, so it is held for the server's lifetime.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }

dry_run=0
machine=""
model_cfg=""
run_id=""
health_timeout="${SMALLPC_HEALTH_TIMEOUT:-300}"
server_toml=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry_run=1 ;;
    --machine) machine="$(realpath -- "${2:?--machine needs a value}")"; shift ;;
    --model-config) model_cfg="$(realpath -- "${2:?--model-config needs a value}")"; shift ;;
    --run-id) run_id="${2:?--run-id needs a value}"; shift ;;
    --health-timeout) health_timeout="${2:?--health-timeout needs a value}"; shift ;;
    -h | --help) usage; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) [ -z "$server_toml" ] || die "more than one config given"; server_toml="$(realpath -- "$1")" ;;
  esac
  shift
done
[ -n "$server_toml" ] || { usage >&2; exit 2; }
[ -f "$server_toml" ] || die "no such config: $server_toml"

render_args=()
[ -z "$machine" ] || render_args+=(--machine "$machine")
[ -z "$model_cfg" ] || render_args+=(--model-config "$model_cfg")

cd "$SMALLPC_REPO"
render() { uv run --frozen --quiet python -m smallpc.render "${render_args[@]}" "$@"; }

if [ "$dry_run" = 1 ]; then
  render "$server_toml"
  exit 0
fi

# ---- render the argv (NUL-separated, via a temp file so a render failure is not lost) ----
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
render --nul "$server_toml" >"$tmp" || die "could not render $server_toml"
mapfile -d '' -t argv <"$tmp"
gpu_index="$(render --gpu-index)"

host="" port="" slot_dir=""
for ((i = 1; i < ${#argv[@]}; i++)); do
  case "${argv[i]}" in
    --host) host="${argv[i + 1]}" ;;
    --port) port="${argv[i + 1]}" ;;
    --slot-save-path) slot_dir="${argv[i + 1]}" ;;
  esac
done
[ -n "$host" ] && [ -n "$port" ] || die "rendered argv has no explicit --host/--port"

# ---- preconditions ----
[ -x "${argv[0]}" ] || die "llama-server not found or not executable: ${argv[0]} (built in WP3)"

if [ -n "$(ss -H -ltn "sport = :$port")" ]; then
  die "port $port is already in use"
fi

mkdir -p "$(dirname "$GPU_LOCK_FILE")"
if [ -n "${SMALLPC_GPU_LOCK_HELD:-}" ]; then
  kill -0 "$SMALLPC_GPU_LOCK_HELD" 2>/dev/null ||
    die "SMALLPC_GPU_LOCK_HELD=$SMALLPC_GPU_LOCK_HELD names a process that is not running (stale variable)"
  if flock -n "$GPU_LOCK_FILE" true; then
    die "SMALLPC_GPU_LOCK_HELD is set but the GPU lock is not held (stale variable)"
  fi
else
  exec 9>"$GPU_LOCK_FILE"
  flock -n 9 || die "the GPU lock is held by another job ($GPU_LOCK_FILE)"
fi

if [ -n "$slot_dir" ]; then
  case "$slot_dir" in
    /dev/shm/local-ai-research-*) mkdir -p "$slot_dir" ;;
    *) die "slot-save path must be under /dev/shm/local-ai-research-*: $slot_dir" ;;
  esac
fi

# ---- run directory ----
run_id="${run_id:-$(date -u +%Y%m%dT%H%M%SZ)-$(basename "$server_toml" .toml)}"
run_dir="$LOG_ROOT/$run_id"
mkdir -p "$LOG_ROOT"
mkdir "$run_dir" || die "run directory already exists: $run_dir"
printf '%s\n' "${argv[@]}" >"$run_dir/argv.txt"
cp "$server_toml" "$run_dir/server.toml"

# ---- start (detached, own session) ----
export CUDA_VISIBLE_DEVICES="$gpu_index"
setsid -f "$here/_supervise.sh" "$run_dir" "${argv[@]}" </dev/null >/dev/null 2>&1

for _ in $(seq 1 100); do
  [ -s "$run_dir/server.pid" ] && break
  sleep 0.1
done
[ -s "$run_dir/server.pid" ] || die "supervisor did not start the server (see $run_dir)"
server_pid="$(<"$run_dir/server.pid")"

# ---- wait for /health ----
deadline=$((SECONDS + health_timeout))
while :; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://$host:$port/health" || true)"
  [ "$code" = 200 ] && break
  if [ -s "$run_dir/exit-code" ]; then
    tail -n 30 "$run_dir/server.log" >&2 || true
    die "server exited with code $(<"$run_dir/exit-code") before becoming healthy ($run_dir)"
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    tail -n 30 "$run_dir/server.log" >&2 || true
    "$here/stop-server.sh" --timeout 30 "$run_dir" || true
    die "no healthy /health within ${health_timeout}s; server stopped ($run_dir)"
  fi
  sleep 1
done

echo "server healthy: pid=$server_pid http://$host:$port"
echo "run-dir: $run_dir"
