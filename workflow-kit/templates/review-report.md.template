# Review T-xxx (cycle N)

## Model

State the model you are running as (one line, for transparency — the config
notes a single model for executor and reviewer).

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-xxx` myself. One row per acceptance item:

| item | verdict | note |
|---|---|---|
| A1 | PASS / FAIL / DEFERRED / ESCALATE | what was re-run, what matched, what did not |

## Findings

Each with severity, an evidence pointer, and the CHEAPEST sufficient action.
RE-ANALYSE is the default whenever re-analysis could fix it; RE-MEASURE names
the card steps to redo and a time estimate but is NEVER ordered by the reviewer
(it becomes an escalation); DECIDE presents the options for the human.

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | BLOCKER / MAJOR / MINOR / NOTE | FIX-DOC / FIX-CODE / RE-ANALYSE / RE-MEASURE / DECIDE | file:line | … |

## Task verdict

accepted | changes-requested | blocked-decision

## What I did not verify

Everything you did not check, plainly: heavy items deferred, files not read,
claims not re-derived. (This section is required — never omit it.)
