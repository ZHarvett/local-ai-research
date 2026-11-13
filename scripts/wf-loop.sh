#!/usr/bin/env bash
# wf-loop.sh — unattended workflow-kit loop (task T-017).
#
# Design: docs/recon/loop-design.md, approved as decision E-004 (option B) with
# the E-005 guard exception. Evidence base: docs/recon/loop-states.md.
#
# Runs fresh headless claude sessions serially; after each session it reads the
# kit state + the session exit code and continues only if nothing needs a human.
# The loop never mutates task state itself: all task writes happen inside the
# claude sessions through wf.sh. (It does run the kit guard as-is before each
# session, per E-004; the guard's own stale-lock cleanup is kit behaviour.)
# Session logs go to /tmp, never into the repo.
#
# E-004 changes applied here:
#   (1) Lane answer (option B): several ready lanes -> "/lane <lowest-numbered>";
#       exactly one ready lane -> "/continue". No stdin answer is piped; every
#       session gets stdin /dev/null (states §7: avoids the 3 s stdin wait).
#   (3) Stop on any guard failure, except the exact E-005 placeholder line
#       ("task T-NNN is in the main state as ready AND in lane N") for a task
#       whose effective status is in-progress / awaiting-gate / blocked-decision.
#   (4) The startup message asks for a supervised first run (~1 hour, awake).
#   (5) The final message names the stop reason and the task id.
#
# Interpretation of "unexpected dirty tree" (card S3): PROGRESS.md and
# .workflow/ are re-rendered by the kit on every mutation (save_owner), so after
# a lane session they are expected churn in the main checkout; they are excluded
# from the dirty-tree check. Any other uncommitted change stops the loop.
#
# "Finished cleanly" / progress (design §5): a session's attempted task is
# fingerprinted (status | steps_done | review cycles | dispositions | git HEAD)
# before and after. The loop iterates only when the task finished
# (done/in-review/accepted) or a review advanced. A session that changed nothing
# gets one re-attempt; the same task attempted twice with an unchanged
# fingerprint stops the loop (card stop condition 6). Partial progress without a
# clean finish stops the loop: /continue only picks ready tasks, so an orphaned
# in-progress task needs a human to run `wf.sh resume`.

set -u -o pipefail

usage() {
  cat <<'EOF'
wf-loop.sh — run the workflow-kit plan unattended, serially, for a bounded time.

Usage:
  scripts/wf-loop.sh <hours>     run for up to <hours> hours (positive number)
  scripts/wf-loop.sh --dry-run   print the next action from state; start nothing
  scripts/wf-loop.sh --help      this help

Each task runs in a fresh headless claude session. The loop stops and prints the
reason (and the task id) on: the deadline; any open gate, escalation or
blocked-decision; a failed acceptance; the same task attempted twice with no
progress; a non-zero session exit or usage-limit message; an unexpected dirty
tree; a second loop running; a per-session timeout; a guard failure (except the
E-005 placeholder exception).

Environment (optional; for tests and advanced use):
  WF_LOOP_CLAUDE_ARGS           extra args for claude -p, word-split (the script
                                never adds a permission-skipping flag itself)
  WF_LOOP_CLAUDE_BIN            claude executable (default: claude)
  WF_LOOP_REPO                  repo sessions run in (default: main checkout)
  WF_LOOP_STATE_FILE            state file (default: <repo>/.workflow/state.json)
  WF_LOOP_LANES_DIR             lane-mirror dir (default: <git-common>/workflow/lanes)
  WF_LOOP_LOCK                  loop lock file (default: /dev/shm/local-ai-research-wf-loop.lock)
  WF_LOOP_LOG                   log file (default: /tmp/wf-loop-<UTCstamp>.log)
  WF_LOOP_SESSION_TIMEOUT_MIN   per-session timeout in minutes (default: 90)

Make the first real run a supervised one of about 1 hour while awake (E-004).
EOF
}

# ------------------------------------------------------------------ globals

D_ACTION="" D_TASK="" D_LANE="" D_PROMPT="" D_REASON="" D_EXIT=""
GUARD_OK=1 GUARD_REASON="" BLOCKERS=""
declare -A TASK_STATUS=() TASK_FP=() TASK_AF=()
LOG_ACTIVE=0
SESSION_RC=0
GUARD_RC=0
DIRTY_DETAIL=""
LAST_TASK=none
LAST_ATTEMPT_TASK=""
LAST_ATTEMPT_FP=""
LAUNCHED_ACTION=""

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"
}

# finish <reason> <task|none> <exit-code> — the final message (E-004 change 5).
finish() {
  local reason=$1 task=${2:-none} code=$3 line
  [[ -n $task ]] || task=none
  line="wf-loop: STOP — $reason (task: $task)"
  printf '%s\n' "$line"
  if [[ $LOG_ACTIVE == 1 ]]; then
    printf '%s\n' "$line" >>"$LOG"
  fi
  exit "$code"
}

resolve_defaults() {
  local script_dir common
  if [[ -z ${WF_LOOP_REPO:-} ]]; then
    script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
    if common=$(git -C "$script_dir/.." rev-parse --git-common-dir 2>/dev/null); then
      [[ $common == /* ]] || common="$script_dir/../$common"
      WF_LOOP_REPO=$(cd -- "$common/.." && pwd)
    else
      WF_LOOP_REPO=$(cd -- "$script_dir/.." && pwd)
    fi
  fi
  REPO=$WF_LOOP_REPO
  STATE_FILE=${WF_LOOP_STATE_FILE:-$REPO/.workflow/state.json}
  if [[ -n ${WF_LOOP_LANES_DIR:-} ]]; then
    LANES_DIR=$WF_LOOP_LANES_DIR
  else
    common=$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null) || common="$REPO/.git"
    [[ $common == /* ]] || common="$REPO/$common"
    LANES_DIR=$common/workflow/lanes
  fi
  CLAUDE_BIN=${WF_LOOP_CLAUDE_BIN:-claude}
  LOCK=${WF_LOOP_LOCK:-/dev/shm/local-ai-research-wf-loop.lock}
  LOG=${WF_LOOP_LOG:-/tmp/wf-loop-$(date -u +%Y%m%dT%H%M%SZ).log}
  TIMEOUT_MIN=${WF_LOOP_SESSION_TIMEOUT_MIN:-90}
  if ! [[ $TIMEOUT_MIN =~ ^[0-9]+([.][0-9]+)?$ ]] ||
    ! python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) > 0 else 1)' "$TIMEOUT_MIN" 2>/dev/null; then
    echo "wf-loop: WF_LOOP_SESSION_TIMEOUT_MIN must be a positive number of minutes" >&2
    exit 2
  fi
}

git_head() {
  git -C "$REPO" rev-parse HEAD 2>/dev/null || printf '(no commits)'
}

# ------------------------------------------------------- the state helper
# Reads the main state + every lane mirror (mirrors win, exactly as
# effective_tasks in scripts/_wf.py), and emits one JSON decision summary.
# Read-only: no writes, no kit commands. Args:
#   state_file lanes_dir repo out_file guard_rc guard_output_file

run_helper() {
  python3 - "$STATE_FILE" "$LANES_DIR" "$REPO" "$WORK/decision.json" "$1" "$2" <<'PY'
import json
import os
import re
import sys
import tomllib
from pathlib import Path

state_file, lanes_dir, repo, out_file, guard_rc, guard_file = sys.argv[1:7]
repo = Path(repo)


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


state = load_json(state_file, {})
tasks = {tid: dict(t) for tid, t in state.get("tasks", {}).items()}
mirrors = []
lp = Path(lanes_dir)
if lp.is_dir():
    for p in sorted(lp.glob("*.json")):
        if p.stem.isdigit():
            mirrors.append(load_json(p, {}))
for mirror in mirrors:  # effective_tasks: lane mirrors overlay the main state
    for tid, t in mirror.get("tasks", {}).items():
        merged = dict(tasks.get(tid, {}))
        merged.update(t)
        tasks[tid] = merged

review_cycles = dict(state.get("review_cycles", {}))
dispositions = dict(state.get("review_dispositions", {}))
escalations = dict(state.get("escalations", {}))
for mirror in mirrors:
    escalations.update(mirror.get("escalations", {}))

max_cycles = 2
cfg = Path(os.environ.get("WF_CONFIG") or repo / ".workflow" / "config.toml")
if cfg.is_file():
    try:
        with open(cfg, "rb") as fh:
            max_cycles = tomllib.load(fh).get("workflow", {}).get("max_review_cycles", 2)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        pass


def cycles(tid):
    return int(review_cycles.get(tid, 0))


def accept_failures(tid, lane):
    bases = []
    if lane > 1:
        wt = repo / ".workflow" / "worktrees" / f"lane-{lane}"
        if wt.is_dir():
            bases.append(wt)
    bases.append(repo)
    for base in bases:
        runs = load_json(base / ".workflow" / "acceptance" / f"{tid}.json", [])
        if isinstance(runs, list) and runs:
            return int(runs[-1].get("failures", 0))
    return 0


def lane_of(tid):
    try:
        return int(tasks[tid].get("lane", 1) or 1)
    except (TypeError, ValueError):
        return 1


ready = sorted(
    (tid for tid, t in tasks.items() if t.get("status") == "ready"),
    key=lambda tid: (lane_of(tid), tid),
)
gates = sorted(tid for tid, t in tasks.items() if t.get("status") == "awaiting-gate")
blocked = sorted(tid for tid, t in tasks.items() if t.get("status") == "blocked-decision")
open_esc = sorted(eid for eid, e in escalations.items() if e.get("status") == "open")

# Due reviews (design §3, §6). Never a blocked-decision task; never past max cycles.
address = [t for t in sorted(tasks) if tasks[t].get("status") == "changes-requested" and cycles(t) < max_cycles]
inflight = [t for t in sorted(tasks) if tasks[t].get("status") == "in-review" and cycles(t) < max_cycles]
post = [t for t in sorted(tasks) if tasks[t].get("status") == "done" and tasks[t].get("review") in ("post", "pre+post") and cycles(t) < max_cycles]
pre = [t for t in sorted(tasks) if tasks[t].get("status") == "ready" and tasks[t].get("review") == "pre+post" and cycles(t) == 0]
exhausted = [t for t in sorted(tasks) if tasks[t].get("status") in ("in-review", "changes-requested") and cycles(t) >= max_cycles]


def act(action, task=None, lane=None, prompt=None, reason="", exit_code=0):
    return {
        "action": action,
        "task": task or "none",
        "lane": "" if lane is None else str(lane),
        "prompt": prompt or "",
        "reason": reason,
        "exit": exit_code,
    }


# Decision priority (design §3):
# 1 in-flight review cycle, 2 post-review of a done task, 3 new task work
# (only when nothing is gated/escalated/blocked), 4 a due pre-review while task
# work is blocked, 5 stop.
if address:
    decision = act("address", address[0], prompt=f"/address-review {address[0]}")
elif inflight:
    decision = act("review", inflight[0], prompt=f"/review {inflight[0]}")
elif post:
    decision = act("review", post[0], prompt=f"/review {post[0]}")
elif ready and not (gates or open_esc or blocked):
    lanes = sorted({lane_of(tid) for tid in ready})
    if len(lanes) > 1:  # E-004 option B: lowest-numbered ready lane, no question
        n = lanes[0]
        tid = next(t for t in ready if lane_of(t) == n)
        decision = act("lane", tid, lane=n, prompt=f"/lane {n}")
    else:
        decision = act("continue", ready[0], lane=lanes[0], prompt="/continue")
elif pre:
    decision = act("review", pre[0], prompt=f"/review {pre[0]}")
elif exhausted:
    decision = act("stop", exhausted[0], reason=f"review cycles exhausted for {exhausted[0]}", exit_code=1)
elif gates:
    tid = gates[0]
    msg = str(tasks[tid].get("gate_message", ""))[:120]
    decision = act("stop", tid, reason=f"open gate {tid}: {msg}", exit_code=1)
elif open_esc:
    eid = open_esc[0]
    decision = act("stop", escalations[eid].get("task"), reason=f"open escalation {eid}", exit_code=1)
elif blocked:
    tid = blocked[0]
    decision = act("stop", tid, reason=f"blocked-decision {tid}: {tasks[tid].get('blocked_reason', '')}", exit_code=1)
else:
    stranded = [t for t in sorted(tasks) if tasks[t].get("status") in ("claimed", "in-progress")]
    if stranded:
        tid = stranded[0]
        decision = act(
            "stop",
            tid,
            reason=f"no ready tasks; {tid} left {tasks[tid].get('status')} — resume manually",
            exit_code=1,
        )
    else:
        decision = act("stop", reason="idle — no ready tasks and no due reviews", exit_code=0)

# Guard verdict (E-004 change 3 + E-005 standing rule). The effective status
# below is exactly what `wf.sh status` prints (effective_tasks).
guard_ok, guard_reason = True, ""
if guard_rc != "0":
    try:
        guard_text = Path(guard_file).read_text(encoding="utf-8")
    except OSError:
        guard_text = ""
    lines = [ln for ln in guard_text.splitlines() if ln.startswith("GUARD:")]
    pat = re.compile(
        r"^GUARD: task (T-[0-9]+) is in the main state as ready AND in lane ([0-9]+); "
        r"run wf\.sh merge-lanes ([0-9]+)$"
    )
    if not lines:
        guard_ok = False
        guard_reason = "guard failed: " + (guard_text.strip().splitlines() or ["(no output)"])[0]
    else:
        named = []
        for ln in lines:
            m = pat.match(ln)
            if not m or m.group(2) != m.group(3):
                guard_ok = False
                guard_reason = ln
                break
            tid = m.group(1)
            st = tasks.get(tid, {}).get("status", "")
            if st not in ("in-progress", "awaiting-gate", "blocked-decision"):
                guard_ok = False
                guard_reason = f"E-005 placeholder for {tid} but its status is {st or 'unknown'}: {ln}"
                break
            named.append(f"{tid} ({st})")
        if guard_ok:
            guard_reason = "E-005 placeholder exception applied: " + ", ".join(named)

task_info = {}
for tid, t in tasks.items():
    fp = "|".join(
        [
            str(t.get("status", "")),
            ",".join(sorted(t.get("steps_done") or [])),
            str(cycles(tid)),
            str(len(dispositions.get(tid, []))),
        ]
    )
    task_info[tid] = {
        "status": str(t.get("status", "")),
        "fp": fp,
        "accept_failures": accept_failures(tid, lane_of(tid)),
    }

blocker_tokens = (
    [f"gate:{t}" for t in gates]
    + [f"escalation:{e}" for e in open_esc]
    + [f"blocked:{t}" for t in blocked]
)

Path(out_file).write_text(
    json.dumps(
        {
            "decision": decision,
            "guard": {"ok": guard_ok, "reason": guard_reason},
            "tasks": task_info,
            "blockers": " ".join(blocker_tokens),
        }
    ),
    encoding="utf-8",
)
PY
}

# Extract the helper JSON into shell variables (shlex-quoted, eval-safe).
extract_decision() {
  local lines
  lines=$(python3 - "$WORK/decision.json" <<'PY'
import json
import shlex
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    d = json.load(fh)
dec = d["decision"]
for k in ("action", "task", "lane", "prompt", "reason", "exit"):
    print(f"D_{k.upper()}={shlex.quote(str(dec[k]))}")
print("GUARD_OK=" + ("1" if d["guard"]["ok"] else "0"))
print("GUARD_REASON=" + shlex.quote(d["guard"]["reason"]))
print("BLOCKERS=" + shlex.quote(d["blockers"]))
for tid, info in d["tasks"].items():
    print(f"TASK_STATUS[{tid}]={shlex.quote(info['status'])}")
    print(f"TASK_FP[{tid}]={shlex.quote(info['fp'])}")
    print(f"TASK_AF[{tid}]={shlex.quote(str(info['accept_failures']))}")
PY
  ) || return 1
  eval "$lines"
}

task_fp() {
  printf '%s|%s' "${TASK_FP[$1]:-unknown}" "$(git_head)"
}

run_guard() {
  GUARD_RC=0
  if [[ -f "$REPO/scripts/wf-guard.sh" ]]; then
    (cd "$REPO" && bash scripts/wf-guard.sh) >"$WORK/guard.out" 2>&1
    GUARD_RC=$?
  else
    GUARD_RC=127
    printf 'wf-loop: guard script not found: %s/scripts/wf-guard.sh\n' "$REPO" >"$WORK/guard.out"
  fi
}

run_session() {
  local prompt=$1
  local -a extra=()
  read -r -a extra <<<"${WF_LOOP_CLAUDE_ARGS:-}"
  (cd "$REPO" && timeout "${TIMEOUT_MIN}m" "$CLAUDE_BIN" -p "$prompt" ${extra[@]+"${extra[@]}"}) \
    </dev/null >"$WORK/session.out" 2>&1
  SESSION_RC=$?
}

usage_limit() {
  grep -Eiq 'usage limit|rate limit|overloaded|quota|\b429\b' "$1"
}

# 0 = dirty (or git failed), 1 = clean. Kit-rendered churn is expected (header).
dirty_tree() {
  local raw filtered
  if ! raw=$(git -C "$REPO" status --porcelain 2>&1); then
    DIRTY_DETAIL="git status failed: $raw"
    return 0
  fi
  filtered=$(printf '%s\n' "$raw" | grep -vE '^.. (PROGRESS\.md|\.workflow/)' || true)
  if [[ -n $filtered ]]; then
    DIRTY_DETAIL=$filtered
    return 0
  fi
  return 1
}

# ------------------------------------------------------------------- dry-run
# Read-only preview (design §1, card S5): reads the state file + lane mirrors,
# prints the decision the loop would make next, exits 0. Takes no lock, starts
# no session, writes no log, and does not run the guard (the kit guard may clean
# stale lane locks, so even it is not purely read-only).

dry_run() {
  resolve_defaults
  WORK=$(mktemp -d /tmp/wf-loop-dry-XXXXXX)
  trap 'rm -rf "$WORK"' EXIT
  : >"$WORK/guard.out"
  if ! run_helper 0 "$WORK/guard.out"; then
    echo "wf-loop: dry-run: cannot read state: $STATE_FILE" >&2
    exit 1
  fi
  if ! extract_decision; then
    echo "wf-loop: dry-run: cannot parse decision summary" >&2
    exit 1
  fi
  if [[ $D_ACTION == stop ]]; then
    printf 'wf-loop: dry-run: would STOP — %s (task: %s)\n' "$D_REASON" "$D_TASK"
  else
    printf 'wf-loop: dry-run: next action: %s task=%s lane=%s prompt=%s\n' \
      "$D_ACTION" "$D_TASK" "${D_LANE:-1}" "$D_PROMPT"
  fi
  printf 'wf-loop: dry-run: state=%s lanes=%s (no session started, no lock taken, no log written)\n' \
    "$STATE_FILE" "$LANES_DIR"
  exit 0
}

# --------------------------------------------------------------------- main

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  usage
  exit 0
fi
if [[ ${1:-} == --dry-run ]]; then
  dry_run
fi
if [[ $# -lt 1 || -z ${1:-} ]]; then
  usage >&2
  exit 2
fi
HOURS=$1
DEADLINE=$(python3 -c 'import sys, time; h = float(sys.argv[1]); assert h > 0; print(int(time.time() + h * 3600))' "$HOURS" 2>/dev/null) || {
  echo "wf-loop: <hours> must be a positive number (got: $HOURS)" >&2
  exit 2
}

resolve_defaults

if ! exec 9>"$LOCK"; then
  echo "wf-loop: cannot open lock file: $LOCK" >&2
  exit 1
fi
if ! flock -n 9; then
  finish "second loop running (lock: $LOCK)" none 1
fi
LOG_ACTIVE=1
if ! touch "$LOG"; then
  echo "wf-loop: cannot write log file: $LOG" >&2
  exit 1
fi
WORK=$(mktemp -d /tmp/wf-loop-run-XXXXXX)
trap 'rm -rf "$WORK"' EXIT

log "wf-loop: start — hours=$HOURS deadline=$(date -u -d "@$DEADLINE" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || printf '%s' "$DEADLINE") session-timeout=${TIMEOUT_MIN}m repo=$REPO"
log "wf-loop: log: $LOG"
log "wf-loop: NOTE (E-004): make the first real run a supervised one of about 1 hour while awake."

ITERATION=0
while :; do
  if (( $(date +%s) >= DEADLINE )); then
    finish "deadline reached" "$LAST_TASK" 0
  fi
  ITERATION=$((ITERATION + 1))

  run_guard
  if ! run_helper "$GUARD_RC" "$WORK/guard.out"; then
    finish "cannot read state: $STATE_FILE" "$LAST_TASK" 1
  fi
  if ! extract_decision; then
    finish "cannot parse decision summary" "$LAST_TASK" 1
  fi
  if [[ $GUARD_OK != 1 ]]; then
    finish "guard failed: $GUARD_REASON" "$D_TASK" 1
  fi
  if [[ -n $GUARD_REASON && $GUARD_RC != 0 ]]; then
    log "iteration $ITERATION: guard: $GUARD_REASON"
  fi
  if [[ $D_ACTION == stop ]]; then
    finish "$D_REASON" "$D_TASK" "$D_EXIT"
  fi

  ATTEMPT_TASK=$D_TASK
  LAUNCHED_ACTION=$D_ACTION
  PRE_BLOCKERS=$BLOCKERS
  PRE_FP="$(task_fp "$ATTEMPT_TASK")"
  log "iteration $ITERATION: $D_ACTION task=$ATTEMPT_TASK lane=${D_LANE:-1} prompt=$D_PROMPT"
  run_session "$D_PROMPT"
  cat "$WORK/session.out" >>"$LOG"
  LAST_TASK=$ATTEMPT_TASK

  if (( SESSION_RC == 124 )); then
    finish "session timeout (${TIMEOUT_MIN}m)" "$ATTEMPT_TASK" 1
  fi
  if (( SESSION_RC != 0 )); then
    finish "session exit $SESSION_RC" "$ATTEMPT_TASK" 1
  fi
  if usage_limit "$WORK/session.out"; then
    finish "usage-limit message in session output" "$ATTEMPT_TASK" 1
  fi

  if ! run_helper 0 "$WORK/guard.out"; then
    finish "cannot read state after session" "$ATTEMPT_TASK" 1
  fi
  if ! extract_decision; then
    finish "cannot parse decision summary after session" "$ATTEMPT_TASK" 1
  fi

  # A blocker that appeared during the session needs a human (design §5).
  read -r -a blocker_tokens <<<"$BLOCKERS"
  for tok in ${blocker_tokens[@]+"${blocker_tokens[@]}"}; do
    case " $PRE_BLOCKERS " in
      *" $tok "*) ;;
      *) finish "new $tok after session" "$ATTEMPT_TASK" 1 ;;
    esac
  done

  if dirty_tree; then
    log "unexpected dirty tree in $REPO:"
    printf '%s\n' "$DIRTY_DETAIL" | tee -a "$LOG"
    finish "unexpected dirty tree in $REPO" "$ATTEMPT_TASK" 1
  fi

  af=${TASK_AF[$ATTEMPT_TASK]:-0}
  st=${TASK_STATUS[$ATTEMPT_TASK]:-}
  if (( af > 0 )) && [[ $st != "done" && $st != "in-review" && $st != "accepted" ]]; then
    finish "acceptance failed ($af failures)" "$ATTEMPT_TASK" 1
  fi

  # Clean finish (design §5): the task reached done/in-review/accepted, or a
  # review advanced. Otherwise: one re-attempt when nothing changed, stop on
  # the second unchanged attempt; partial progress without a finish also stops
  # (a human must resume an orphaned task; /continue only picks ready tasks).
  POST_FP="$(task_fp "$ATTEMPT_TASK")"
  finished=0
  case $LAUNCHED_ACTION in
    review | address)
      # A review finishes when a verdict landed or the review state advanced;
      # merely staying in-review with nothing changed is not a finish.
      case $st in
        accepted | changes-requested) finished=1 ;;
      esac
      if [[ $POST_FP != "$PRE_FP" ]]; then
        finished=1
      fi
      ;;
    *)
      case $st in
        done | in-review | accepted) finished=1 ;;
      esac
      ;;
  esac
  if (( finished )); then
    LAST_ATTEMPT_TASK=""
    LAST_ATTEMPT_FP=""
  else
    if [[ $ATTEMPT_TASK == "$LAST_ATTEMPT_TASK" && $POST_FP == "$LAST_ATTEMPT_FP" ]]; then
      finish "no progress: attempted twice, state unchanged" "$ATTEMPT_TASK" 1
    fi
    if [[ $POST_FP != "$PRE_FP" ]]; then
      finish "task not finished cleanly (status: ${st:-unknown}) — resume manually" "$ATTEMPT_TASK" 1
    fi
    LAST_ATTEMPT_TASK=$ATTEMPT_TASK
    LAST_ATTEMPT_FP=$POST_FP
  fi
done