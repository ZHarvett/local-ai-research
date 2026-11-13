# T-017 design — unattended loop (`scripts/wf-loop.sh`)

<!-- sources: docs/recon/loop-states.md, scripts/_wf.py, .claude/commands/continue.md, .claude/commands/review.md, .claude/commands/address-review.md, .workflow/config.toml -->

Design for the card's S3, grounded in `docs/recon/loop-states.md` (the S1/S2 recon,
cited below as `states §N`). This is the document escalated for **loop design
approval**; S4–S6 build it only after the DECISION.

## 0. Purpose and scope

Run the planning-chat plan unattended for a bounded time: repeatedly launch a fresh
headless `claude -p "/continue"` session, and after each session read the authoritative
state + the session exit code and continue **only** if the last task finished cleanly
and nothing needs a human. Stop and print the reason on the first state that needs a
human (or any of the card's other stop conditions). Version 1 is **serial** — one
session at a time, lane 1 preferred — and never passes a gate, never works a blocked
task, never starts a task after the deadline.

Out of scope for v1 (explicitly): parallel lanes; any mutation of kit state by the loop
itself (the loop only **reads** state and launches sessions; all writes happen inside
the claude sessions through `wf.sh`); running against this repo's real state during
T-017 (S5 forbids it — fixtures only).

## 1. Usage and interface

```
scripts/wf-loop.sh <hours>          # run for up to <hours> hours
scripts/wf-loop.sh --dry-run        # print the next action from state; start nothing
scripts/wf-loop.sh --help           # usage; exit 0
```

- `<hours>`: positive number (integer or decimal). Deadline = start + hours×3600 s.
  No **new** session starts at/after the deadline; a session already running is bounded
  by the per-session timeout (§4).
- `--dry-run`: read state, print the decision the loop would make next (action, task,
  lane, reason), exit 0. Takes no lock, starts no session, writes no log. Reads the
  state file named by `WF_LOOP_STATE_FILE` (and lane mirrors from `WF_LOOP_LANES_DIR`),
  so it runs against fixtures (S5).

### Environment knobs (all optional; defaults in parentheses)

| var | meaning | default |
|---|---|---|
| `WF_LOOP_CLAUDE_ARGS` | extra args passed to `claude -p`, word-split. The script **never** adds a permission-skipping flag itself (card; acceptance greps for the literal). | empty |
| `WF_LOOP_CLAUDE_BIN` | claude executable (tests point this at a fake) | `claude` |
| `WF_LOOP_REPO` | repo sessions run in (cwd) | main checkout (§2) |
| `WF_LOOP_STATE_FILE` | authoritative state file | `<main>/.workflow/state.json` |
| `WF_LOOP_LANES_DIR` | lane-mirror dir | `<git-common-dir>/workflow/lanes` |
| `WF_LOOP_LOCK` | the loop's own lock file | `/dev/shm/local-ai-research-wf-loop.lock` |
| `WF_LOOP_LOG` | log file | `/tmp/wf-loop-<UTCstamp>.log` |
| `WF_LOOP_SESSION_TIMEOUT_MIN` | per-session timeout, minutes | `90` (within the card's 60–120) |

The env knobs exist so S4's tests can drive the loop with a **fake claude** and
**fixture state files in a temp dir** without touching this repo. They are not a
public API; the documented usage is `wf-loop.sh <hours>`.

## 2. Reading the authoritative state (states §3.0, §2.2)

Two recon facts drive this:
1. The authoritative state is the **main checkout's** `.workflow/state.json`, overlaid
   by the lane mirrors in `<git-common-dir>/workflow/lanes/N.json` (the *effective
   view*, `effective_tasks` `_wf.py:398-408`). A worktree's own state copy is stale.
2. `wf.sh ready` and `wf.sh accept` exit **0** even when nothing is ready / an item
   failed (states §2.2). So the loop reads **state**, not exit codes, for those.

**Mechanism:** an embedded `python3` helper (python3 is guaranteed by the kit,
`wf.sh:8`; no `jq` dependency) reads `WF_LOOP_STATE_FILE` + every `*.json` in
`WF_LOOP_LANES_DIR`, merges them exactly as `effective_tasks` does (mirrors win), and
emits one JSON **decision summary** to stdout:

```json
{
  "tasks": {"T-xxx": {"status","lane","review","review_cycles","steps_done",
                       "blocked_reason","gate_message"}},
  "open_escalations": ["E-NNN"],
  "gates": ["T-xxx"],                 // status == awaiting-gate
  "blocked": ["T-xxx"],               // status == blocked-decision
  "ready": ["T-xxx"],                 // lane-ordered, then id
  "active": ["T-xxx"],                // claimed/in-progress/awaiting-gate
  "review_due": [{"task","kind":"post|pre|address","cycles"}],
  "accept_failures": {"T-xxx": N}     // latest .workflow/acceptance record failures
}
```

The helper does **no** writes and needs no git when the paths are overridden (fixtures).
Bash consumes the JSON via a small `python3 -c` extractor (keeps the script
python3-only). The merge mirrors `_wf.py:398-408`; `review_cycles` comes from the main
state's `review_cycles` map (`_wf.py:1876-1877`); `accept_failures` reads the last run
in `.workflow/acceptance/T-xxx.json` (`_wf.py:1813-1824`) under the task's work dir.

## 3. The decision algorithm (one iteration)

Bash first applies the **orchestration stops** it owns (§5: deadline, lock, exit code,
usage-limit, dirty tree, no-progress). Then it asks the helper for the summary and
picks the next action in this priority order:

1. **Continue an in-flight review cycle.** A task `changes-requested` →
   `/address-review T-xxx`; a task `in-review` → `/review T-xxx`. (These finish what a
   prior session started; bounded by `max_review_cycles`, §6.)
2. **Post-review a just-finished task.** A task `done` with `review != none` and
   `review_cycles < max` → `/review T-xxx`. (Card: "after a task whose card asks for
   review it runs /review".) Lowest task id wins if several are due.
3. **Run the next task.** A `ready` task exists **and** there is no open gate,
   escalation or blocked-decision → `/continue` (answer "yes, lane 1", §4). This is the
   only action that starts new task work.
4. **Run a review that is already due while task work is gated.** If step 3 is blocked
   (everything ready waits for a human, or nothing is ready) but a review is due — a
   post-review of a `done` task, or a **pre-review** of a `ready` `pre+post` task that
   is waiting at a gate — run `/review T-xxx`. **Never** for a task blocked
   mid-escalation (`blocked-decision`), and never past `max_review_cycles` (card S3).
5. **Otherwise STOP.** Print the reason: `idle` (no ready, no due review), or the
   blocking state (`gate T-xxx`, `escalation E-NNN`, `blocked-decision T-xxx`).

A blocking state (gate / open escalation / blocked-decision) stops **new task work**
(step 3) but does not by itself stop a *due, unblocked review* (step 4) — this is the
card's "when nothing can proceed … it may run a review that is already due". The loop
never reviews a `blocked-decision` task.

## 4. Launching a session; the lane answer (states §4.3, §7)

Each action runs in a **fresh** headless session, cwd = `WF_LOOP_REPO` (main checkout):

```
timeout <session-timeout> "$WF_LOOP_CLAUDE_BIN" -p "<prompt>" $WF_LOOP_CLAUDE_ARGS \
    < <stdin-answer>  >>"$WF_LOOP_LOG" 2>&1
```

- `<prompt>` is `/continue` for task work, `/review T-xxx` or `/address-review T-xxx`
  for reviews. Extra args come **only** from `WF_LOOP_CLAUDE_ARGS`; the script adds no
  permission-skipping flag (card; the acceptance grep forbids the literal string in the
  file, so even comments avoid it).
- **stdin:** S2 showed headless claude waits ~3 s for stdin (states §7). For
  `/continue` the loop pipes the lane answer `yes` (so "Start lane 1?" is pre-answered);
  for reviews it uses `< /dev/null`. This avoids the 3 s wait and supplies the answer.
- **Lane answer mechanism — the central uncertainty (escalated).** `/continue`
  (continue.md:19-23) stops and asks when several lanes are ready; headless there is no
  human. The design pipes `yes` on stdin so the model proceeds with lane 1. **This is
  unverified**: S2 forbids running `/continue` headlessly in this task, and the fake
  claude in S4 tests cannot validate real claude's behaviour. The escalation asks the
  planning chat to approve this mechanism (option A) or choose an alternative (B: use
  `/lane 1` when several lanes are ready; C: append a no-ask instruction to the prompt).
  See §8.
- **Lanes v1:** always prefer lane 1 (the `yes` answer). When only one lane is ready,
  `/continue` proceeds without asking (continue.md:17-18). No parallel sessions: the
  loop waits for each session to exit before the next. Lane 2/3 tasks therefore run
  only when they are the sole ready lane — a deliberate v1 simplification (escalated).
- **Per-session timeout:** `timeout` kills a session that exceeds
  `WF_LOOP_SESSION_TIMEOUT_MIN` (default 90). A timeout is a stop condition (the session
  did not finish cleanly).
- **Logging:** all session stdout+stderr append to `WF_LOOP_LOG`
  (`/tmp/wf-loop-<stamp>.log`), **never** into the repo (card). The loop's own progress
  lines (iteration, action, stop reason) go to the same log and to stdout.

## 5. Stop conditions and where each is detected

| # | condition | detected by | signature |
|---|---|---|---|
| 1 | deadline | bash | `now >= deadline` before starting a new session; running session bounded by `timeout` |
| 2 | open gate | helper | a task `status == awaiting-gate` (states §3.1) |
| 3 | open escalation | helper | `escalations[*].status == "open"` (states §3.2) |
| 4 | blocked-decision | helper | a task `status == blocked-decision` (states §3.4) |
| 5 | failed acceptance | helper + bash | latest accept record `failures > 0` for the attempted task, and it did not reach `done` (states §2.2, §6.2) |
| 6 | same task twice, no progress | bash | attempted task id repeats AND fingerprint (status + sorted steps_done + git HEAD) unchanged across two iterations |
| 7 | non-zero exit / usage-limit | bash | session exit `!= 0`, or captured output matches a usage-limit pattern (`usage limit`, `rate limit`, `429`, `overloaded`, `quota`) |
| 8 | unexpected dirty tree | bash | after a session that reported a clean finish, `git -C "$repo" status --porcelain` is non-empty |
| 9 | second loop running | bash | `flock -n` on `WF_LOOP_LOCK` fails at startup |
| 10 | per-session timeout | bash | `timeout` returns 124 |

On any stop the loop prints `wf-loop: STOP — <reason>` (to stdout and the log), releases
its lock, and exits non-zero for human-needed stops (0 for a clean `idle`/deadline exit).
The lock is held for the whole run via `flock` on a kept-open fd; a crashed loop's lock
is reclaimable because `flock` is released by the OS when the holder dies (no stale-pid
problem, unlike the kit's pid-based lane locks).

**"Finished cleanly" (continue) requires all of:** session exit 0; no usage-limit text;
the attempted task advanced to `done`/`in-review`/`accepted` (or a review advanced); no
new gate/escalation/blocked-decision; tree clean; progress fingerprint advanced. Only
then does the loop iterate (states §6.1).

## 6. Reviews and the two-cycle bound (states §3.3)

`max_review_cycles = 2` (`config.toml:9`). The loop reads `review_cycles[T-xxx]` from
state and never opens a cycle past the max — `review-open` itself refuses past it
(`_wf.py:1896-1900`), so a session that tries will exit non-zero and the loop stops
(§5.7). Flow per task: `done` → `/review` (cycle 1) → if `changes-requested`,
`/address-review` → if it re-opens review, `/review` (cycle 2) → `accepted` or stop.
A `blocked-decision` review verdict stops the loop (human). The loop never reviews a
task that is `blocked-decision` mid-escalation (card). Pre-review (`pre+post` cards)
runs before the task's heavy work; the loop offers it as a due review when the task is
ready but gated (§3 step 4).

## 7. The keep-continuing command (S4)

`.claude/commands/keep-continuing.md` — a thin command: take the hours argument
(`$ARGUMENTS`), start `scripts/wf-loop.sh <hours>` **detached** (setsid + nohup, stdin
`/dev/null`, the loop manages its own `/tmp` log), and print how to follow the log
(`tail -f /tmp/wf-loop-<stamp>.log`) and how to stop it. It does not use
`run-detached.sh` because that writes a job log **into the repo** (`data/logs/jobs/`,
`run-detached.sh:47-49`), which would violate the card's "logs … never into the repo";
the loop's log stays in `/tmp`. (The loop runs for hours, so detaching satisfies the
umbrella's ">8 minutes runs detached" rule.)

## 8. Open questions for the planning chat (escalated)

1. **Lane-answer mechanism (§4).** Approve A (pipe `yes` to `/continue` stdin), or
   choose B (`/lane 1` when several lanes ready) or C (append a no-ask instruction to
   the prompt)? A is most faithful to the card's `claude -p "/continue"` but is
   unverified headlessly (S2 forbids testing `/continue` here). Recommendation: A,
   with the mechanism verified live in a later task that may run `/continue` headlessly
   (or a small approved follow-up), since S4's fake-claude tests cannot validate real
   claude. Confidence: medium.
2. **Serial lane-1 preference (§4).** v1 runs lane 1 first and lane 2/3 only when sole
   ready lane — so T-005/T-011/T-017 may wait while lane 1 has work. Acceptable for v1?
   (The card prescribes this; confirming.) Confidence: high.
3. **Review-while-gated (§3 step 4).** Confirm the loop may run a due, unblocked review
   even when an open gate stops new task work, and that "any open gate" as a stop
   condition applies to *task work*, not to a due pre-review. Confidence: medium.

Everything else (internal structure, log format, the 90-minute default timeout, the
env knobs, the python3 helper) is within the card's "may" decision rights.

## 9. Test plan (S4) and dry-run (S5)

`tests/test_wf_loop.py` — pytest, one test per stop condition (§5 #1–#10) plus the
continue path and the review flow. Each test builds a temp dir with: a minimal git repo
(`git init`, for the dirty-tree check), fixture `state.json` (+ optional lane mirrors),
a **fake claude** script on `WF_LOOP_CLAUDE_BIN` that mutates the fixture state to
simulate a session outcome and exits with a chosen code, and env overrides
(`WF_LOOP_STATE_FILE`, `WF_LOOP_LANES_DIR`, `WF_LOOP_REPO`, `WF_LOOP_LOCK`,
`WF_LOOP_LOG`, `WF_LOOP_CLAUDE_BIN`, `WF_LOOP_SESSION_TIMEOUT_MIN`). The test runs
`wf-loop.sh` (small `<hours>`) and asserts the stop reason / exit code / that no real
session ran. The fake claude is a bash/python stub — **never** the real CLI. S5 adds
`--dry-run` and runs it against the same fixtures (asserting the printed next action),
never against this repo's real state.

## 10. Acceptance alignment

- `shellcheck scripts/wf-loop.sh` → clean (S6).
- `uv run pytest -q tests/test_wf_loop.py` → pass (S4/S6).
- `bash scripts/wf-loop.sh --help` → exit 0.
- `uv run ruff check / format --check tests/test_wf_loop.py` → clean.
- no existing file under `src/ configs/ scripts/ pyproject.toml uv.lock` modified
  (`--diff-filter=MD` from start HEAD): the loop, command and test are **new** files
  (Added, excluded by `MD`); no existing file is touched.
- `! grep -q 'dangerously-skip-permissions' scripts/wf-loop.sh`: the literal never
  appears (the script adds no permission-skipping flag; comments avoid the string).
- `.claude/commands/keep-continuing.md` exists.
- manual: the loop never passes a gate, never works a blocked task, never starts a task
  after the deadline, runs lanes in order, runs only due reviews, stops on the first
  human-needed state — each covered by a test (§9).
