# Review T-017 (cycle 1)

## Model

qwen4-max-preview (same model as executor; adversarial re-derivation, read-only).

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-017` myself (run 2, 0 failures, at HEAD `05dc32e`
or later — a concurrent session landed T-006 commits `d4badce`/`e315ff5`/`28be44a`
during this review; T-017's files are untouched since `d43741e`, verified by
`git diff --name-only d43741e..HEAD` over the task's files, empty).

| item | verdict | note |
|---|---|---|
| A1 | PASS | `shellcheck scripts/wf-loop.sh` re-run, exit 0, no output. |
| A2 | PASS | `uv run pytest -q tests/test_wf_loop.py` re-run: **37 passed in 4.03s** — count matches the progress-log claim (32 at S4 + 5 at S5). Tests use a fake claude + fixture git repos/state in temp dirs only; no test invokes the real CLI (S2's `/status` probe was the one allowed real run, E-004 change 2). |
| A3 | PASS | `bash scripts/wf-loop.sh --help` re-run, exit 0; usage lists all stop conditions and env knobs. |
| A4 | PASS | `uv run ruff check` + `ruff format --check` on the test file re-run, exit 0. |
| A5 | PASS | Re-ran the diff check; additionally verified independently: `git diff --name-status 49f92c2..d43741e` shows only **Added** files (script, command, tests, two recon notes, start-HEAD file, escalation briefs E-004/E-005, kit state) plus `M docs/progress-log.md` — all within `files_write` or standard kit/escalation output. No existing file under src/, configs/, scripts/, pyproject.toml, uv.lock touched; tests/conftest.py unchanged (the new test imports `REPO` from it). |
| A6 | PASS | `! grep -q 'dangerously-skip-permissions' scripts/wf-loop.sh` re-run, exit 0. Extra claude args come only from `WF_LOOP_CLAUDE_ARGS` (wf-loop.sh:402), word-split via `read -r -a`, no eval of args; verified by `test_claude_args_come_only_from_env`. |
| A7 | PASS | File exists on main; `sha256sum` = `6a5ed823…` — identical to the hash recorded at accept time in the lane-3 worktree, so the merge carried it unchanged. |
| A8 | PASS (with caveat F-1) | Judged clause-by-clause against the code and the 37 re-run tests: no gate path exists (awaiting-gate → stop, helper line 266-269; test_stop_2); open escalation / blocked-decision stop new work (254, 270-275; tests 3, 4) and a blocked-decision task is never reviewed (status filters 226-230; test_never_reviews_a_blocked_task); deadline checked before every launch (499-501; test_stop_1); lanes lowest-first per E-004 option B (254-261; test_multi_lane_uses_lowest_lane_then_continue); reviews are status- and cycle-bounded (226-230; tests in "review scheduling"); every human-needed state stops with reason + task id (finish(), tests). New blockers appearing mid-session stop the loop (548-554). **Caveat:** the "due pre-review of a ready pre+post task" the card/design promise cannot actually complete under the frozen kit — see F-1. The loop's own behaviour is safe (it stops); the gap is design/kit-level. |

Evidence integrity: all three evidence hashes re-verified (`loop-states.md`
`04f33f43…`, `loop-design.md` `67965d35…`, `wf-loop.sh` `a16ed003…`). Spot-checked
12 `file:line` citations from loop-states.md against `scripts/_wf.py` (52-53, 54-67,
217-218, 229-240, 1196, 1353-1355, 1813-1824, 1840-1845, 1860-1870, 1876-1877,
656-659, 2661-2670) — **all accurate**. The S2 headless `/status` captures still
exist in /tmp and corroborate §7 verbatim (command expanded, guard/status/ready/
lane-status output, 3 s stdin warning, connectors + unrecognized_model stderr
noise, effective lane state visible). No `/tmp/wf-loop-<stamp>.log` exists —
consistent with the attestation that the loop was never run against real state.

Decision fidelity (re-derived against docs/decisions.md:1236-1252):
- **E-004 option B, all 5 changes implemented**: (1) several ready lanes →
  `/lane <lowest>`, one → `/continue`, no stdin answer (helper 254-261,
  run_session 403-404); (2) fake claude only in tests; (3) guard failure stops
  except the E-005 line; (4) supervised-first-run note in the startup log (495)
  and keep-continuing.md step 3; (5) final message names reason + task (90-99).
- **E-005 exception is exact and narrow**: the helper's regex (298-301) matches
  only the literal placeholder form the guard actually prints (`guard()`
  `_wf.py:605-616`, all problems prefixed `GUARD:`), requires both lane numbers
  equal, requires the effective status ∈ {in-progress, awaiting-gate,
  blocked-decision} (ready/todo/done → stop), and stops if ANY other GUARD line
  is present or no GUARD line exists. Matches the decision text clause by clause.
- Helper semantics match the kit: mirror overlay identical to `effective_tasks`
  (`_wf.py:398-408`); `accept_failures` mirrors `latest_accept_record`
  (`_wf.py:1813-1824`, worktree-then-repo); `review_cycles` main-state-only,
  exactly as the kit reads it (`_wf.py:1876-1877`). The acceptance-failure stop's
  exclusion of done/in-review/accepted is sound: `cmd_done` refuses any FAIL item
  (`_wf.py:1840-1845`), so done-with-failures cannot arise from a work session.
- `--dry-run` verified live against the real state (read-only; no lock, no log,
  no guard, writes only a /tmp scratch dir): correctly printed
  `next action: review task=T-017 prompt=/review T-017`.

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | MAJOR | DECIDE | scripts/_wf.py:1891-1892, 105; scripts/wf-loop.sh:229,262-263; docs/recon/loop-design.md:106-110,188-190; docs/progress-log.md (T-017 open issue 4) | Planning-chat ruling: the promised pre-review of a ready pre+post task cannot be opened under the frozen kit; decide the interim protocol for T-007 and whether to schedule a kit change. Options below. |
| F-2 | MINOR | FIX-DOC | docs/recon/loop-states.md:372; docs/recon/T-001.md:131; PLAN.md D8 | Replace the home path containing the account name with `<home>`/`~` (refer to it as `<account-name>`, never write it); re-run `wf.sh accept T-017` to refresh the evidence hash. |
| F-3 | MINOR | FIX-DOC | docs/recon/loop-design.md:119-146,203-217; docs/decisions.md:1246-1252; scripts/wf-loop.sh:14-22 | Add a decision addendum to loop-design.md: E-004 approved option B (not the stdin-`yes` mechanism §4/§8 still present as "the design"), the E-005 guard exception, and the F-1 gap, so the named evidence matches the shipped code. |
| F-4 | NOTE | FIX-DOC | .claude/commands/keep-continuing.md:23 | Document that `kill <pid>` stops only the loop: an in-flight claude session (child of `timeout`) keeps running to completion; or switch to a process-group kill (`kill -- -<pid>`, setsid makes the loop the group leader). |
| F-5 | NOTE | FIX-DOC | scripts/wf-loop.sh:254-265; docs/recon/loop-design.md:154-167 | Document the ordering: a review-exhausted task (cycles ≥ max, still in-review/changes-requested) stops the loop only when no other ready work or due review exists; unrelated ready work proceeds first. Consistent with the card's stop list (exhausted reviews are not one of its stop conditions) but absent from design §5's stop table. |

**F-1 (MAJOR, DECIDE) — pre-reviews of ready tasks are unachievable under the frozen
kit.** The card (S3: "a pre-review of a ready task waiting at a gate"), the approved
design (§3 step 4, §6: "Pre-review … runs before the task's heavy work; the loop
offers it as a due review when the task is ready but gated") and the loop's `pre`
branch (helper line 229, decision 262-263) all promise a pre-review of a `ready`
`pre+post` task. But `cmd_review_open` accepts only `done`/`changes-requested`
(`_wf.py:1891-1892`: "review-open needs done"), and `TRANSITIONS["ready"]`
(`_wf.py:105`) contains no review state — so even skipping review-open, a verdict
could not be recorded. Every `/review T-xxx` the loop launches for a ready task
ends in a kit refusal → non-zero exit or no-progress → safe stop. The feature is
dead on arrival, and **T-007 (ready, pre+post, exclusive-machine) is the next task
in the plan** — the same refusal hits a human-run `/review T-007` (review.md steps
8+10), so this is a plan/kit contradiction the loop inherited, not a loop coding
error. The executor's own recon documents the precondition (loop-states.md:52)
but never connects it to the pre-review promise; progress-log open issue (4)
analyses only the nothing-blocked path and asserts "two no-op /continue attempts"
as fact — if the session claims+starts before honouring continue.md:52-53 (the
command's step order), the task lands in-progress and the loop stops after **one**
attempt with "not finished cleanly — resume manually". Both paths are safe; the
analysis is incomplete. Per shared rule 7 this assumption mismatch should have
been escalated. Options for the planning chat (cheapest first):
(a) interim, no code change: FIX-DOC the gap in the design/recon/progress-log and
rule how T-007's pre-review is performed and recorded under the frozen kit (e.g.
an interactively-approved deviation); (b) schedule a kit change with/after T-018
(post-T-008 freeze): allow review-open for ready pre+post tasks with a proper
transition path + regression test; (c) revise the loop's pre branch to stop
explicitly ("pre-review due; kit cannot open a review on a ready task") instead of
launching a doomed session — a deviation from the E-004-approved ordering, so it
needs approval. F-1 cannot be resolved inline (DECIDE): escalate.

**F-2 (MINOR, FIX-DOC) — D8 privacy violation in a committed file.**
loop-states.md:372 records the claude CLI path as a home path containing the
account name. `git grep` shows this is the **only** committed file containing it;
`git log -S` confirms the history matches T-001's recorded scan (WP0 `26faadd`
occurrence, removed in WP3 `dfcd7d9`) **plus the new introduction in T-017's
`3f41e18`**. D8: "No committed file may contain the account name; refer to it as
`<account-name>`"; T-001.md:131 states the convention explicitly. The repo is
private until T-015/T-016, so nothing was exposed, but the step plan's scrub
checklist names `data/` and `reports/` — `docs/recon/` may not be swept by T-013,
so fix at source. No history rewrite (D8 forbids; the name matches the already-
public author name, the accepted WP0 rationale).

**F-3 (MINOR, FIX-DOC).** loop-design.md is named acceptance evidence, yet §4
still presents the stdin-`yes` lane answer (option A) as the mechanism and §8
still lists it as an open question recommending A. E-004 chose B; the script
header and progress log record this correctly, but a reader of the design alone
gets the wrong mechanism. A short addendum fixes it.

**F-4, F-5 (NOTE).** Small doc gaps, no behaviour change required; both failure
modes are safe (orphan session still obeys the kit protocol; exhausted-review
ordering only affects which work runs first).

## Task verdict

changes-requested

Rationale: all 7 mechanical items PASS on re-run and A8's behavioural clauses hold
as implemented; the code faithfully implements the E-004/E-005 decisions. But F-1
is a MAJOR mismatch between the named evidence's claims and re-derived kit
behaviour, on a card-required capability, with immediate impact on T-007 — and
DECIDE findings must be escalated, not resolved inline. F-2 is a standing-rule
(D8) violation in a committed file. The address cycle is cheap: escalate F-1,
apply the F-2/F-3 doc fixes (+ optional F-4/F-5), re-run accept to refresh the
evidence hash.

## What I did not verify

- **Real headless behaviour of `/continue`, `/lane N`, `/review`,
  `/address-review`** — forbidden in T-017 (S2, E-004 change 2); all session
  behaviour is verified against fake claude only. E-004 change 4's supervised
  first real run (~1 hour, awake) is still pending and is the real verification.
- The full 2674-line read of `_wf.py` claimed by the recon: I spot-checked ~20
  cited ranges plus the guard, review-open/verdict, done, accept-record, status,
  effective_tasks, recompute_ready and TRANSITIONS code. Not re-derived: §5.2
  lock line ranges (739-749, 758-773, 776-798), cmd_claim internals (1381-1451),
  the §2.2 live exit-code table beyond what my own commands exercised.
- S2's exit code 0 itself: the /tmp captures show complete, consistent output and
  the recorded stderr, but no exit-code record; I did not re-run headless /status.
- The executor's attestation "never ran the loop against real state": supported
  by the test design, the absence of any /tmp/wf-loop-<stamp>.log, and the
  fixture-only dry-run tests — not provable after the fact. (I ran `--dry-run`
  against the real state myself, read-only, as reviewer verification.)
- keep-continuing.md's detached launch (setsid/nohup) was not executed — it would
  start a real loop. The `$!` pid semantics under setsid were reasoned about, not
  tested.
- T-013's actual scrub scope for docs/recon/ (inferred from the step plan's
  checklist; its card was not read).
- The concurrent T-006 session's work (out of scope; noted only as context — it
  committed during this review and swept the run-2 acceptance record into its
  kit-state commit; PROGRESS.md churn in the tree is expected kit rendering).
- No heavy items: T-017 is `light`; nothing DEFERRED. No GPU/exclusive-machine
  task was in progress during this review.
