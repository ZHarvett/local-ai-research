# workflow-kit

The files, scripts and slash commands that let a Claude Code session execute a
planning-chat plan task by task: recorded progress, human gates, adversarial
review, escalations, and parallel lanes. One model is executor, subagent and
reviewer alike (`config.toml`: `model_note`), so acceptance is mechanical
wherever possible and reviews re-run the evidence instead of trusting claims.

## What is here

| path | what |
|---|---|
| `scripts/_wf.py`, `scripts/wf.sh` | the engine (stdlib-only Python + bash dispatcher); `wf.sh --help` lists all subcommands |
| `scripts/wf-{card,plan-import,guard,progress,escalate,decision,merge-lanes}.sh` | the named entry points |
| `.claude/commands/` | `/continue`, `/lane N`, `/review`, `/address-review`, `/escalate`, `/status`, `/calibrate-reviewer` |
| `templates/` | CLAUDE.md block, docs/WORKFLOW.md, settings.json, escalation brief, review report, worked example plan |
| `planning-chat-brief.md` | what you attach to a planning chat so it writes a compliant PLAN.md |
| `calibrate/` | a finished task with planted errors + answer key (reviewer self-test) |
| `bootstrap.sh`, `sync.sh` | install into a repo / update kit-owned files |
| `tests/` | 116 tests (pytest) incl. an end-to-end scripted run of the example plan |

## Install into a repo

```bash
workflow-kit/bootstrap.sh <target-repo>            # see what it would do:
workflow-kit/bootstrap.sh <target-repo> --dry-run  # nothing is written
```

Bootstrap never overwrites silently: differences are reported as diffs and
skipped without `--force`; an existing `.claude/settings.json` is never touched
(a suggested diff is printed); CLAUDE.md is merged via the
`<!-- workflow-kit:begin/end -->` markers (appended when absent). It writes
`.workflow-kit-version` + `.workflow-kit-manifest.json` (what `sync.sh` uses).
`--with-hook` installs a pre-commit hook that runs `wf-guard.sh`. After
installing, commit, drop the plan's `PLAN.md` in the repo root, and run
`bash scripts/wf-plan-import.sh PLAN.md`.

Updating a repo's kit later: `workflow-kit/sync.sh <target-repo>` (adds missing
kit files, updates unchanged ones, refuses locally-modified ones without
`--force`; settings.json is never touched).

## A typical session

1. Zack types `/continue` in a fresh session (the repo has `PLAN.md`,
   `.workflow/` and `PROGRESS.md` from a previous import).
2. The session runs the guard, shows status; if tasks are blocked-decision it
   stops (decisions come from the planning chat, recorded with
   `wf-decision.sh`).
3. One ready task → claim, run the card's steps (`wf.sh step-done` after each),
   stop at every gate (`wf.sh gate-wait` / `gate-release`), run
   `wf.sh accept`, then `wf.sh done`, commit, and end with
   `TASK T-xxx DONE | review: … | next ready: …`.
4. Several lanes ready → the session asks "Start lane 1 (<task>?)"; Zack opens
   `/lane 2` and `/lane 3` in other terminals (max 3).
5. Cards with `review: post` end with "run /review in a fresh session"; the
   reviewer re-runs `wf.sh accept`, writes REVIEW_REPORT.md, sets the verdict.
   `/address-review` records a disposition per finding (BLOCKERs are never
   rejected; RE-MEASURE/DECIDE findings always escalate).
6. Anything unexpected → `/escalate` writes `escalations/E-NNN.md`, the task
   becomes blocked-decision, Zack brings the brief to the planning chat.

## When a session stops

| it stopped at | what you do |
|---|---|
| a HUMAN-GATE | the printed instruction (e.g. close apps), then say "go" (or run `wf.sh gate-release T-xxx`) |
| blocked-decision | bring `escalations/E-NNN.md` to the planning chat; paste the reply into a file and run `bash scripts/wf-decision.sh E-NNN --reply-file F` |
| "Start a fresh session and run /continue" | context discipline — do exactly that (steps were recorded) |
| changes-requested | run `/address-review T-xxx` |
| a crashed lane (stale lock) | `bash scripts/wf.sh lane-release N`, then `/lane N` again |
| a crashed machine lock | confirm nothing heavy runs anywhere, then `bash scripts/wf.sh machine-release` |

## Checks

```bash
cd workflow-kit
uv run pytest        # 116 tests, no GPU, no model
uv run ruff check . && uv run ruff format --check .
shellcheck scripts/*.sh bootstrap.sh sync.sh
```

`/calibrate-reviewer` (in a bootstrapped repo) runs the bundled
planted-error task and stores the result in `.workflow/calibration.json`, so
the planning chat can see how much to trust reviews.
