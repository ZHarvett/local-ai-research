# T-018 recon — the kit cannot leave blocked-decision after a review verdict

<!-- sources: scripts/_wf.py, docs/WORKFLOW.md, .workflow/state.json, reviews/T-021/r1-REVIEW_REPORT.md, docs/progress-log.md -->

Scope: the four defects named in card T-018, re-read in the current `scripts/_wf.py`
(line numbers verified this session; the card's approximations are corrected below).
All `.workflow/state.json` facts were read from the main checkout's state (the shared
runtime state every session reads); no live state was modified by this task.

## 1. What happened to T-021 (the observed failure)

Event timeline, from `.workflow/state.json` `events` (main checkout):

```text
seq 175  2026-11-14T15:13:42Z  done          T-021  accept run at 2026-11-14T15:12:32Z
seq 176  2026-11-14T15:29:42Z  review-opened T-021  cycle 1
seq 177  2026-11-14T15:29:42Z  review-verdict T-021  blocked-decision (cycle 1, 6 findings)
seq 178  2026-11-14T15:58:43Z  plan-added    T-018  new card in amended plan
```

The cycle-1 review (`reviews/T-021/r1-REVIEW_REPORT.md`, "## Task verdict:
blocked-decision") raised F-2 as a DECIDE finding (R7 scope). The verdict moved T-021
`in-review -> blocked-decision`, and the task record now carries **no `blocked_from`
and no `blocked_reason` field at all**. No escalation was ever filed for T-021
(`escalations` holds E-001…E-008, all decided, none for T-021). From that moment every
kit path out of `blocked-decision` fails (section 3). The planning chat created T-018
(plan v1.4, commit `22e20de`) to repair the kit.

## 2. The four defects, with file:line evidence

All references are to `scripts/_wf.py` at the pre-fix tree (commit `22e20de`, identical
in this worktree after the setup merge, section 5).

**(a) `cmd_review_verdict` records no `blocked_from` — lines 1924-1948, the `mutate`
call at 1939-1945** (card said "about 1939-1944"; the call's closing paren is line 1945).
It calls `mutate(repo, tid, verdict, event="review-verdict", ...)` with no `extra`
dict, so a `blocked-decision` verdict sets only `status`. Compare `cmd_block`
(lines 2002-2014), which correctly passes
`{"blocked_from": task["status"], "blocked_reason": args.reason}` at line 2010.
This is the root cause: T-021 entered `blocked-decision` with no return status.

**(b) `cmd_escalate` overwrites `blocked_from` with the current status — line 2095**
(inside the `mutate` at 2090-2100, function 2062-2102). It always passes
`"blocked_from": task["status"]`. When the task is *already* `blocked-decision`
(e.g. escalating the review's DECIDE finding after a blocked-decision verdict),
`blocked_from` becomes `"blocked-decision"` — a status that is not a legal transition
out of `blocked-decision`, so it can never be restored to.

**(c) `cmd_unblock` falls back to `todo`, which TRANSITIONS forbids — lines 2017-2032,
the fallback at 2021-2023** (card said "about 2017-2033"; the function ends at 2032):

```python
restore = task.get("blocked_from", "todo")
if restore not in TRANSITIONS["blocked-decision"]:
    restore = "todo"
```

`TRANSITIONS["blocked-decision"]` (lines 131-141) is
`{ready, claimed, in-progress, awaiting-gate, done, in-review, changes-requested,
superseded, cancelled}` — it contains **neither `todo` nor `accepted`**. So when
`blocked_from` is missing (defect a) the default `"todo"` fails the membership test,
the fallback assigns `"todo"` *again*, and `transition()` (lines 512-524) dies with
`invalid transition ... blocked-decision -> todo`. When `blocked_from` is
`"blocked-decision"` (defect b) the same fallback fires. The fallback cannot produce a
legal target in either case; `unblock` without `--to` is unusable for these tasks.

**(d) `cmd_decision` writes before it unblocks — lines 2117-2126** (card's range is
exact; function 2105-2128). Order of operations:

```text
2117-2120  append the DECISION block to docs/decisions.md
2121-2123  mark the escalation decided and save state
2124-2126  cmd_unblock(repo, Namespace(task=tid))   <- can die (defect c)
```

If the unblock dies, the decision is already recorded and the escalation already
`decided`, while the task stays `blocked-decision`. Re-running `wf-decision.sh` then
dies at lines 2112-2113 (`escalation E-NNN is already decided`), so the reply cannot be
re-recorded either. The only escape left is hand-editing `.workflow/` state, which the
protocol forbids.

## 3. Why T-021 is stuck — every path fails

- `wf.sh unblock T-021` → defect (c): no `blocked_from`, fallback `todo` is illegal → die.
- `wf-escalate.sh --task T-021 ...` (to file the F-2 DECIDE finding) → defect (b):
  `blocked_from := "blocked-decision"`; any later `unblock` or `wf-decision.sh` still
  dies via (c).
- `wf-decision.sh E-NNN --reply-file ...` → defect (d): `docs/decisions.md` grows a
  DECISION block and the escalation is marked decided, then the unblock dies; the task
  stays blocked and the decision cannot be re-recorded.

## 4. The fix (card S2, four changes, all in `scripts/_wf.py`)

The shell wrappers need no change: `scripts/wf.sh` is a thin `exec python3 _wf.py "$@"`
dispatcher and `wf-decision.sh` / `wf-escalate.sh` forward to it, so `--to` passes
through untouched.

1. **`wf.sh unblock T-NNN --to STATUS`** (new optional flag). Accepted targets are the
   card's three review-flow return statuses — `done`, `in-review`, `changes-requested` —
   each checked against `TRANSITIONS["blocked-decision"]` (all three are members).
   Anything else is refused before any mutation. The `--to` path writes an `unblocked`
   event whose detail names the old and the new status. **Without `--to` the command is
   byte-for-byte the old behaviour**, including the broken fallback — that is exactly
   the case `--to` exists for.
   *Interpretation note:* `TRANSITIONS["blocked-decision"]` also contains `ready`,
   `claimed`, `in-progress`, `awaiting-gate`, `superseded`, `cancelled`, but card S3
   explicitly requires `--to ready` to be **refused**, so the allow-list is the three
   statuses the card's S2 parenthetical names; the TRANSITIONS membership test is the
   card's "legal transition in the existing TRANSITIONS table" condition applied on top.
2. **`cmd_review_verdict` records `blocked_from` for a blocked-decision verdict**:
   `blocked_from = "changes-requested"` — the status the review protocol returns to
   (`/address-review` works a `changes-requested` task, `docs/WORKFLOW.md` §"Addressing
   a review"; `cmd_review_open` accepts `done` or `changes-requested`, line 1892).
3. **`cmd_escalate` keeps an existing `blocked_from`** when the task is already
   `blocked-decision`, instead of overwriting it with `"blocked-decision"`. If the
   existing value is missing/None it stays missing/None (the `--to` flag is the escape
   hatch for that case); `blocked_reason` still names the newest escalation.
4. **`cmd_decision` computes the unblock target before writing anything**, using the
   same expression `cmd_unblock` uses (`task.get("blocked_from", "todo")` plus the
   TRANSITIONS membership test). If the task exists and cannot be unblocked — not
   `blocked-decision`, or no legal restore target — it dies **before** appending to
   `docs/decisions.md` or marking the escalation decided. The refusal message names the
   `wf.sh unblock T-NNN --to STATUS` remedy.

Estimated size: well under the card's ~80-changed-line ceiling (section 6 of the final
report carries the measured diffstat).

## 5. Session setup — the lane-2 worktree was stale (git mechanics only)

The claim recreated `.workflow/worktrees/lane-2` from the old `lane-2` branch tip
`4bc967c` (T-005 era): the earlier `merge-lanes 2` (main merge `5bd5070`) removed the
worktree but kept the branch, and `ensure_lane_worktree` (`scripts/_wf.py:1454-1467`)
reuses an existing branch without refreshing it. Card acceptance 4 requires the
`plan: v1.4` commit (`22e20de`) in this branch's history, and S4 appends to
`docs/decisions.md` / `docs/progress-log.md`, whose worktree copies were stale. Setup:

```text
64b956d  workflow: bookkeeping (T-018 claim/start, lane 2)   <- kit-written lane file, committed as-is
540c133  Merge branch 'main' into lane-2                     <- brings the branch to 22e20de
```

The merge's only conflict was modify/delete on `.workflow/lanes/2.json` (main folded and
deleted it at the earlier merge-lanes). It was resolved by **keeping the kit-written
file unchanged**; before and after, the file is byte-identical to the runtime mirror
`.git/workflow/lanes/2.json` (diff verified). No state content was edited by hand; all
status changes go through `wf-*.sh`. `wf-guard.sh` passes before and after; T-021 and
every other task's state are untouched. The `ensure_lane_worktree` refresh gap is
flagged for the planning chat (section 7), not fixed here — outside the card's four
changes.

## 6. T-021 recovery path after this fix (suggestion only — not executed here)

T-021 is lane 1's task; this session does not touch it. The shape the fix enables:

1. `wf.sh unblock T-021 --to changes-requested` — works with no `blocked_from`
   (test scenario 1 in `tests/test_wf_unblock.py` is exactly this shape).
2. `/address-review T-021`: dispositions for F-1/F-3/F-4/F-5 (doc fixes), F-2 DECIDE →
   `wf-escalate.sh --task T-021 --type review-disagreement`. From `changes-requested`
   the escalation records `blocked_from = "changes-requested"`; fix 3 keeps it across
   any re-escalation.
3. Planning chat rules on F-2 → `wf-decision.sh E-NNN --reply-file ...`: the pre-check
   now passes, the decision is recorded and the task unblocks to `changes-requested`.
4. Apply the ruling + doc fixes, re-open review (cycle 2 of 2).

Order matters: escalating *before* step 1 would leave `blocked_from` missing (fix 3
keeps it missing), and `wf-decision.sh` would then correctly refuse until step 1 runs.

## 7. Flagged, not fixed (outside the card's four changes)

- `ensure_lane_worktree` (lines 1454-1467) does not refresh a recreated lane worktree
  to main HEAD — the cause of section 5's setup merge. Candidate for a future kit card.
- `parse_review_report`'s findings regex (line 1918) does not match an action column
  carrying a parenthetical (T-019 F-3, `wf.sh review-disposition` refused
  "FIX-DOC (not by T-019)"). T-019's progress log says the planning chat routed this
  "into the T-018 amend after T-008", but the v1.4 card as issued lists only the four
  changes above — flagging the discrepancy for the planning chat; not fixed here.

Result: recon complete, four defects confirmed at the corrected lines above.