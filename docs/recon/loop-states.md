# T-017 recon — workflow-kit states, exit codes and headless behaviour

<!-- sources: scripts/_wf.py, scripts/wf.sh, docs/WORKFLOW.md, .workflow/config.toml, .claude/commands/continue.md, .claude/commands/lane.md, .claude/commands/status.md, .claude/commands/review.md, .claude/commands/address-review.md, .claude/settings.json -->

Recon for the unattended loop (`scripts/wf-loop.sh`). Every claim below carries a
`file:line` pointer into the kit engine `scripts/_wf.py` (2674 lines, read in full)
or the named command file. Line numbers are from the lane-3 worktree copy at start
HEAD `49f92c2` (see `docs/recon/T-017-start.txt`); `_wf.py` is frozen until T-008 so
they are stable for this task.

The loop's contract (card S3): run fresh headless `claude -p "/continue"` sessions,
and after each session read `.workflow/state.json` + the session exit code and
continue **only** if the last task finished cleanly and nothing needs a human.
This document is the evidence base for which states mean "continue" and which mean
"stop, human needed".

---

## 1. Task statuses and the commands that move between them

### 1.1 The status vocabulary

`ALL_STATUSES` — `scripts/_wf.py:54-67`:
`todo, ready, claimed, in-progress, awaiting-gate, done, in-review,
changes-requested, accepted, blocked-decision, superseded, cancelled`.

Two subsets drive the loop:
- `ACTIVE_STATUSES = ("claimed", "in-progress", "awaiting-gate")` — `_wf.py:52`.
  A task in any of these is "being worked / waiting mid-task".
- `TERMINAL_STATUSES = ("accepted", "superseded", "cancelled")` — `_wf.py:53`.
  No further transitions out of these (`TRANSITIONS["accepted"] = set()`, etc.,
  `_wf.py:130,142-143`).

Note `done` is **not** terminal: a `done` task with `review != none` still owes a
review (`done -> in-review`, `_wf.py:115`). Only `done` + `review == none` counts as
complete for dependency purposes (`task_deps_satisfied`, `_wf.py:439-440`) and for
phase advancement (`current_phase`, `_wf.py:1338-1340`).

### 1.2 The transition table

`TRANSITIONS` — `_wf.py:103-144`. The ones the loop cares about:

| from | to | command (fn) | evidence |
|---|---|---|---|
| todo | ready | `recompute_ready` (automatic, on any mutate) | `_wf.py:446-470` |
| ready | claimed | `claim` (`cmd_claim`) | `_wf.py:1381-1451` |
| claimed | in-progress | `start` (`cmd_start`) | `_wf.py:1470-1492` |
| claimed/… | in-progress | `resume` (`cmd_resume`, orphaned task) | `_wf.py:1532-1572` |
| in-progress | awaiting-gate | `gate-wait` (`cmd_gate_wait`) | `_wf.py:1603-1613` |
| awaiting-gate | in-progress | `gate-release` (`cmd_gate_release`) | `_wf.py:1616-1618` |
| in-progress / awaiting-gate | done | `done` (`cmd_done`) | `_wf.py:1827-1870` |
| done / changes-requested | in-review | `review-open` (`cmd_review_open`) | `_wf.py:1887-1906` |
| in-review | accepted / changes-requested / blocked-decision | `review-verdict` (`cmd_review_verdict`) | `_wf.py:1924-1948` |
| any non-terminal | blocked-decision | `block` (`cmd_block`) | `_wf.py:2002-2014` |
| any non-terminal | blocked-decision | `escalate` (`cmd_escalate`) | `_wf.py:2062-2102` |
| blocked-decision | (the status it was blocked from) | `unblock` / `decision` (`cmd_unblock`, `cmd_decision`) | `_wf.py:2017-2032`, `2105-2128` |
| any non-accepted | superseded | `supersede` (`cmd_supersede`) | `_wf.py:2176-2193` |
| (new) | todo/ready | `add-task` (`cmd_add_task`) | `_wf.py:2134-2173` |
| active (lane) | ready | `lane-release` (`cmd_lane_release`) | `_wf.py:2216-2244` |

`step-done` (`cmd_step_done`, `_wf.py:1575-1600`) and `review-disposition`
(`cmd_review_disposition`, `_wf.py:1951-1990`) do **not** change status; they record
`steps_done` / a disposition list. `mutate` (`_wf.py:526-554`) is the single write
path: it validates the transition, updates the owning file, re-derives readiness and
re-renders `PROGRESS.md`.

### 1.3 What "finished cleanly" means for the loop

A session that ran a task to completion leaves the task in `done` (review pending)
or `accepted`/`in-review` (if it also reviewed). The authoritative signal is the
`done` command's stdout line plus exit 0 (see §6). A task left in `claimed`,
`in-progress` or `awaiting-gate` after a session means the session did **not** finish
it — the loop must treat that as "no clean finish" and inspect why.

---

## 2. Exit codes and output of each `wf.sh` subcommand the loop would call

### 2.1 The global exit-code contract

`main()` — `_wf.py:2661-2670`:
- returns **0** on success;
- catches `WfError` (raised by every `die()`, `_wf.py:168-173`), prints
  `wf: <message>` to **stderr** and returns **1**.
- `argparse` failures (missing/unknown subcommand, bad/missing required argument)
  exit **2** (argparse default; subcommand is `required=True`, `_wf.py:2494`).
  Verified: `bash scripts/wf.sh` with no subcommand → `exit=2`.
- `cmd_guard` is the one command that calls `sys.exit(1)` itself when it finds
  problems (`_wf.py:656-658`); otherwise it prints `guard: OK` and returns (exit 0,
  `_wf.py:659`).

So: **0 = ok, 1 = a kit refusal/error (message on stderr), 2 = bad invocation.**
The loop can rely on `!= 0` meaning "something refused", but the *reason* must be
read from state.json or stderr — most "human needed" states are NOT exit codes (see
§6.2).

### 2.2 Per-subcommand behaviour (read-only ones verified live)

| subcommand | exit on success | stdout (shape) | notes / evidence |
|---|---|---|---|
| `guard` | 0 | `guard: OK` | 1 + `GUARD:` lines on problems (`_wf.py:654-659`). May delete a stale lane lock (`_wf.py:628-638`). |
| `status` | 0 | `plan: …`, `phase: …`, one line per task `T-xxx  <status>  lane N  <title>`, then optional `blocked-decision (escalations): …` and `READY: …` | `_wf.py:1318-1331`. Always 0 unless state unreadable. |
| `ready` | 0 | `lane N  T-xxx  <title>` (+ `    lane reason: …`) per ready task; **`no ready tasks`** when none | `_wf.py:1346-1361`. **Exit 0 even when nothing is ready** (`_wf.py:1353-1355`) — the loop must parse output/state, not the exit code, to detect "nothing to do". |
| `config` | 0 | effective config as JSON | `_wf.py:2448-2449`. `max_review_cycles` lives here (`config.toml:9`, default `_wf.py:159`). |
| `lane-status [N]` | 0 | `lane N: ACTIVE pid … \| worktree … \| …` | `_wf.py:2199-2213`. |
| `card T-xxx` | 0 | shared rules + ONE card + `status: … lane: … review: …` | `_wf.py:1293-1312`. The trailing `review:` field tells the loop the card's review policy. |
| `claim T-xxx [--lane N]` | 0 | `claimed T-xxx (lane 1); next: wf.sh start …` or, lane 2+, `claimed … worktree: <path>` | `_wf.py:1381-1451`. Refuses (exit 1) if not ready, wrong lane, file/resource conflict, machine lock taken. |
| `start T-xxx` | 0 | `started T-xxx (in-progress, lane N)` + `first step: S1 — …` | `_wf.py:1470-1492`. Refuses if orphaned (use resume). |
| `precheck T-xxx` | 0 | `Pn PASS/FAIL …` + `all preconditions pass` | `_wf.py:1721-1743`. Any FAIL → exit 1, "STOP and report". |
| `accept T-xxx` | 0 | `An PASS/FAIL/JUDGEMENT/DEFERRED …`, evidence lines, `record: … failures: N` | `_wf.py:1749-1805`. **Exit 0 even with failures** — failures are counted in the record and printed, not raised. The loop reads `failures` / the record, not the exit code. |
| `done T-xxx` | 0 | `TASK T-xxx DONE \| review: … \| judgement items: … \| next ready: (run wf.sh ready)` | `_wf.py:1827-1870`. Refuses (exit 1) if not in-progress, no accept record, any FAIL item, or missing evidence. |
| `review-open T-xxx` | 0 | `T-xxx in-review (cycle N); report: …` | `_wf.py:1887-1906`. Refuses (exit 1) past `max_review_cycles` ("escalate … review-disagreement"). |
| `review-verdict T-xxx <v> --report-file F` | 0 | `T-xxx -> <verdict>; archived to …` | `_wf.py:1924-1948`. |
| `escalate --task … --type … --brief-file …` | 0 | `escalation E-NNN written …; task … is blocked-decision` | `_wf.py:2062-2102`. |
| `decision E-NNN --reply-file F` | 0 | `decision E-NNN recorded …; task … unblocked` | `_wf.py:2105-2128`. |

Verified live from the lane-3 worktree (read-only): `ready`, `status`, `config`,
`lane-status` all `exit=0`; no-subcommand `exit=2`.

**Key consequence for the loop:** `accept` and `ready` return 0 even when there is a
failure / nothing ready. The loop's stop logic therefore reads **state.json** (and
the acceptance record / stdout), not just exit codes. Exit codes are a secondary
signal (a non-zero from the *claude session* or from `done`/`review-open` is a hard
stop).

---

## 3. How gate / escalation / pending review / blocked-decision look in state.json

### 3.0 Where the authoritative state lives (critical)

`state_path()` **always** resolves to the **main checkout**:
`main_root(repo)/.workflow/state.json` (`_wf.py:299-301`, `main_root` `_wf.py:212-214`).
A worktree's own `.workflow/state.json` is a **stale branch copy** — confirmed live:
the lane-3 worktree copy still showed `T-004 ready` while the main checkout showed
`T-004 in-progress`. The loop must read the **main checkout** state, never a worktree
copy.

The full picture is the **effective view**: main-state tasks overlaid by every lane
mirror (`effective_tasks`, `_wf.py:398-408`). Lane mirrors live at
`<git-common-dir>/workflow/lanes/N.json` (`shared_dir`, `_wf.py:217-218`;
`lane_mirror`, `_wf.py:308-309`). Verified live: `T-017` is `todo` in main state but
`in-progress` in `.git/workflow/lanes/3.json`, and `wf.sh status` (which uses
`effective_tasks`) correctly shows `in-progress`. **The loop must merge main state +
lane mirrors** (or call `wf.sh status`/`ready`, which do) to see the truth.

state.json top-level keys (verified live): `version, kit_version, plan_file,
plan_sha256, phases, title, created_utc, tasks, events, escalations, review_cycles,
review_dispositions, checksum`. The `checksum` (`_wf.py:312-332`) means the loop must
**never hand-edit** state; it only reads it.

### 3.1 A gate (HUMAN-GATE)

`cmd_gate_wait` (`_wf.py:1603-1613`) sets:
- `tasks[T-xxx].status = "awaiting-gate"` (an ACTIVE status, `_wf.py:52`);
- `tasks[T-xxx].gate_message = "<what Zack must do>"`.

**Loop detection:** any effective task with `status == "awaiting-gate"` → STOP
(human must `gate-release`). The message is in `gate_message`.

### 3.2 An escalation

`cmd_escalate` (`_wf.py:2062-2102`) writes:
- `escalations["E-NNN"] = {task, type, status: "open", created_utc}`
  (`_wf.py:2079-2085`);
- the task → `blocked-decision` with `blocked_reason = "escalation E-NNN"`
  (`_wf.py:2088-2100`).

`cmd_decision` (`_wf.py:2105-2128`) flips `escalations[E-NNN].status` to `"decided"`,
adds `decided_utc`, and unblocks the task.

**Loop detection:** any `escalations[*].status == "open"` → STOP. (Equivalently, a
task `blocked-decision` whose `blocked_reason` names an open escalation.) Verified
live: main state currently has E-001/E-002/E-003 all `"decided"`, none open.

### 3.3 A pending review

- A task awaiting review is `status == "in-review"` or `"changes-requested"`
  (review queue render, `_wf.py:2386-2398`).
- `review_cycles[T-xxx]` (int) counts opened cycles (`review_cycles`,
  `_wf.py:1876-1877`; incremented by `review-open`, `_wf.py:1895-1901`).
- `review_dispositions[T-xxx]` is a list of `{cycle, finding, severity, action_taken,
  reason}` (`_wf.py:1973-1983`).
- The card's review policy (`none` / `post` / `pre+post`) is `tasks[T-xxx].review`
  (`_wf.py:1196`) and is echoed by `wf.sh card` (`_wf.py:1312`).
- `max_review_cycles = 2` (`config.toml:9`, default `_wf.py:159`); `review-open`
  refuses past it (`_wf.py:1896-1900`).

**Loop detection:** a `done` task with `review != none` and `review_cycles < max`
owes a post-review; a `changes-requested` task owes `/address-review`; an
`in-review` task is mid-review. A `ready` task with `review == "pre+post"` owes a
pre-review before its heavy work (continue.md:52-53). These drive the loop's review
scheduling (card S3), not a hard stop — unless cycles are exhausted (then escalate).

### 3.4 A blocked-decision

`cmd_block` (`_wf.py:2002-2014`) / `cmd_escalate` set:
- `tasks[T-xxx].status = "blocked-decision"`;
- `tasks[T-xxx].blocked_from = "<previous status>"`;
- `tasks[T-xxx].blocked_reason = "<reason>"`.

**Loop detection:** any effective task `status == "blocked-decision"` → STOP for
that task; the loop never works a blocked task (CLAUDE.md / continue.md:10-14). A
blocked-decision does **not** stop *other* ready tasks (CLAUDE.md "Every session
starts by" §2), but the loop's v1 is serial (one session at a time), so an open
escalation that blocks the only ready lane is a practical stop. The card S3 lists
"any open gate, escalation or blocked-decision" as a stop condition — the loop stops
on the first such state it encounters when choosing the next action.

---

## 4. How a ready task is chosen; where /continue asks the lane question

### 4.1 Readiness derivation

`recompute_ready` (`_wf.py:446-470`) promotes `todo -> ready` when
`task_deps_satisfied` (`_wf.py:434-443`): every `depends_on` task must be `accepted`,
or `done` with `review == none`. It runs on every `mutate`, so readiness is always
current in state.

### 4.2 The READY list

`cmd_ready` (`_wf.py:1346-1361`) selects effective tasks with `status == "ready"`,
groups them by `task["lane"]`, sorts lanes then task ids, and prints
`lane N  T-xxx  <title>` plus the card's `lane_reason`. **No ready tasks → prints
`no ready tasks`, exit 0** (`_wf.py:1353-1355`).

### 4.3 Where the lane question is asked

The question is **not** in `_wf.py` — it is in the command file
`.claude/commands/continue.md:19-23` (step 3):

> Several LANES ready: list them … then ASK: "Start lane 1 (<task T-xxx>?" — wait
> for Zack's yes. Do not start anything before the answer. …

`.claude/commands/lane.md:10-12` is the pre-selected variant: it picks the ready task
whose lane is `$ARGUMENTS` and asks **no** question.

**Consequence for the loop (the central design problem):** a headless
`claude -p "/continue"` session that hits "several lanes ready" will, per the command,
stop and ask — but there is no human to answer. The loop must supply the "yes, lane 1"
answer itself (card S3: "when several tasks are ready it answers yes to lane 1").
The mechanism for doing that headlessly is a design decision escalated in S3 (see
`docs/recon/loop-design.md`); it cannot be verified in this task because the card
forbids running `/continue`, `/lane` or `/review` headlessly here (S2).

---

## 5. Session ids and locks (WF_SESSION_PID)

### 5.1 Session pid

`session_pid()` (`_wf.py:229-259`):
- `WF_SESSION_PID` env var overrides everything (`_wf.py:235-240`) — used by tests
  and non-claude drivers;
- otherwise walks the `/proc` parent chain (up to 20 hops) for a process whose
  `comm` starts with `claude` (`_wf.py:241-259`);
- returns **0** if unknown. `pid_alive(0)` is **True** ("unknown owner: never
  auto-stale", `_wf.py:262-265`).

**Consequence for the loop:** each headless `claude -p` session is its own `claude`
process, so claims/locks it takes record that session's pid. When the session exits,
its pid dies, and the guard / resume path treats its claim as orphaned
(`cmd_start` refuses an orphaned claim, `_wf.py:1477-1481`; `cmd_resume` takes over,
`_wf.py:1540-1542`). The loop itself is a bash process (not `claude`); if it ever
called a mutating `wf.sh` command directly it would record pid 0 — but the loop only
**reads** state and launches claude sessions, so it never takes a claim itself.

### 5.2 Locks

- **Lane locks:** `<git-common-dir>/workflow/locks/lane-N.lock`, JSON
  `{pid, task, ts}` (`take_lane_lock`, `_wf.py:739-749`). One session per lane; a live
  holder pid blocks a second claim (`_wf.py:742-748`). The guard removes a stale lock
  whose holder pid is dead and whose lane has no active task (`_wf.py:628-638`).
  Released when a lane goes idle (`release_lane_lock_if_idle`, `_wf.py:758-773`).
- **Claims registry:** `<git-common-dir>/workflow/claims.json`,
  `{T-xxx: {lane, pid, ts, resources}}` (`_claims`, `_wf.py:707-714`). Verified live:
  T-004 (lane 1), T-005 (lane 2), T-017 (lane 3) each with their session pid.
- **Machine-wide lock:** `config.toml:18` `machine_lock =
  /dev/shm/local-ai-research-machine.lock` (override `WF_MACHINE_LOCK`,
  `_wf.py:291-293`); taken by gpu/exclusive-machine/cpu-heavy tasks from start to done
  (`take_machine_lock`, `_wf.py:791-798`; `machine_lock_free`, `_wf.py:776-788`).
  T-017 is `light`, so it never takes this lock.

**Consequence for the loop:** the loop runs **one session at a time** (card S3, "no
parallel sessions"), so it never contends with itself for a lane lock. But a lane
lock left by a *crashed* headless session could block the next claim; the guard
(called at the start of every `/continue`) cleans dead-holder locks, so the loop
relies on `/continue`'s guard rather than touching locks itself. The loop's **own**
lock (so two loops cannot run) is a separate file it manages (card S3), distinct from
the kit's lane/machine locks.

---

## 6. Which signal means "task done, next ready: X" vs "stop, human needed"

### 6.1 "Task done, next ready: X"

`cmd_done` (`_wf.py:1827-1870`) on success prints exactly:

```
TASK T-xxx DONE | review: required, run /review in a fresh session | judgement items: … | next ready: (run wf.sh ready)
```

(`_wf.py:1860-1870`; `review: none` when the card says so). The
`next ready: (run wf.sh ready)` is a **placeholder** — the comment at `_wf.py:1866`
says "commands replace this". Exit code **0**.

**Loop interpretation:** session exit 0 **and** the task it attempted is now `done`
(or further along: `in-review`/`accepted`) in the effective state **and** no new
gate/escalation/blocked-decision appeared → the task finished cleanly. The loop then
runs `wf.sh ready` to find the next ready task (and schedules a review if the card
owes one). The `TASK … DONE` stdout line is a convenient positive marker, but the
authoritative check is the state transition (a session could print the line and then
fail to commit; the loop also checks the tree is clean, card S3).

### 6.2 "Stop, human needed"

There is **no single exit code** for this. The loop detects it from state.json (and
secondarily from non-zero exits):

| condition | state.json signature | evidence |
|---|---|---|
| open HUMAN-GATE | a task `status == "awaiting-gate"` (+ `gate_message`) | `_wf.py:1603-1613` |
| open escalation | `escalations[*].status == "open"` | `_wf.py:2079-2085` |
| blocked-decision | a task `status == "blocked-decision"` | `_wf.py:2002-2014`, `2088-2100` |
| failed acceptance | `done` exits 1 ("acceptance item … FAILED"); accept record `failures > 0` | `_wf.py:1840-1845`, `1780` |
| review cycles exhausted | `review-open` exits 1 ("already used N review cycles") | `_wf.py:1896-1900` |
| precondition failure | `precheck` exits 1 ("STOP and report") | `_wf.py:1741-1742` |

A non-zero exit from the **claude session itself**, or a usage-limit message in its
output, is also a hard stop (card S3) — that is outside state.json and must be read
from the session's exit code / captured output.

### 6.3 "Nothing to do" (not a human stop, but a loop exit)

`wf.sh ready` prints `no ready tasks` (exit 0, `_wf.py:1353-1355`) and no task is
active/blocked/reviewable. The loop exits cleanly ("plan idle / complete"), distinct
from a human-needed stop. If everything ready is waiting at a gate, the loop may run
a *due* review (card S3) rather than exit immediately.

---

## 7. S2 — headless slash-command behaviour (read-only test)

Ran `claude -p "/status"` from the lane-3 worktree (the only headless slash command
this task may run; `/continue`, `/lane`, `/review` are forbidden here). Captured
stdout/stderr to `/tmp/wf-loop-s2-status.{out,err}`.

**Result: exit code 0; the slash command WAS expanded and executed.** stdout shows
the full `/status` procedure output: `guard: OK`, the `wf.sh status` task table, the
`wf.sh ready` line, `wf.sh lane-status`, the last 5 PROGRESS.md events, and the
command's interpretation line ("No task is `blocked-decision`, and the review queue
is empty"). So `claude -p "/<command>"` runs the command file's procedure in headless
mode — the loop can rely on `claude -p "/continue"` doing the same.

Observations that the loop design must handle:
1. **stdin wait:** stderr carried `Warning: no stdin data received in 3s, proceeding
   without it. … redirect stdin explicitly: < /dev/null to skip`. Headless claude
   waits ~3s for stdin. The loop must redirect stdin (`< /dev/null`, or pipe the
   lane answer — see §4.3 / loop-design.md) to avoid the delay and to feed the
   "yes, lane 1" answer.
2. **stderr noise is harmless:** `claude.ai connectors are disabled …` (an
   `ANTHROPIC_API_KEY` is set) and `[claude-code:unrecognized_model]
   {"model":"qwen4-max-preview",…}` both went to stderr and did **not** affect the
   exit code (0). The loop must not treat stderr presence as failure — only the exit
   code and explicit usage-limit text matter.
3. **Effective state is visible headlessly:** the nested `/status` session correctly
   showed T-005/T-017 as `in-progress` (lane mirrors) and the live lane pids, even
   though it ran from a worktree. A headless session reads the main state + shared
   runtime correctly, so the loop's per-session state reads are trustworthy.
4. **claude CLI:** `/home/zack/.local/bin/claude`, version `2.1.323 (Claude Code)`.
   `python3` 3.14.9 and `jq` are both on PATH (the loop may use either for JSON;
   `python3` is guaranteed by the kit, `wf.sh:8`).

**Not verified (forbidden in this task):** whether `claude -p "/continue"` actually
proceeds past the lane question when a "yes" is supplied on stdin, and the exact
headless behaviour of `/review` / `/address-review`. These are design assumptions
escalated in S3 for approval (and, if approved, verified in S4/S5 against fixtures
with a fake claude, never against this repo's real state).
