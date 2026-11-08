#!/usr/bin/env bash
# OpenCode smoke test (WP7): fix the toy task with `opencode run` against the stock-64k server.
#
#   scripts/run-detached.sh --gpu smoke-opencode -- scripts/smoke-opencode.sh
#   scripts/smoke-opencode.sh --probe-only        # permission probes only: no GPU, no llama-server
#
# Options: --server-config FILE (default configs/server/examples/stock-64k.toml)
#          --timeout SEC        hard timeout of one `opencode run` (default 1200)
#
# Order: preflight, two permission probes against a scripted fake model (an unprompted allow, a
# missed deny or an `ask` that is not auto-rejected aborts before the GPU is touched), then the
# real run: server via launch-server.sh, config rendered from /props, `opencode run` in a fresh
# scratch copy of the toy task under /tmp, an independent pytest and test-file check, one retry if
# the model failed to fix the bug, server stopped. Every OpenCode execution goes through
# scripts/_sandbox.sh (bubblewrap, repo-local HOME/XDG, only the server and a deny-all logging
# proxy reachable). Results are scrubbed and written to data/harness/smoke-opencode-<UTC>/.
# Exit codes: 0 pass, 3 the model failed twice, 4 other failure, 5 a permission probe failed.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"
# shellcheck source=_smoke_lib.sh
source "$here/_smoke_lib.sh"

HARNESS=opencode
HARNESS_CONFIG_NAME=opencode.json
PROBE_KINDS=(opencode opencode-ask)
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

OC="$SMALLPC_REPO/third_party/node/node_modules/opencode-ai/bin/opencode.exe"
OUT="$SMALLPC_REPO/data/harness/smoke-opencode-$(date -u +%Y%m%dT%H%M%SZ)"
trap smoke_cleanup EXIT

harness_probe_run() { # KIND DIR SCRATCH FAKE_PORT PROXY_PORT
  local kind="$1" d="$2" scratch="$3" fake="$4" proxy="$5" extra=()
  [ "$kind" != opencode-ask ] || extra=(--probe-ask-pattern "curl *")
  "$PY" -I -m smallpc.harness render-opencode --props-url "http://127.0.0.1:$fake" \
    --host 127.0.0.1 --port "$fake" --out "$d/opencode.json" "${extra[@]}"
  env_args opencode
  timeout --signal=INT --kill-after=10 180 "$here/_sandbox.sh" --kind opencode --rw "$scratch" \
    --cwd "$scratch" --path "$SMALLPC_REPO/.venv/bin:/usr/bin:/bin" --proxy "$proxy" \
    --bridge "$fake" --bridge "$proxy" --env "OPENCODE_CONFIG=$d/opencode.json" "${ENV_ARGS[@]}" -- \
    "$OC" run --format json --print-logs --log-level DEBUG "run the probe" \
    >"$d/events.jsonl" 2>"$d/debug.log" </dev/null
}

harness_attempt_run() { # DIR SCRATCH SERVER_PORT PROXY_PORT PROMPT
  local d="$1" scratch="$2" port="$3" proxy="$4" prompt="$5"
  env_args opencode
  timeout --signal=INT --kill-after=30 "$SMOKE_TIMEOUT" "$here/_sandbox.sh" --kind opencode \
    --rw "$scratch" --cwd "$scratch" --path "$SMALLPC_REPO/.venv/bin:/usr/bin:/bin" \
    --proxy "$proxy" --bridge "$port" --bridge "$proxy" \
    --env "OPENCODE_CONFIG=$OUT/opencode.json" "${ENV_ARGS[@]}" -- \
    "$OC" run --format json --print-logs --log-level DEBUG "$prompt" \
    >"$d/events.jsonl" 2>"$d/debug.log" </dev/null
}

# ---- preflight ----
[ -x "$OC" ] || die "OpenCode is not installed: run scripts/install-harnesses.sh and --rebuild"
[ -x "$PY" ] && [ -x "$SMALLPC_REPO/.venv/bin/pytest" ] || die "the repository virtualenv is missing (uv sync)"
mkdir -p "$OUT" "$STATE"
pinned="$("$PY" -I -c 'from smallpc.config import load_harness; print(load_harness().package("opencode-ai").version)')"
installed="$(sandboxed_offline opencode "$OC" --version)"
[ "$installed" = "$pinned" ] || die "installed OpenCode $installed is not the pinned $pinned"
smoke_log "OpenCode $installed (pinned $pinned); output: $OUT"

for kind in "${PROBE_KINDS[@]}"; do
  smoke_probe "$kind" || { scrub_dir "$OUT/probe-$kind"; exit 5; }
  scrub_dir "$OUT/probe-$kind"
done
[ "$probe_only" = 0 ] || { smoke_log "probe-only: done"; exit 0; }

# ---- real run (needs the GPU lock, taken by run-detached.sh --gpu) ----
[ -n "${SMALLPC_GPU_LOCK_HELD:-}" ] || die "run this through scripts/run-detached.sh --gpu (GPU lock)"
SMOKE_PASSED=0
SMOKE_MODEL_FAILED=0
smoke_gpu "$server_cfg"
for d in "$OUT"/attempt-*; do [ -d "$d" ] && scrub_dir "$d"; done
scrub_dir "$OUT"
if [ "$SMOKE_PASSED" = 1 ]; then
  smoke_log "OpenCode smoke test: PASS ($OUT)"
  exit 0
fi
smoke_log "OpenCode smoke test: FAIL ($OUT)"
[ "$SMOKE_MODEL_FAILED" = 1 ] && exit 3
exit 4
