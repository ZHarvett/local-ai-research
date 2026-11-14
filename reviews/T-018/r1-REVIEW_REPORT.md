# Review T-018 (cycle 1)

## Model

qwen4-max-preview (same model as executor; adversarial re-derivation, read-only).

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-018` myself (run 2, 0 failures; evidence hashes
`19c658c28128…` / `5e4f36641a45…` match the committed files byte-for-byte, 10,583 / 11,055
bytes). Guard OK at session start; no llama-server running; no GPU or exclusive-machine
task in progress, so nothing was deferred.

| item | verdict | note |
|---|---|---|
| A1 | PASS | accept run 2 exit 0; also ran directly: `uv run pytest -q tests/test_wf_unblock.py tests/test_wf_loop.py` → **49 passed in 5.09s** (12 new + 37 existing kit tests), matching the log's "49/49 with test_wf_loop.py". |
| A2 | PASS | accept run 2: shellcheck on the three wrappers exit 0. Wrappers verified unchanged since plan v1.4 (`git diff 22e20de HEAD -- scripts/wf.sh scripts/wf-decision.sh scripts/wf-escalate.sh` empty); all three are thin `exec` dispatchers, so `--to` reaches `_wf.py` untouched. |
| A3 | PASS | accept run 2: ruff check + format on the new test exit 0. Also re-ran on `scripts/_wf.py` (log claim): "All checks passed! / 1 file already formatted". |
| A4 | PASS | Re-derived at current HEAD `dd675d4` (accept ran at `9d91d5a`): `git diff --name-only 22e20de HEAD -- src configs scripts pyproject.toml uv.lock` lists **only `scripts/_wf.py`**. Diffstat `9d91d5a^..9d91d5a -- scripts/_wf.py`: 51 insertions, 8 deletions = **59 changed lines**, under the card's ~80 ceiling. Commit `9d91d5a` touches only `docs/recon/T-018-kit-repair.md`, `scripts/_wf.py`, `tests/test_wf_unblock.py`; `4b23e09` only the acceptance record, T-018's own lane-file events (checked: step-done S1–S4 + checksum, no other task), `docs/decisions.md`, `docs/progress-log.md`. |
| A5 | PASS | `docs/decisions.md:1300` starts `- Kit exception (T-018):`, names the four scripts + one test file only, the why (all four defects), fix commit `9d91d5a`, ruling date 14 November 2026 (plan v1.4), evidence pointer. |
| A6 | PASS | Judgement, each clause re-derived: **(only named files changed)** A4 window + both commit stats above; of the four scripts only `_wf.py` needed changes. **(unblock without --to unchanged)** the no-`--to` branch is byte-identical to the pre-fix code including the illegal-todo fallback (diff verified); test scenario 1 asserts the old path still fails with "invalid transition" and scenario 3 asserts the old restore + "restored to in-progress" event. **(six scenarios cover T-021 exactly)** scenario 1 is T-021's exact shape (blocked-decision, no `blocked_from`) and asserts the pre-fix failure first; scenarios 2–6 match the card's list (refusals ready/todo/accepted with byte-identical state; restore via blocked_from; verdict records blocked_from; re-escalate keeps it; decision refusal leaves decisions.md absent-or-byte-identical and the escalation open, no events); 6 further regression guards = 12 tests. Fixtures are tmp_path git repos via `WF_REPO` (honored at `scripts/_wf.py:199`), never live `.workflow/`. **(no live state touched)** T-018's commits touch only its own task state; the T-021 unblock is a separate post-task commit (F-1). Recon quality: every cited pre-fix file:line checked against `22e20de:scripts/_wf.py` and **all exact** (1939–1945, 2010, 2017/2021–2023/2032, 2062/2095, 2105/2112–2113/2117–2126/2128, 131–141, 512–524, 1892, 1918, 1454–1467); event timeline seq 175–178 and "E-001…E-008, none for T-021" verified in `.workflow/state.json`; the setup-merge claim verified (`git diff 64b956d 540c133 -- .workflow/lanes/2.json` empty — kit bytes kept). Number checker on the recon: exit 0, "3 numbers verified, 5 sources" (matches log). Full non-GPU suite re-run: **1065 passed, 2 deselected, 286.51s** — the log's counts re-derived exactly. |

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | NOTE | NONE | `.workflow/state.json` event seq 196 (`unblocked`, T-021, "blocked-decision -> changes-requested", 2026-11-14T16:23:06Z); commit `dd675d4`; `docs/recon/T-018-kit-repair.md` §6 | Transparency record: ~3 min after the task-done commit, T-021 was unblocked via the **new `--to` path** in a separate "workflow:" commit (`dd675d4`, which also folds lane 2 into main state). The recon §6 says "suggestion only — not executed here" and the card says "Do not touch T-021"; T-018's own commits indeed never touch T-021, and the change is kit-mediated (event present, no hand-editing). Who ran it (executor after `done` vs Zack) is not verifiable from repo state. It matches the recon's suggested recovery and the fix's purpose — real-world validation of the new path. No action. |
| F-2 | NOTE | FIX-CODE | `scripts/_wf.py` `cmd_decision` pre-check (~2143–2159) vs `mutate` foreign-lane check (~545–548); `scripts/wf-decision.sh` (does not force main) | Residual edge, outside the card's four changes: the decision pre-check validates status and restore target but not lane ownership. Run from a lane worktree for **another lane's** task, it would still write `docs/decisions.md` and mark the escalation decided before `mutate` dies on the foreign-lane check — the original defect class in a narrow path (the protocol runs decisions from main, where the check is inert). Related nuance: `transition()` no-ops on self-transition, so a `review-verdict blocked-decision` issued directly on an already-blocked task (outside the review-open flow) would overwrite an existing `blocked_from`. Both are misuse-adjacent edges; a future kit card could pre-check ownership and guard the overwrite. **Not T-018 rework** — the card froze scope to the four changes, and all card scenarios pass. |
| F-3 | NOTE | DECIDE | `docs/decisions.md:1274` (E-007 rule 3) vs card T-018 as issued (plan v1.4, `22e20de`); `docs/recon/T-018-kit-repair.md` §7; pre-fix `scripts/_wf.py:1918`, `1454–1467` | Routing mismatch confirmed real: E-007 rule 3 routes the review-parser parenthetical limitation "into the T-018 amend after T-008", but the issued v1.4 card lists only the four changes — the executor correctly followed the card and flagged the discrepancy instead of expanding scope. The `ensure_lane_worktree` refresh gap (cause of the documented setup merge) is likewise flagged, not fixed. Both verified at the cited lines. **Does not block T-018's acceptance.** Planning chat to route: (a) a new kit card after T-008 for the parser regex + worktree refresh (recommended — keeps the freeze exception auditable), or (b) an explicit amend to an existing card. Already surfaced by the executor; this review confirms the flag is accurate. |

## Task verdict

accepted

## What I did not verify

- The executor's chat reasoning (not available to the reviewer, per protocol).
- **Who** ran the post-task T-021 unblock (`dd675d4`): repo evidence shows what happened and that it was kit-mediated, not the actor (F-1).
- The recon §5 claim that the lane file was byte-identical to the **runtime mirror** `.git/workflow/lanes/2.json` "before and after": I verified the committed bytes are identical across `64b956d → 540c133`, but the untracked mirror's historical content is gone (folded in `dd675d4`) and was not reconstructed.
- The log's full-suite **runtime** 308.49 s: my re-run took 286.51 s; pass/deselect counts match exactly, timing is machine variance and not re-derivable.
- The foreign-lane decision edge (F-2) is from code reading, not a fixture run; I did not build a two-lane worktree fixture to trigger it end-to-end.
- "Guard OK throughout" the executor's session: I verified guard at my session start and the acceptance re-run, not at every historical step.
- The T-005-era lane events (seq 0–5) folded into main state by `dd675d4`: provenance noted, not audited line-by-line.
- No heavy/GPU items exist in this card; nothing was deferred.
