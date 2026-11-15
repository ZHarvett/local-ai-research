# T-022 — Kit fixes: lane merge status and state riders

Recon for card T-022 (lane 2). Start marker: `docs/recon/T-022-start.txt`
(HEAD `8ca56dee8cc9c0a2c8cffc57cf7e0682ccae2d70`, the lane-2 tip at claim time).
All line numbers below were re-read in the worktree at that HEAD and corrected
where the card's approximation was off. Live-state evidence was read read-only
from the main checkout; no live state was written by this task.

## 1. The five problems, with file:line evidence

### (1) The lane fold overwrites advanced main statuses — `scripts/_wf.py:2318`

`cmd_merge_lanes` (`scripts/_wf.py:2289`) folds every lane-mirror task into the
main state with

```python
merged = {**base, **task}          # scripts/_wf.py:2318
```

so every lane field — including `status` — wins over main. A lane mirror keeps
the status the task had when it last mutated *in the lane*; a review run from
main (legal: `mutate`'s foreign-lane check, `scripts/_wf.py:542-544`, only bites
inside a worktree) advances the main state but never the mirror. The next
`merge-lanes` then folds the stale mirror status back over the advanced one.

Observed on 15 November (live `.workflow/state.json` and git history):

- `review-verdict` seq 204, T-018, detail `accepted (cycle 1, 3 findings)`,
  ts 2026-11-14T17:35:27Z; `review-verdict` seq 210, T-005, detail
  `accepted (cycle 2, 5 findings)`, ts 2026-11-14T19:49:43Z.
- Commit `c4becdd` ("workflow: bookkeeping (merge lane 2, T-011 done)",
  2026-11-15 12:27:32 +0200) is the regression: at `c4becdd~1` the main state
  has T-005 **accepted** and T-018 **accepted**; at `c4becdd` both are **done**.
  Its `lane-merged` event is seq 291 (ts 2026-11-15T10:27:08Z). Later lane-2
  merges (seq 331, 373) re-folded the same stale statuses.
- Current main state: T-005 `done`, T-018 `done` — regressed, while their
  review-verdict events still say accepted.

The card's "about line 2316" is the fold loop's `for` line; the dict fold itself
is line 2318.

### (2) No command can restore a regressed status

`TRANSITIONS["done"]` (`scripts/_wf.py:115`) is
`{in-review, blocked-decision, superseded, cancelled}` — `done -> accepted` is
not a legal transition, and no subcommand offers a repair path (the argparse
table, `scripts/_wf.py:2560-2700`, has no `restore-status`). `accepted` is
terminal (`scripts/_wf.py:130`), so once the fold regressed T-005/T-018 to
`done`, the only kit routes were a fresh review cycle or hand-editing state
(forbidden). Card S3 adds the guarded repair command.

### (3) The review-verdict parser misses a parenthetical — `scripts/_wf.py:1917`

`parse_review_report` (`scripts/_wf.py:1913`) reads the report's verdict line:

```python
m = re.search(r"^## Task verdict\s*\n+\s*(\S+)\s*$", text, re.M)   # line 1917
```

`(\S+)\s*$` accepts a single bare token only. A verdict line such as
`accepted (cycle 1, 3 findings)` — the same shape the kit itself writes into
event details (`scripts/_wf.py:1952`) — fails the match, `verdict` stays `""`,
and `cmd_review_verdict` dies on the report/argument mismatch
(`scripts/_wf.py:1937-1938`). T-018 review F-3
(`reviews/T-018/r1-REVIEW_REPORT.md:29`) cites pre-fix line 1918; in this
worktree the regex is line 1917 and the `if m:` is 1918.

### (4) `ensure_lane_worktree` never refreshes a stale worktree — `scripts/_wf.py:1458-1471`

```python
if worktree.is_dir():
    return worktree            # lines 1463-1464: existing worktree, no refresh
...
if branch in branches:
    _git(repo, "worktree", "add", str(worktree), branch)   # 1467-1468: old branch tip
```

An existing worktree is returned as-is, and a recreated worktree reuses the old
`lane-N` branch tip without merging main. Documented consequence:
`docs/recon/T-018-kit-repair.md` §5 (lines 128-149) — the T-018 claim recreated
the lane-2 worktree from the T-005-era branch tip `4bc967c`, and the session had
to merge main in by hand (merge `540c133`). T-018 review F-3
(`reviews/T-018/r1-REVIEW_REPORT.md:29`) confirms the gap at pre-fix lines
1454-1467; in this worktree the function is 1458-1471.

### (5) `recompute_ready` promotes lane-owned placeholders — `scripts/_wf.py:450-474`

The promotion loop (`scripts/_wf.py:466-470`) turns every `todo` task in
`owner` whose dependencies are satisfied into `ready`, with no check for lane
ownership. When the owner is the main state (`owner_lane is None` — callers at
`scripts/_wf.py:1180, 1263, 2325, 2484`), the `todo` placeholders that
`cmd_claim` leaves for lane-owned tasks (`scripts/_wf.py:1444-1451`) get
promoted to `ready` in the main state while the lane mirror still owns the
task. The guard then fails with "task T-NNN is in the main state as ready AND
in lane N". E-005 (`docs/decisions.md:1236-1242`, Reason at 1240, Rule 2 at
1242) diagnosed exactly this and scheduled the fix: "recompute_ready leaves
tasks owned by a lane mirror alone, with a regression test for concurrent
lanes". The issued T-018 card did not include it (its F-3 routing note); T-022
S4 does.

## 2. Fix design notes (S2-S4)

- **S2 fold fix.** Keep main's status when it is one of `accepted`,
  `in-review`, `changes-requested`, `superseded`, `cancelled` (the card's five);
  all other lane fields fold as before. These are exactly the statuses a lane
  mirror can be stale against: terminal (`accepted`, `superseded`, `cancelled`)
  or review-flow statuses that only main advances.
- **S3 restore-status.** `wf.sh restore-status T-NNN --to accepted --verdict-seq N`.
  Guards, in order: `--to` must be `accepted`; the task must exist and be
  `done`; the event log must hold a `review-verdict` event for that task with
  that seq whose detail starts with `accepted`; no `review-opened` event for
  the task may be later than that verdict. "Later" uses the kit's own canonical
  event order `(ts, seq)` (`all_events`, `scripts/_wf.py:415-422`) — the merged
  log contains duplicate lane events (each `merge-lanes` re-appends the whole
  mirror event list, `scripts/_wf.py:2322`) and lane/main seq spaces collide,
  so seq alone is not a safe ordering. The actual event name is
  `review-opened` (`scripts/_wf.py:1906`), not "review-open".
  The command writes the status directly (not through `transition()`/`mutate`):
  `done -> accepted` is deliberately outside `TRANSITIONS` — this is the
  card-specified repair path for a bug-regressed status, guarded by verdict
  evidence, and it changes no existing transition. It appends a
  `status-restored` event naming old status, new status and the verdict seq,
  and keeps `mutate`'s foreign-lane guard convention (`scripts/_wf.py:542-544`)
  so a worktree session cannot restore another lane's task.
- **S4 (3) parser.** Allow one optional trailing parenthetical after the
  verdict token in the line-1917 regex; anything else after the token still
  fails the match. One line.
- **S4 (4) worktree refresh.** When the worktree already exists, merge `main`
  into it if it is behind (`rev-list --count HEAD..main` > 0), reusing the
  merge/abort pattern of `cmd_merge_lanes` (`scripts/_wf.py:2306-2314`); on
  conflict, abort and leave the worktree as-is (the session can still merge by
  hand, as T-018 did). A dirty worktree is no obstacle: git refuses a merge
  only if it would overwrite locally modified files, and any failure aborts
  cleanly. This automates exactly the manual step documented in T-018 recon §5.
- **S4 (5) recompute_ready.** When the owner is the main state, skip any task
  that a lane mirror owns (mirrors are the ownership authority, cf.
  `find_task`, `scripts/_wf.py:484-495`). Lane-owned owners (`owner_lane` set)
  are unchanged: a lane promoting its own todo tasks is correct.

## 3. Deferrals (S4)

None. All three S4 fixes were applied, each well under 50 changed lines:
(3) parser 2 lines, (4) worktree refresh 16 lines, (5) recompute_ready 10 lines.
Total production diff (S2+S3+S4): `scripts/_wf.py` 91 insertions, 9 deletions;
`scripts/wf.sh` unchanged (it is a thin dispatcher; `restore-status` is
registered in `_wf.py`'s argparse). Under the card's ~200-line escalation
threshold; the new test file is additional, as the card mandates tests for
every fix (the T-018 precedent: its test file was 277 lines).

Every fix was red/green verified: with the fix reverted, its new tests fail
(S2: 6 of 7; S4: 5 of 10, the other 5 are controls that must pass both ways).

## 4. S6 — runbook figure check

Finding confirmed and fixed: `docs/runbook-stage3.md:146` (Stage 3, 64K row)
said `804 + 403 + 370 = 1,578 s`; the sum of the row's own addends is 1,577
(`python3 -c "print(804+403+370)"` → 1577). T-019 review r1 F-3
(`reviews/T-019/r1-REVIEW_REPORT.md:86`) flagged exactly this, and r2
(`reviews/T-019/r2-REVIEW_REPORT.md:113`) verified the addends against the
source data ("804 + 403 + 370 = 1,577 s / 26 / 29 / 44 min. All match the
doc."). The Stage 4 row (line 156) already used the correct 1,577 with the same
addends. Changed that one number only (1,578 → 1,577 on line 146), per the card.

Observation (not changed, per the card's "nothing else"): line 149 still reads
"1,083 + 1,578 + 2,771 = 5,432 s = 90 min"; with the corrected 64K figure the
grand total would be 5,431 s. The 1 s difference does not change the 90 min
estimate. Left for a future docs card.

## 5. S7 — review-note application check

(to be filled in)