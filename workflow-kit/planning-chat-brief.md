# Planning-chat brief — how to write a PLAN.md the workflow kit can execute

Attach this file to the planning chat. The chat plans; it never executes. It
delivers ONE downloadable file, `PLAN.md`, that the kit's sessions then run task
by task. Everything below is mechanical: the kit's `wf-plan-import.sh` validates
it and refuses what does not fit.

## Who does what

- **The planning chat (you):** writes PLAN.md — rules first, then data. You
  answer escalations brought back by Zack ("DECISION E-NNN" replies).
- **Executor sessions** (`/continue`, `/lane N`): run ONE task at a time, record
  evidence, stop at gates, escalate judgement calls. They never plan.
- **The reviewer** (`/review`): the same model as the executor (see the kit's
  `config.toml` note), so acceptance must be machine-checkable wherever
  possible — that is YOUR job when writing cards.

## PLAN.md structure (in this order)

```markdown
# <title>
*Version N.N · <date>*

## Shared rules          (frozen; every session reads them with every card)
## Assumption register   (every assumption, each checked by a named recon task)
## Phases
## Task cards
### T-NNN — <short title>   (one card per task, nothing else in the file)
```

Rules before data: everything under "Shared rules" is printed with EVERY card,
so keep it short and universal. Sessions may never edit PLAN.md; a re-issued
plan goes through `wf-plan-import.sh PLAN.md --amend` (unchanged cards keep
their status, changed cards are flagged for re-acknowledgement, and a card that
changed while its task is in progress blocks the amend until it is finished).

## The card template (every field required)

```markdown
### T-NNN — Short title
id: T-NNN
title: Short title
phase: P1
depends_on: T-001            (or: none; comma-separated for several)
lane: 1                      (1, 2 or 3; the plan fixes the lane)
lane_reason: <one line>      (REQUIRED when lane > 1; must state the saving)
resources: light             (light | cpu-heavy | gpu | exclusive-machine)
files_read: path, path       (or: none)
files_write: path, path      (claim conflicts are checked against these)
gates: <what Zack must do>   (or: none)
review: none                 (none | post | pre+post)
preconditions:
  - cmd: <command>
    expect: exit_code 0      (or: stdout_regex <re> | file_exists <path> | json_eq <file> <dotted.path> <value>)
steps:
  - S1: <what to do> (redo-safe)          (every step ends with its marker)
  - S2: <what to do> (not redo-safe)      (cannot be repeated without confirmation)
acceptance:
  - cmd: <command>
    expect: exit_code 0
  - expect: file_exists <path>
  - expect: json_eq <file> <dotted.path> <value>
  - expect: stdout_regex <re>
  - expect: manual "<what a human or reviewer judges>"
  - cmd: <expensive command>
    expect: exit_code 0
    heavy: true               (deferred by wf accept; the reviewer decides)
evidence: <files the acceptance writes>   (hashed at accept time)
estimate: 45m
decision_rights:
  - may: <what the session may decide freely>
  - must_escalate: <what must come back to you>
```

Validation is mechanical and refuses: missing fields, bad enums, unknown
dependencies, dependency cycles, a lane > 1 without a reason, steps without
redo-safe markers, cmd items without expectations, a missing assumption
register, an assumption that names no existing recon task — and it WARNS when
a reviewed card's acceptance is mostly `manual` (same model on both sides;
machines must check what they can).

## Decision rights — write them per card

The card's `may` line is the session's authority; anything outside it, or any
surprise, becomes an escalation brief to you. Prefer a tight `may` on
measurement tasks (wording, argument names, step order) and a wide `must_escalate`
whenever raw data or acceptance criteria would be touched.

## Which tasks get review

- `review: post` for anything that produces evidence, numbers or docs — the
  default for measured work. Cheap, mechanical acceptance lets the reviewer
  re-run everything.
- `review: pre+post` for expensive GPU runs: the pre-review checks the setup
  before the machine time is spent.
- `review: none` only for trivial, fully machine-checked tasks.

## Lanes: when parallel work is worth it

A lane hint (lane 2 or 3) is honoured only when it passes the value test: the
tasks write different files, they do not contend for the machine (only `light`
tasks may run beside gpu / exclusive-machine work), and parallelism saves more
than about 30 minutes. Say so in one `lane_reason` line — the sessions will
refuse claims that conflict, and `/continue` asks Zack before starting lanes.

## Gates

If Zack must do something (close apps, run sudo, spend, publish, confirm the
machine is quiet), declare it in `gates`: the session stops at `gate-wait`,
prints exactly that, and waits for his "go". Never put a sudo command in a
step — the gate text is the instruction for Zack.

## The assumption register

Every plan rests on assumptions you cannot verify from the chat. Each entry
names the recon task that checks it:

```markdown
## Assumption register

- A1: the lock file lives at .locks/gpu.lock — checked by T-001
```

The recon task's acceptance should be the check (a `cmd` + `expect`), and its
findings feed the escalation protocol: an assumption that fails is an
`assumption-mismatch` escalation, never a silent workaround.

## Escalation replies

When a session escalates, Zack pastes you `escalations/E-NNN.md`. Reply in this
shape (recorded verbatim by `wf-decision.sh` in `docs/decisions.md`):

```markdown
DECISION E-NNN
Chosen option: A
Reason: <one line>
Scope: <this plan | standing rule>
Rule: <the standing rule text, if it becomes one>
```

## A worked example

A complete, valid example plan (6 tasks: one parallel pair T-002/T-003 in lanes
2 and 3, one human gate in T-004, post-review on T-004 and T-005, an escalation
path from a RE-MEASURE finding, and an assumption register checked by the first
task) ships with the kit as `templates/plan-example.md`. It is also the kit's
end-to-end test fixture: every construct in it is proven to parse and run.

## Delivery

One file, `PLAN.md`, downloadable from the chat. Nothing else — the sessions
bootstrap everything else from the kit.
