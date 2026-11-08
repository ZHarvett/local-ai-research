# shellcheck shell=bash
# shellcheck disable=SC2034  # PROXY_*, FAKE_* and ENV_ARGS are read by the scripts that source this
# Shared helpers for scripts/smoke-opencode.sh and scripts/smoke-dsh.sh (sourced; functions only).
# Expects _common.sh to be sourced first (SMALLPC_REPO, die, GPU_LOCK_FILE).

PY="$SMALLPC_REPO/.venv/bin/python"
STATE="$SMALLPC_REPO/third_party/harness-state"
TOY="$SMALLPC_REPO/tests/fixtures/toy-task"
SCRATCH_GLOB="/tmp/local-ai-research-smoke-"

smoke_log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# make_scratch: fresh copy of the toy task in a git repository with one commit, so the harness
# sees a project rooted there. Prints the path. No global git config is read or written.
make_scratch() {
  local d
  d="$(mktemp -d "${SCRATCH_GLOB}XXXXXX")"
  cp "$TOY"/*.py "$TOY/PROMPT.txt" "$d/"
  (
    cd "$d" || exit 1
    export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
    git init -q .
    git add -A
    git -c user.name=smoke -c user.email=smoke@example.invalid commit -q -m "toy task"
  )
  echo "$d"
}

# remove_scratch DIR: only paths that match the scratch pattern are ever removed.
remove_scratch() {
  case "$1" in
    "$SCRATCH_GLOB"??????) rm -rf -- "$1" ;;
    *) echo "refusing to remove $1" >&2 ;;
  esac
}

# start_proxy LOGFILE: deny-all logging proxy; sets PROXY_PID and PROXY_PORT.
start_proxy() {
  local portfile
  portfile="$(mktemp "$STATE/proxy-port-XXXXXX")"
  "$PY" -I -m smallpc.netproxy --log "$1" --port-file "$portfile" &
  PROXY_PID=$!
  for _ in $(seq 1 100); do [ -s "$portfile" ] && break; sleep 0.1; done
  [ -s "$portfile" ] || die "proxy did not start"
  PROXY_PORT="$(<"$portfile")"
  rm -f "$portfile"
}

# start_fake_model SCRIPT_JSON: scripted OpenAI-compatible endpoint; sets FAKE_PID and FAKE_PORT.
start_fake_model() {
  local portfile
  portfile="$(mktemp "$STATE/fake-port-XXXXXX")"
  "$PY" -I "$SMALLPC_REPO/tests/fixtures/fake_openai_server.py" --port-file "$portfile" \
    --script "$1" --model fake-model &
  FAKE_PID=$!
  for _ in $(seq 1 100); do [ -s "$portfile" ] && break; sleep 0.1; done
  [ -s "$portfile" ] || die "fake model did not start"
  FAKE_PORT="$(<"$portfile")"
  rm -f "$portfile"
}

# env_args HARNESS: --env K=V arguments for _sandbox.sh from smallpc.harness (into array ENV_ARGS)
env_args() {
  ENV_ARGS=()
  local line
  while IFS= read -r line; do ENV_ARGS+=(--env "$line"); done < <("$PY" -I -m smallpc.harness env "$@")
}

# sandboxed_offline KIND COMMAND...: run a harness binary with no network at all (informational).
sandboxed_offline() {
  local kind="$1"
  shift
  "$SMALLPC_REPO/scripts/_sandbox.sh" --kind "$kind" --no-net -- "$@"
}

# ---------------------------------------------------------------------------------------------
# Generic smoke flow. The calling script defines two callbacks and sets HARNESS (opencode|dsh),
# OUT (output directory) and PROBE_KINDS (array):
#   harness_probe_run KIND DIR SCRATCH FAKE_PORT PROXY_PORT
#       run the harness against the scripted fake model; write DIR/events.jsonl and DIR/debug.log
#   harness_attempt_run DIR SCRATCH SERVER_PORT PROXY_PORT PROMPT
#       run the harness against the real server; write DIR/events.jsonl and DIR/debug.log
# ---------------------------------------------------------------------------------------------

CLEAN_PIDS=()
CLEAN_SCRATCH=()
SERVER_RUN_DIR=""
TELEMETRY_PID=""

smoke_cleanup() {
  local rc=$?
  trap - EXIT
  [ -z "$TELEMETRY_PID" ] || kill -INT "$TELEMETRY_PID" 2>/dev/null || true
  for p in "${CLEAN_PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
  if [ -n "$SERVER_RUN_DIR" ] && [ -s "$SERVER_RUN_DIR/server.pid" ]; then
    "$SMALLPC_REPO/scripts/stop-server.sh" --timeout 90 "$SERVER_RUN_DIR" || true
  fi
  for d in "${CLEAN_SCRATCH[@]}"; do remove_scratch "$d"; done
  wait 2>/dev/null || true
  exit "$rc"
}

scrub_dir() {
  local f tmp
  for f in "$1"/*.json "$1"/*.jsonl "$1"/*.log "$1"/*.txt "$1"/*.csv "$1"/*.yml; do
    [ -f "$f" ] || continue
    tmp="$(mktemp "$STATE/scrub-XXXXXX")"
    "$PY" -I -m smallpc.smoke scrub "$f" "$tmp"
    mv "$tmp" "$f"
  done
}

smoke_probe() {
  local kind="$1" d="$OUT/probe-$1" scratch
  mkdir -p "$d"
  smoke_log "permission probe: $kind (scripted fake model, no GPU)"
  "$PY" -I -m smallpc.smoke probe-script "$kind" --out "$d/script.json"
  start_fake_model "$d/script.json"
  local fake_pid=$FAKE_PID fake_port=$FAKE_PORT
  start_proxy "$d/net.jsonl"
  local proxy_pid=$PROXY_PID proxy_port=$PROXY_PORT
  scratch="$(make_scratch)"
  CLEAN_SCRATCH+=("$scratch")
  harness_probe_run "$kind" "$d" "$scratch" "$fake_port" "$proxy_port" || true
  kill "$fake_pid" "$proxy_pid" 2>/dev/null || true
  wait "$fake_pid" "$proxy_pid" 2>/dev/null || true
  local rc=0
  "$PY" -I -m smallpc.smoke probe-check "$kind" --events "$d/events.jsonl" --log "$d/debug.log" \
    >"$d/checks.json" || rc=$?
  [ ! -f "$d/script.json.requests.jsonl" ] || mv "$d/script.json.requests.jsonl" "$d/model-requests.jsonl"
  remove_scratch "$scratch"
  if [ "$rc" -ne 0 ]; then
    echo "probe $kind FAILED; see $d/checks.json" >&2
    "$PY" -I -c 'import json,sys; [print(c) for c in json.load(open(sys.argv[1]))["checks"] if not c["pass"]]' "$d/checks.json" >&2 || true
    return 1
  fi
  smoke_log "probe $kind: all checks passed"
}

# smoke_gpu SERVER_CONFIG TIMEOUT_S: start the server, run up to two attempts, stop the server.
smoke_gpu() {
  local server_cfg="$1" ts host port run_id run_dir
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  run_id="smoke-$HARNESS-$ts"
  read -r host port < <("$PY" -I -c 'from smallpc.config import load_machine; m = load_machine(); print(m.server.host, m.server.port)')
  # preconditions (step plan 5.3 step 1); the 1-minute load average may still be high after the probes
  local waited=0
  until "$PY" -I -m smallpc.envsnap --preconditions >"$OUT/preconditions.json"; do
    [ "$waited" -lt 300 ] || { cat "$OUT/preconditions.json" >&2; die "preconditions failed"; }
    sleep 20
    waited=$((waited + 20))
  done
  smoke_log "preconditions ok (waited ${waited}s)"
  smoke_log "starting the server: $server_cfg"
  "$SMALLPC_REPO/scripts/launch-server.sh" --run-id "$run_id" "$server_cfg" | tee "$OUT/launch.txt"
  run_dir="$SMALLPC_REPO/data/logs/$run_id"
  SERVER_RUN_DIR="$run_dir"
  curl -s "http://$host:$port/props" | "$PY" -I -c '
import json, sys
p = json.load(sys.stdin)
keep = ("build_info", "total_slots", "model_path", "modalities")
out = {k: p.get(k) for k in keep}
out["default_generation_settings.n_ctx"] = p.get("default_generation_settings", {}).get("n_ctx")
out["n_ctx_top_level"] = p.get("n_ctx")
print(json.dumps(out, indent=2))' >"$OUT/props.json"
  cat "$OUT/props.json"
  "$PY" -I -m smallpc.envsnap --out "$OUT/snapshot.json"
  "$PY" -I -m smallpc.telemetry run --out "$OUT/telemetry.csv" --pidfile "$run_dir/server.pid" &
  TELEMETRY_PID=$!
  "$PY" -I -m smallpc.harness "render-$HARNESS" --out "$OUT/${HARNESS_CONFIG_NAME}" 2>"$OUT/render.txt"
  cat "$OUT/render.txt"

  local attempt scratch d mark end_mark rc t0 t1 passed=0 model_failed=0
  for attempt in 1 2; do
    d="$OUT/attempt-$attempt"
    mkdir -p "$d"
    scratch="$(make_scratch)"
    CLEAN_SCRATCH+=("$scratch")
    start_proxy "$d/net.jsonl"
    local proxy_pid=$PROXY_PID proxy_port=$PROXY_PORT
    mark="$(stat -c %s "$run_dir/server.log")"
    t0="$(date +%s)"
    smoke_log "attempt $attempt: $HARNESS in $scratch (hard timeout ${SMOKE_TIMEOUT}s)"
    rc=0
    harness_attempt_run "$d" "$scratch" "$port" "$proxy_port" "$(<"$TOY/PROMPT.txt")" || rc=$?
    t1="$(date +%s)"
    end_mark="$(stat -c %s "$run_dir/server.log")"
    kill "$proxy_pid" 2>/dev/null || true
    wait "$proxy_pid" 2>/dev/null || true
    tail -c +$((mark + 1)) "$run_dir/server.log" | head -c $((end_mark - mark)) >"$d/server-slice.log"
    printf '{"harness_exit_code": %s, "seconds": %s, "hard_timeout_s": %s}\n' "$rc" "$((t1 - t0))" "$SMOKE_TIMEOUT" >"$d/timing.json"
    "$PY" -I -m smallpc.smoke verify --scratch "$scratch" --original "$TOY" --python "$PY" >"$d/verify.json" || true
    local steps_arg=()
    if [ "$HARNESS" = dsh ]; then
      steps_arg=(--main-steps "$("$PY" -I -m smallpc.smoke summarize dsh --events "$d/events.jsonl" | "$PY" -I -c 'import json,sys; print(json.load(sys.stdin)["steps"])')")
    fi
    "$PY" -I -m smallpc.requests --server-log "$d/server-slice.log" --harness "$HARNESS" \
      --harness-log "$d/debug.log" --run-id "$run_id-attempt-$attempt" --out "$d/request-pattern.json" "${steps_arg[@]}"
    "$PY" -I -m smallpc.smoke finalize "$HARNESS" --verify "$d/verify.json" --events "$d/events.jsonl" \
      --log "$d/debug.log" --pattern "$d/request-pattern.json" --net "$d/net.jsonl" >"$d/verdict.json" && passed=1 || true
    grep -E "n_slots|kv_unified|new prompt|print_timing|stop processing" "$d/server-slice.log" >"$d/server-log-excerpt.txt" || true
    git -C "$scratch" diff --stat -- . >"$d/scratch-diff-stat.txt" 2>/dev/null || true
    git -C "$scratch" diff -- movavg.py >"$d/scratch-movavg.diff" 2>/dev/null || true
    remove_scratch "$scratch"
    if [ "$passed" = 1 ]; then
      smoke_log "attempt $attempt: PASS"
      break
    fi
    if "$PY" -I -c 'import json,sys; sys.exit(0 if not json.load(open(sys.argv[1]))["pytest_green"] else 1)' "$d/verify.json"; then
      model_failed=1
      smoke_log "attempt $attempt: the model did not fix the bug"
    else
      smoke_log "attempt $attempt: not a model failure (see $d/verdict.json); no retry"
      break
    fi
  done
  grep -E "n_slots|kv_unified" "$run_dir/server.log" >"$OUT/server-slots.txt" || true
  kill -INT "$TELEMETRY_PID" 2>/dev/null || true
  wait "$TELEMETRY_PID" 2>/dev/null || true
  TELEMETRY_PID=""
  "$SMALLPC_REPO/scripts/stop-server.sh" --timeout 90 "$run_dir" | tee "$OUT/stop.txt"
  cp "$run_dir/stop-status.json" "$OUT/stop-status.json" 2>/dev/null || true
  SERVER_RUN_DIR=""
  SMOKE_PASSED=$passed
  SMOKE_MODEL_FAILED=$model_failed
}
