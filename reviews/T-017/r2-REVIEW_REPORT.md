# Review T-017 (cycle 2)

## Model

qwen4-max-preview (the config records a single model for executor and reviewer;
adversarial re-derivation, read-only).

## Why this cycle exists

Cycle 1 (`reviews/T-017/r1-REVIEW_REPORT.md`) returned **changes-requested**: F-1
(MAJOR, DECIDE — pre-reviews of `ready` `pre+post` tasks are unachievable under the
frozen kit), F-2 (MINOR, FIX-DOC — D8 account-name home path in a committed file),
F-3 (MINOR, FIX-DOC — design still showed the superseded stdin lane mechanism),
F-4 / F-5 (NOTE, FIX-DOC — kill semantics; review-exhausted ordering). Since then:

- F-2–F-5 doc fixes committed in `bc8e0c3`; acceptance re-run (run 3, 0 failures).
- F-1 escalated as **E-006** (`1ba3bf9`); the planning chat decided **option A**
  (2026-11-13T18:21:00Z, `docs/decisions.md:1256-1264`): pre-reviews are not performed
  under the frozen kit, the loop's `pre` branch stays as inert code, no code change,
  and T-017 "may be accepted and finished". The E-006 rule-4 F-2 follow-up (introducing
  + fix commit hashes) was recorded under the decision (`8e441c9`).
- Cycle 2 was opened by the address session (`8e441c9`); `review_cycles[T-017]=2`,
  status `in-review`. This report records the verdict for that open cycle (review-open
  is not re-run: it requires `done`/`changes-requested` and would exceed `max_review_cycles=2`).

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-017` myself (**run 5, 0 failures**, at HEAD
`56e1c39`). Evidence hashes re-verified and identical to run 4: `loop-states.md`
`09e5a378…`, `loop-design.md` `99a4ad87…`, `wf-loop.sh` `a16ed003…` (the script is
byte-for-byte unchanged since the S4 build — consistent with E-006 option A "no code
change"). The working tree carries uncommitted **T-019** cycle-2 review artifacts
(`REVIEW_REPORT.md`, `reviews/T-019/r2`, `.workflow/`, `PROGRESS.md`); none is under
`src/ configs/ scripts/ pyproject.toml uv.lock`, so A5 (a committed `HEAD` diff) is
unaffected, and T-017's own files are untouched since `bc8e0c3`.

| item | verdict | note |
|---|---|---|
| A1 | PASS | `shellcheck scripts/wf-loop.sh` re-run, exit 0, no output. |
| A2 | PASS | `uv run pytest -q tests/test_wf_loop.py` re-run: **37 passed in 4.03s** (also re-run `-v`: every stop condition #1–#10, the E-005 guard exception, lane ordering, the review flow and dry-run are named tests). Fixtures are isolated: `make_fixture` builds a temp git repo + fixture state + a **fake claude** (`WF_LOOP_CLAUDE_BIN`→fake, `WF_LOOP_REPO`→temp repo, lock/log in `tmp_path`); `from conftest import REPO` only locates the script. No test invokes the real CLI or this repo's state. |
| A3 | PASS | `bash scripts/wf-loop.sh --help` re-run, exit 0; usage lists all stop conditions + env knobs + the supervised-first-run note. |
| A4 | PASS | `uv run ruff check` + `ruff format --check` on the test file re-run, exit 0. |
| A5 | PASS | Re-ran the `--diff-filter=MD` check from start `49f92c2`; empty. `git diff --stat 49f92c2..HEAD` over the task's files shows only **Added** files (script, command, tests, two recon notes, start-HEAD file) + `M docs/progress-log.md` — all within `files_write`. No existing file under src/configs/scripts/pyproject/uv.lock touched. |
| A6 | PASS | `! grep -q 'dangerously-skip-permissions' scripts/wf-loop.sh` re-run, exit 0. Extra args come only from `WF_LOOP_CLAUDE_ARGS` (`wf-loop.sh:402`, `read -r -a`, no eval of args); covered by `test_claude_args_come_only_from_env`. |
| A7 | PASS | `.claude/commands/keep-continuing.md` exists; `sha256` `be0f29d3…` matches the accept-time record (runs 3–5). |
| A8 | PASS | Judged clause-by-clause against the code and the 37 re-run tests — see below. |

**A8 clause-by-clause (re-derived):**
- *Never passes a gate:* no `gate-release` path exists; `awaiting-gate` → stop
  (`wf-loop.sh:266-269`), and new task work requires `not (gates or open_esc or blocked)`
  (`:254`). `test_stop_2_open_gate`.
- *Never works a task with an open escalation:* an escalated task is `blocked-decision`,
  excluded from every review list (`:226-230`) and blocking new work (`:254`); an open
  escalation stops the loop (`:270-272`). `test_stop_3_open_escalation`,
  `test_stop_4_blocked_decision`, `test_never_reviews_a_blocked_task`.
- *Never starts a second task after the deadline:* `now >= DEADLINE` checked before every
  launch (`:499-501`); a running session is bounded by `timeout`. `test_stop_1_deadline_before_any_session`.
- *Runs lanes in order:* `ready` sorted by `(lane, id)` (`:217-220`); several lanes →
  lowest-numbered `/lane N`, one → `/continue` (E-004 option B, `:255-261`).
  `test_single_ready_lane_uses_continue`, `test_multi_lane_uses_lowest_lane_then_continue`.
- *Runs only reviews that are due:* status- and cycle-bounded lists (`:226-230`), never a
  `blocked-decision` task, never past `max_review_cycles`. `test_post_review_then_idle`,
  `test_in_flight_review_finished`, `test_address_review_flow`, `test_review_cycles_exhausted_stops`,
  `test_pre_review_while_gated`.
- *Stops on the first human-needed state:* `finish()` prints reason + task id (`:90-99`) on
  gate/escalation/blocked/acceptance-fail/no-progress/non-zero/usage-limit/dirty/timeout/guard-fail;
  new blockers appearing mid-session stop (`:548-554`). `test_final_message_names_reason_and_task` + all stop tests.

Live read-only `--dry-run` against the real state printed
`next action: continue task=T-007 lane=1 prompt=/continue` — with T-017 `in-review` at
cycle 2 (exhausted) and T-007 `ready`, the loop correctly takes ready work first (F-5
ordering) rather than stopping on the exhausted review; no gate/escalation/blocked is open
(E-006/E-007 both `decided`). No `/tmp/wf-loop-<stamp>.log` exists — consistent with the
attestation that the loop was never run against real state (dry-run takes no lock, starts no
session, cleans its `/tmp` scratch dir).

## Verification of the cycle-1 findings and E-006 application

- **F-1 (MAJOR → resolved by E-006 option A).** Re-derived the kit precondition:
  `cmd_review_open` accepts only `done`/`changes-requested` (`_wf.py:1892-1893`) and
  `TRANSITIONS["ready"]` has no review state — so a pre-review of a `ready` task cannot
  complete. The decision (`docs/decisions.md:1259-1262`) rules pre-reviews not performed,
  the `pre` branch kept inert. Verified the branch is still present and unchanged
  (`wf-loop.sh:229,262-263`), no `pre+post` task remains in the plan (T-007 is `post` since
  v1.2), and the script hash is unchanged → option A's "no code change" honoured. The
  design carries the gap note (§11.3). **Resolved.** (Doc-freshness nit → F-1 below.)
- **F-2 (privacy → fixed, verified).** `git grep -l -F "<account-name>"` over **HEAD** and
  the **working tree** returns nothing (filenames-only check; the name was never printed).
  `loop-states.md:372` now reads `~/.local/bin/claude (home path scrubbed per D8)`. Pickaxe
  `git log --format=%h -S"/home/<account-name>" -- docs/recon/loop-states.md` returns exactly
  `3f41e18` (introduce) and `bc8e0c3` (remove); both commits exist. This matches the E-006
  rule-4 record (`docs/decisions.md:1264`) verbatim. **Resolved.**
- **F-3 (design addendum → present).** `loop-design.md` §11.1 records E-004 option B
  (supersedes §4's stdin mechanism, which now carries a "superseded" note at `:134-137`);
  §8 question 1 marked resolved; §11.2 records the E-005 guard exception. **Resolved.**
- **F-4 (kill semantics → documented).** `keep-continuing.md:23-29` states `kill <pid>`
  stops only the loop; an in-flight claude session (child of `timeout`) runs to completion
  and still obeys the kit. **Resolved.**
- **F-5 (review-exhausted ordering → documented).** `loop-design.md:176-183` (§5) records
  that an exhausted review stops only after ready work / due reviews; matches the helper
  priority (`wf-loop.sh:248-287`) and the live dry-run. **Resolved.**

Evidence integrity: all three evidence hashes re-verified; the acceptance records are
kit-generated (run 5 appended by my re-run); the recon docs are legitimate authored
evidence, not hand-written forgeries — the privacy fix and pickaxe hashes were independently
re-derived, not taken on trust. My re-run agrees with the executor's runs 1–4 (0 failures,
identical hashes) — no executor/reviewer disagreement.

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | NOTE | FIX-DOC | docs/recon/loop-design.md:111-112,206-208,308-323; docs/decisions.md:1256-1264 | Refresh §11.3 (and the §3 step 4 / §6 gap notes) to record that E-006 was **decided option A** — they still say "open" / "pending the planning chat's decision" / "await the planning chat's ruling". The authoritative ruling is in docs/decisions.md; this is a freshness nit in named evidence. Cheapest: a short addendum line, can ride with T-010's doc pass. Non-blocking (E-006 rule 3 authorises acceptance; the brief called softening §3/§6 optional). |
| F-2 | NOTE | FIX-CODE | scripts/wf-loop.sh:419,24-27; .claude/commands/review.md (no commit step); .gitignore; tests/test_wf_loop.py:321-336 | `dirty_tree()` excludes only `PROGRESS.md`/`.workflow/`. A `/review` session records a verdict but does **not** commit (review.md has no commit step; `REVIEW_REPORT.md`/`reviews/` are not gitignored), so it leaves `M REVIEW_REPORT.md` + `?? reviews/T-xxx/rN` — verified live: the filter flags exactly those. The loop would therefore stop "unexpected dirty tree" after a cleanly-finished review. **Safe** (stops, never proceeds dangerously) and a documented conservative choice (header :24-27); code frozen per E-006. Recommend widening the exclusion to review artifacts, or having review sessions commit — decide at the supervised first run (E-004 change 4) / T-018. No test covers post-review churn (`test_stop_8_kit_rendered_churn_is_expected` uses PROGRESS/.workflow only). Non-blocking for T-017. |

**F-1 (NOTE, FIX-DOC).** The design is named acceptance evidence, and §11.3 still frames
F-1/E-006 as awaiting a ruling that has already been made (option A). A reader of the design
alone would think the decision is pending. The decision itself is correctly recorded in
`docs/decisions.md`, the code matches option A, and E-006 explicitly authorises acceptance,
so this does not block — but the design should be refreshed for accuracy (the same principle
as cycle-1 F-3).

**F-2 (NOTE, FIX-CODE, deferred).** Re-derivable operational interaction, not a coding error
in the reviewed behaviour: the dirty-tree exclusion list omits the kit's review artifacts.
It is a *safe* stop and the design deliberately chose a conservative check, so it is recorded
as an observation for the supervised first run / T-018 rather than a defect requiring a fix
cycle (cycles are exhausted and E-006 froze the code). It does, however, mean the unattended
loop cannot currently progress past a post-review without a human committing the review
artifacts — worth resolving before relying on the loop unattended.

## Task verdict

accepted

Rationale: all 7 mechanical items PASS on my own re-run (run 5, 0 failures) and A8's six
behavioural clauses hold as implemented, each covered by an isolated fixture test (37
passed). Every cycle-1 finding is resolved: F-1 by the planning chat's E-006 option A
(no code change; inert `pre` branch kept; verified), F-2 by a verified privacy scrub
(no account name in HEAD or working tree; pickaxe hashes match the rule-4 record), and
F-3/F-4/F-5 by doc fixes I re-read in place. E-006 rule 3 explicitly states T-017's code is
complete and may be accepted and finished. The two remaining items are NOTE-level (a design
freshness nit and a safe, documented dirty-tree observation routed to the supervised run /
T-018); neither is a BLOCKER or MAJOR, and neither warrants stranding the task in a third
cycle the kit cannot open. Accepted.

## What I did not verify

- **Real headless behaviour of `/continue`, `/lane N`, `/review`, `/address-review`** —
  forbidden in T-017 (S2, E-004 change 2); all session behaviour is verified against fake
  claude only. E-004 change 4's supervised first real run (~1 hour, awake) is still pending
  and is the real verification — F-2 above is exactly the kind of thing it should surface.
- **T-013's history-scan method.** The E-006 rule-4 allowlist (`3f41e18`, `bc8e0c3`) is
  correct for the prescribed `git log -S` pickaxe (re-derived, matches). I did not read
  T-013's card: if its scan greps every commit's tree rather than pickaxe, the account name
  also persists in the intermediate commits that carry `loop-states.md` unchanged, and the
  allowlist would need the full range. Out of T-017 scope; flagged for T-013.
- The full `_wf.py` read claimed by the recon: I spot-checked the review-open/verdict,
  TRANSITIONS, effective_tasks merge, accept-record and guard code plus the cited ranges.
  Not re-derived: lock line ranges, cmd_claim internals, the full live exit-code table.
- S2's headless `/status` exit code itself (the /tmp captures corroborate the output; I did
  not re-run headless /status).
- The executor's attestation "never ran the loop against real state": supported by the
  fixture-only tests, the absence of any `/tmp/wf-loop-<stamp>.log`, and my own read-only
  dry-run — not provable after the fact.
- `keep-continuing.md`'s detached launch (setsid/nohup) was not executed (it would start a
  real loop); the `$!` pid semantics under setsid were reasoned about, not tested.
- The concurrent **T-019** cycle-2 review artifacts left uncommitted in the tree (out of
  scope; noted only as context — they are T-019's, finalized in state at seq 128-130, and
  their root working copy is identical to `reviews/T-019/r2-REVIEW_REPORT.md`).
- No heavy items: T-017 is `light`; nothing DEFERRED. No GPU/exclusive-machine task was in
  progress during this review.