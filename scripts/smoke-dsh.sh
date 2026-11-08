#!/usr/bin/env bash
# dsh smoke test (WP7): fix the toy task with `dsh --profile headless` against the stock-64k server.
#
#   scripts/run-detached.sh --gpu smoke-dsh -- scripts/smoke-dsh.sh
#   scripts/smoke-dsh.sh --probe-only        # permission probe only: no GPU, no llama-server
#
# Same flow as scripts/smoke-opencode.sh (see there). dsh's own permission settings are the shipped
# ones: DSH_PERMISSION_MODE=workspace-write (file sandbox) with approval policy "ask", which has no
# answerer in headless mode and so fails closed; the probe checks that. dsh's sandbox does not
# restrict bash network access or /tmp, so scripts/_sandbox.sh's private network namespace (only
# the server and a deny-all logging proxy reachable) and its read-only file system are what
# confine the run. Telemetry is switched off (DSH_TELEMETRY_MODE=DISABLED), web tools are disabled
# in the profile patch. Results: data/harness/smoke-dsh-<UTC>/.
# Exit codes: 0 pass, 3 the model failed twice, 4 other failure, 5 the permission probe failed.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"
# shellcheck source=_smoke_lib.sh
source "$here/_smoke_lib.sh"

HARNESS=dsh
HARNESS_CONFIG_NAME=dsh.cordis.patch.yml
SMOKE_TIMEOUT=1200
server_cfg="$SMALLPC_REPO/configs/server/examples/stock-64k.toml"
probe_only=0
while [ $# -gt 0 ]; do
  case "$1" in
    --probe-only) probe_only=1 ;;
    --server-config) server_cfg="$(realpath -- "${2:?--server-config needs a value}")"; shift ;;
    --timeout) SMOKE_TIMEOUT="${2:?--timeout needs a value}"; shift ;;
    -h | --help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

DSH_JS="$SMALLPC_REPO/third_party/node/node_modules/@deepseek-ai/dsh/lib/bin.js"
NODE=/usr/bin/node
DSH_HOME_DIR="$STATE/dsh/dsh-home"
OUT="$SMALLPC_REPO/data/harness/smoke-dsh-$(date -u +%Y%m%dT%H%M%SZ)"
trap smoke_cleanup EXIT

dsh_run() { # TIMEOUT PATCH SCRATCH SERVER_PORT PROXY_PORT PROMPT
  local tmo="$1" patch="$2" scratch="$3" port="$4" proxy="$5" prompt="$6"
  env_args dsh --dsh-home "$DSH_HOME_DIR"
  timeout --signal=INT --kill-after=30 "$tmo" "$here/_sandbox.sh" --kind dsh --rw "$scratch" \
    --cwd "$scratch" --path "$SMALLPC_REPO/.venv/bin:/usr/bin:/bin" --proxy "$proxy" \
    --bridge "$port" --bridge "$proxy" "${ENV_ARGS[@]}" -- \
    "$NODE" "$DSH_JS" --profile headless --patch "$patch" --json "$prompt"
}

harness_probe_run() { # KIND DIR SCRATCH FAKE_PORT PROXY_PORT
  local d="$2" scratch="$3" fake="$4" proxy="$5"
  "$PY" -I -m smallpc.harness render-dsh --props-url "http://127.0.0.1:$fake" \
    --host 127.0.0.1 --port "$fake" --out "$d/dsh.cordis.patch.yml"
  dsh_run 180 "$d/dsh.cordis.patch.yml" "$scratch" "$fake" "$proxy" "run the probe" \
    >"$d/events.jsonl" 2>"$d/debug.log" </dev/null
}

harness_attempt_run() { # DIR SCRATCH SERVER_PORT PROXY_PORT PROMPT
  dsh_run "$SMOKE_TIMEOUT" "$OUT/$HARNESS_CONFIG_NAME" "$2" "$3" "$4" "$5" \
    >"$1/events.jsonl" 2>"$1/debug.log" </dev/null
}

# ---- preflight ----
[ -f "$DSH_JS" ] || die "dsh is not installed: run scripts/install-harnesses.sh"
[ -x "$PY" ] && [ -x "$SMALLPC_REPO/.venv/bin/pytest" ] || die "the repository virtualenv is missing (uv sync)"
mkdir -p "$OUT" "$STATE"
pinned="$("$PY" -I -c 'from smallpc.config import load_harness; print(load_harness().package("@deepseek-ai/dsh").version)')"
installed="$(sandboxed_offline dsh "$NODE" "$DSH_JS" --version)"
[ "$installed" = "$pinned" ] || die "installed dsh $installed is not the pinned $pinned"
smoke_log "dsh $installed (pinned $pinned); output: $OUT"

smoke_probe dsh || { scrub_dir "$OUT/probe-dsh"; exit 5; }
scrub_dir "$OUT/probe-dsh"
[ "$probe_only" = 0 ] || { smoke_log "probe-only: done"; exit 0; }

# ---- real run (needs the GPU lock, taken by run-detached.sh --gpu) ----
[ -n "${SMALLPC_GPU_LOCK_HELD:-}" ] || die "run this through scripts/run-detached.sh --gpu (GPU lock)"
SMOKE_PASSED=0
SMOKE_MODEL_FAILED=0
smoke_gpu "$server_cfg"
for d in "$OUT"/attempt-*; do [ -d "$d" ] && scrub_dir "$d"; done
scrub_dir "$OUT"
if [ "$SMOKE_PASSED" = 1 ]; then
  smoke_log "dsh smoke test: PASS ($OUT)"
  exit 0
fi
smoke_log "dsh smoke test: FAIL ($OUT)"
[ "$SMOKE_MODEL_FAILED" = 1 ] && exit 3
exit 4
