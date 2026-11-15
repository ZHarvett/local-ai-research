# Review T-022 — Kit fixes: lane merge status and state riders (cycle 1)

- Reviewer model: qwen4-max-preview (adversarial re-derivation; executor reasoning not seen)
- Date: 2026-11-15
- Lane: 2 (work reviewed at lane-2 tip `662a349`; executor acceptance run 1 at `cf1c7e4`)
- Guard: `wf-guard.sh` returned exactly the three E-013 false-positive lines
  (T-005, T-011, T-018 "in the main state as done AND in lane 2"); `status` shows
  each as `done`. Per planning-chat decision E-013 the guard was treated as OK and
  `merge-lanes 2` was NOT run. No other GUARD line appeared.

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-022` myself (run 2). It resolved the workdir to
the lane-2 worktree (`.workflow/worktrees/lane-2`) and ran every command there
against the new code. No GPU server running, no in-progress task, so no heavy item
needed deferral. Result: A1–A5 PASS, A6 judgement, **0 failures** — identical to the
executor's run 1, including both evidence-file SHA-256 hashes
(`docs/recon/T-022-kit-fixes.md` = `4e675e27d2ed…`, `tests/test_wf_lane_merge.py`
= `6a15fa3ed5a4…`). The accept-commit→HEAD delta (`cf1c7e4..662a349`) is only
`.workflow/acceptance/T-022.json` + `.workflow/lanes/2.json` (kit bookkeeping); the
tested code is byte-identical, so run 1 is valid for HEAD.

| Item | Check | Verdict | Evidence |
|---|---|---|---|
| A1 | `pytest -q tests/test_wf_lane_merge.py tests/test_wf_unblock.py` | PASS | run 2 exit 0; independent verbose run = **45 passed in 2.81s**; output_bytes 99 matches run 1 |
| A2 | `shellcheck scripts/wf.sh` | PASS | run 2 exit 0, 0 bytes; `wf.sh` unchanged (thin `exec python3 _wf.py "$@"` dispatcher routes `restore-status` via argparse) |
| A3 | `ruff check` + `ruff format --check` on the new test file | PASS | run 2 exit 0, 44 bytes |
| A4 | `source commands.env && eval "$CI_CMD"` | PASS | run 2 exit 0, 5604 bytes, 303.8 s (run 1: 301.7 s); full suite `uv sync --frozen && ruff check && ruff format --check && pytest -m "not gpu" && shellcheck scripts/*.sh`; recon §6 records 1103 passed, 2 deselected |
| A5 | `grep restore-status _wf.py` + both recon files non-empty | PASS | run 2 exit 0; both evidence files present, hashes match run 1 |
| A6 | manual scope/behaviour judgement | PASS | see below |

### A6 judgement (verified by inspection, not just the executor's word)

- **Only named files changed.** `git diff --name-only c6e8bda..lane-2` excluding
  kit bookkeeping (`.workflow/`) and the escalation (`escalations/E-013.md`) is
  exactly: `scripts/_wf.py`, `tests/test_wf_lane_merge.py`, `docs/runbook-stage3.md`,
  `docs/recon/T-022-start.txt`, `docs/recon/T-022-kit-fixes.md`. `scripts/wf.sh`
  unchanged (permitted). No `src/`, `configs/`, `pyproject.toml`, `uv.lock`.
- **Fold fix keeps advanced statuses.** `MAIN_WINS_STATUSES = (accepted, in-review,
  changes-requested, superseded, cancelled)` — exactly the card's five; the fold
  keeps `base["status"]` for those and folds other lane fields as before
  (`_wf.py:2387-2391`). Covered by the T-005/T-018 regression test, a 5-status
  parametrisation that also asserts a non-status lane field still folds, and a
  control that the normal `todo`→`done` lane flow is unchanged.
- **restore-status refuses everything but verified done→accepted.** Guards verified
  in code (`cmd_restore_status`): `--to` must be `accepted`; task must be `done`;
  a `review-verdict` event for that task with that exact `seq` whose detail starts
  `accepted`; no `review-opened` later than the verdict in canonical `(ts, seq)`
  order; foreign-lane guard copied from `mutate`. `seq` is an int (`append_event`
  uses `len(events)`), so the `== args.verdict_seq` int comparison is sound. Tests
  cover the accept case (incl. the `status-restored` event detail) and every refusal
  (other targets, non-done tasks, wrong seq, non-accepted verdict, another task's
  verdict, later review-opened with both larger and smaller seq, unknown task,
  missing flags, foreign lane from a worktree); each refusal asserts the state file
  is byte-unchanged. Writes status directly (done→accepted is deliberately outside
  `TRANSITIONS`, card-specified) and changes no existing transition.
- **Every deferral recorded with a reason.** Recon §3: no S4 deferrals — all three
  applied (parser 2 lines, worktree refresh 16, recompute_ready 10). Production diff
  is `scripts/_wf.py` **91 insertions / 9 deletions = 100 lines** (verified by
  `--numstat`), under the card's ~200-line escalation threshold. The threshold is
  read as production code, excluding the card-mandated test file (318 lines) and
  recon doc (242 lines); that is the only coherent reading (S5 mandates tests for
  every fix) and matches the T-018 precedent cited in the recon.
- **Live state not touched.** `git diff c6e8bda..lane-2 -- .workflow/state.json` is
  empty; main still shows T-005 `done`, T-018 `done` (the regressed statuses left for
  the driver to restore post-merge, per card S8 / E-013). The lane work wrote only
  its own lane mirror and acceptance record (normal bookkeeping). No `restore-status`
  or `merge-lanes` was run against live state by the executor.

Other fixes verified in code: S4(3) parser regex allows exactly one trailing
parenthetical and still rejects trailing junk (tested both ways); S4(4)
`ensure_lane_worktree` refreshes a stale/recreated worktree from `main` when
`rev-list --count HEAD..main > 0` and aborts cleanly on conflict (`_git` strips
output so `behind.isdigit()` is valid; `subprocess` imported; conflict test asserts
HEAD unchanged and no `MERGE_HEAD`); S4(5) `recompute_ready` skips lane-owned
placeholders when the owner is main, while a lane owner still promotes its own
(tested both). S6: 804+403+370 = **1577**, exactly one number changed on
`docs/runbook-stage3.md:146`; the Stage 4 row already used 1577.

## Findings

| ID | Severity | Action | Evidence | Finding |
|---|---|---|---|---|
| F-1 | NOTE | FIX-DOC | docs/runbook-stage3.md:149; recon §4 | The grand-total line still reads "1,083 + 1,578 + 2,771 = 5,432 s"; with the corrected 64K figure it should be 1,578→1,577 and 5,432→5,431. Card S6 mandated "that one number and nothing else", so leaving it is correct for T-022 and the executor documented it. The 1 s does not change the 90 min estimate. Route to a future docs card; no T-022 action. |
| F-2 | NOTE | FIX-DOC | recon §5; reports/baseline-report.md; scripts/_wf.py | S7's read-only check correctly lists still-unapplied review notes: T-005 r2 F-1 (0.771 attribution gap — verified: absent from the three named §8 sources, present in stage3/headline.md:123 and stage2-summary.md:29), F-2 and F-5 (optional), and T-018 r1 F-2 (cmd_decision lane-ownership pre-check; cmd_review_verdict unconditional blocked_from — a future kit card, FIX-CODE). These are out of T-022's scope and were only listed, as the card requires. Tracked for future cards; no T-022 action. |

No BLOCKER, MAJOR or MINOR findings. The executor's report and my re-run agree on
every mechanical item and on the evidence hashes; no mismatch found.

## Task verdict

accepted

## What I did not verify

- I did not independently re-run the executor's red/green revert experiment
  (reverting each fix and confirming its tests fail). I verified the green side
  (45 tests pass) and the logical necessity of each test by reading it; the recon's
  red/green counts (S2 6/7, S4 5/10) are the executor's claim, not re-derived.
- I did not re-run the full 1103-test suite a second time to recount; A4 exit 0
  confirms the whole CI passed, and the 1103/2-deselected figure is taken from the
  recon's cited job log (gitignored), not recounted here.
- I did not exercise `restore-status`, `merge-lanes`, or the worktree auto-refresh
  against the LIVE state (forbidden by card S8); all behaviour was verified through
  the throwaway-fixture tests and code reading. The end-to-end driver repair of
  T-005/T-018 after the lane merge is downstream of this review and untested here.
- I did not verify the S7 notes I did not spot-check (T-005 F-2/F-5 detail, T-018
  F-2 both edges) line-by-line; I confirmed F-1 and F-4 by grep and read the rest of
  the recon's evidence pointers.
- The review verdict is recorded against the lane-2 mirror (T-022 is unmerged); I
  did not verify the post-merge fold of T-022's own accepted status into main (the
  merge uses main's pre-fix `_wf.py` until lane 2 is merged; T-022's main placeholder
  is `todo`, so the fold cannot regress it).
