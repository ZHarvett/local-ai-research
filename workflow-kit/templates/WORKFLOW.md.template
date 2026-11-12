# WORKFLOW — how a session executes a planning-chat plan

This is the full protocol for agent sessions in this repo. The one-page summary
lives in CLAUDE.md between the `workflow-kit` markers; commands live in
`.claude/commands/`.

## Roles and model note

One model is executor, subagent and reviewer alike (see `config.toml`:
`model_note`). Because the reviewer is not a stronger model, acceptance is
mechanical wherever possible: `wf.sh accept` runs the card's acceptance commands
and records evidence, and `/review` re-runs them instead of trusting the
executor's claims. `/review` prints the model it runs as, for transparency only.

## Files

| file | who writes it | notes |
|---|---|---|
| `PLAN.md` | planning chat only | hash-frozen; `wf-guard.sh` fails if it changes |
| `PLAN-ADDED.md` | sessions (append only) | new cards from escalations, via `wf.sh add-task` |
| `.workflow/state.json` | scripts only | checksummed; hand edits fail the guard |
| `.workflow/lanes/N.json` | scripts only | lane-local task statuses (lane branch) |
| `PROGRESS.md` | generated | `wf-progress.sh render`; do not edit by hand |
| `escalations/E-NNN.md` | `wf-escalate.sh` | self-contained briefs for the planning chat |
| `reviews/T-xxx/rN-REVIEW_REPORT.md` | reviewer | archived by `review-verdict` |
| `.workflow/acceptance/T-xxx.json` | `wf.sh accept` | evidence records |
| `.workflow/calibration.json` | `/calibrate-reviewer` | reviewer self-test history |

Shared runtime state (untracked, visible from every worktree) sits in
`<git-common-dir>/workflow/`: `locks/lane-N.lock`, `claims.json`, `lanes/N.json`
(mirrors). Lane sessions read dependency status from the main checkout's
`state.json`, never from a stale branch copy.

## Session start

1. `bash scripts/wf-guard.sh` — plan hash, state checksums, PROGRESS.md render,
   stale locks. Any failure: stop and report, do not repair by hand.
2. `bash scripts/wf.sh status` — the current picture.
3. If blocked-decision items exist, show them first (`escalations/`, decisions
   are recorded by `wf-decision.sh` after Zack pastes the reply).
4. `bash scripts/wf.sh ready` — the READY list grouped by lane.

## Picking a task (`/continue`)

- Exactly one ready task → claim it and run it.
- Several **lanes** ready → list them with each card's one-line lane reason,
  ask "Start lane 1 (<task>)?", wait for yes, run lane 1, and remind Zack to
  open more sessions with `/lane 2` and `/lane 3` (max 3 parallel sessions).
- The parallel-lane value test (a lane hint is only honoured when it passes):
  different files, no machine contention, and more than about
  `parallel_value_threshold_min` minutes saved. The card must say so.

Claiming (`wf.sh claim T-xxx --lane N`) refuses on `files_write` overlap with any
in-progress task, on resource conflicts (gpu / exclusive-machine tasks only run
beside `light` tasks), and when the machine lock is taken. Lanes 2 and 3 get a
worktree and branch (`.workflow/worktrees/lane-N`); their file work and commits
happen there.

## Running a task

1. `bash scripts/wf-card.sh T-xxx` — the shared rules and that one card.
2. `bash scripts/wf.sh precheck T-xxx` — any precondition mismatch means STOP and
   report. Never work around.
3. `bash scripts/wf.sh claim T-xxx` then `wf.sh start T-xxx`.
4. Execute steps S1..Sn in order; after each, `wf.sh step-done T-xxx Sn`
   (checkpoints, so an interrupted session can resume).
5. HUMAN-GATE: `wf.sh gate-wait T-xxx --message "…"` stops the task, prints
   exactly what Zack must do, and waits; Zack's "go" is `wf.sh gate-release`.
6. `bash scripts/wf.sh accept T-xxx` — runs the acceptance commands, evaluates
   `exit_code` / `stdout_regex` / `file_exists` / `json_eq` expectations, defers
   `heavy` items, records `manual` items as judgement, and hashes the card's
   evidence files.
7. `bash scripts/wf.sh done T-xxx` — refuses unless the latest accept record has
   no failures and every evidence file exists.
8. Commit the task's work (small commits). End with one line:
   `TASK T-xxx DONE | review: required, run /review in a fresh session | next ready: …`.

Steps marked **not redo-safe** may not be repeated on resume without
confirmation (`wf.sh resume T-xxx --confirm`).

## Interruption, orphans and resume

If a session finds a task in-progress whose claim pid is dead, it offers to
resume: `wf.sh resume T-xxx` continues from the first incomplete step; redo-safe
steps repeat freely, others need `--confirm`. Context discipline: when roughly
70% of the context is used, finish the current step, `wf.sh step-done`, stop,
and tell Zack: "Start a fresh session and run /continue".

## Review (`/review [T-xxx]`, read-only)

- Prints the model it runs as, then sees the card, the acceptance evidence and
  the diff — never the executor's reasoning.
- Re-runs `wf.sh accept` itself (cheap items); defers heavy items while a gpu or
  exclusive-machine task is in progress; DEFERS heavy ones it cannot run.
- Writes `REVIEW_REPORT.md` (latest) and archives it via
  `wf.sh review-verdict T-xxx <verdict> --report-file REVIEW_REPORT.md`.
- Verdicts per acceptance item: PASS, FAIL, DEFERRED, ESCALATE. Task verdicts:
  accepted, changes-requested, blocked-decision.
- Findings carry severity (BLOCKER, MAJOR, MINOR, NOTE), an evidence pointer and
  a required action chosen as cheaply as possible: FIX-DOC, FIX-CODE,
  RE-ANALYSE (the default whenever re-analysis could fix it), RE-MEASURE (raw
  data invalid; names the card steps to redo and a time estimate; the reviewer
  NEVER orders it — it becomes an escalation), or DECIDE (options for the human).
- Every report ends with a "What I did not verify" section.
- At most `max_review_cycles` review cycles per task, then it escalates.

## Addressing a review (`/address-review T-xxx`)

For each finding, record one disposition (`wf.sh review-disposition`):
ACCEPT (do FIX-DOC / FIX-CODE / RE-ANALYSE inline), REJECT with a written reason,
or ESCALATE. A BLOCKER may not be rejected. RE-MEASURE and DECIDE findings are
never done inline: escalate; if Zack approves, a new gated task is created via
`PLAN-ADDED.md` + `wf.sh add-task`, and the old run is `wf.sh supersede`d —
never deleted. If any BLOCKER or MAJOR was fixed, re-open review.

## Escalation (`wf-escalate.sh`, `/escalate`)

The planning chat cannot see the repo, so the brief is one self-contained page
(see `escalations/E-NNN.md`): what happened (facts, paths, numbers), why it
cannot proceed, options A/B/C with consequences and cost, the session's
recommendation with confidence, what is blocked and what can proceed in
parallel, and the exact question. Types: decision, problem, assumption-mismatch,
review-disagreement. The task becomes blocked-decision; Zack brings the brief to
the planning chat and pastes the reply; `wf-decision.sh E-NNN --reply-file F`
records it in `docs/decisions.md` and unblocks. A problem report (unexpected
error, assumption mismatch, tool bug) uses the same brief with the matching
type. Never fix a bug in the tooling you are using for measurements without
escalating first.

## Lanes

Lane 1 works on the main checkout. Lanes 2 and 3 claim their task (the claim
creates the worktree and branch), work and commit inside
`.workflow/worktrees/lane-N`, and only ever write their own lane file
`.workflow/lanes/N.json`. `render` merges the main state and the lane mirrors,
so `PROGRESS.md` never conflicts between branches. When a lane's work is
finished, `wf.sh merge-lanes N` merges the branch into main, folds the lane
file into the state, and removes the worktree. A crashed lane session is freed
with `wf.sh lane-release N` (its active tasks revert to ready).

## Locks

- Lane locks (`<git-common-dir>/workflow/locks/lane-N.lock`): one session per
  lane; dead holder pids are cleaned by the guard.
- Machine-wide lock (`machine_lock` in `config.toml`, default
  `/dev/shm/local-ai-research-machine.lock`): taken by gpu, exclusive-machine
  and cpu-heavy tasks from `start` to `done`, so sessions in OTHER repos cannot
  start conflicting heavy work. Release after a crash: `wf.sh machine-release`
  (only after human confirmation).
- The repo's own GPU lock (for measurement scripts) is untouched by the kit and
  stays authoritative for the processes it wraps. Note it is repo-local: when a
  second measured repo appears, point `SMALLPC_GPU_LOCK_FILE` at a shared path
  (proposed: `/dev/shm/gpu.lock`) — a decision for Zack, not for a session.

## Plan edit rights

Sessions may append new cards to `PLAN-ADDED.md` (with the reason and the
escalation that caused them) and change statuses through the scripts. They may
NOT edit `PLAN.md`, existing cards, acceptance criteria, pre-declared rules or
gates. If a fix is bigger than a few steps: write a new card, mark it ready,
stop with "I added task T-xxx, run /continue".
