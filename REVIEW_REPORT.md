# Review T-008 (cycle 1)

## Model

qwen4-max-preview (single model for executor and reviewer; adversarial re-derivation, read-only).

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-008` myself (record run 2, 0 failures). Evidence hashes
identical to the executor's run 1: repro-output `10ff296c9b69`, s2-summary.md `8d46940332a5`,
s2-summary.json `831a466b0f00`.

| item | verdict | note |
|---|---|---|
| A1 | PASS | `REPRO_CMD` with `SESSION=stage4-run2` exit 0; accept's stdout sha256 `10ff296c…` equals the committed `data/analysis/stage4/repro-output.txt` (1092 bytes). Independently rebuilt with the frozen `smallpc.stage3.repro.build`/`render`: `render + "\n"` is byte-identical to the committed file. |
| A2 | PASS | `s2-summary.json` `overall: PASS`. All 6 rows recomputed from `data/raw/stage3-64K` + `data/raw/stage4-run2`; the allowed band re-derived from scratch as the wider of the Stage 3 CI and ±5% of the Stage 3 mean (matches the tool's lo/hi to 1e-9) and each PASS re-evaluated independently. |
| A3 | PASS | `tools/check_doc_numbers.py data/analysis/stage4/s2-summary.md` exit 0 — 55 numbers verified, 4 sources (matches the progress-log claim). |
| A4 | PASS (judgement) | Rows match: md table == JSON == fresh tool output for all 6 rows (programmatic comparison, `/tmp/t008-review/verify.py`). R1 correctly **not** triggered: re-derived `n_clean`/`n_total` with the frozen `views.Data` — stock-64K and tuned-64K are 5/5 on **both** days (`MIN_CLEAN_PAIRED = 5`). Run 2's only flagged unit is stock-64K rep 2 attempt 1 (`paging`), superseded by a clean attempt 2; tuned-64K has zero flags. No all-units fallback banner; every row reads "evaluated on clean units". R1's condition (<5 clean units) holds for neither cell, so not applying it is correct. |

### Other re-derivations (beyond the mechanical acceptance)

- **S1 supersession (R5):** the three run-1 files in `data/analysis/stage4-run1-superseded/`
  are sha256-identical to their `a52bd82` originals in `data/analysis/stage4/` (nothing deleted
  or edited); the one-line README is present. The run-1 render `reports/stage4/report.md` +
  figures is unchanged (`git diff a52bd82..HEAD` empty for those paths). The superseded run-1
  JSON reads `overall: FAIL`, 1 of 6 rows passing — matching the summary's "5 of 6 rows" claim.
- **Code freeze (shared rule 2):** `git diff --name-only a52bd82..HEAD -- src configs scripts
  pyproject.toml uv.lock` is empty. `data/raw/` untouched (0 files in the diff).
- **Report authenticity (S3):** a fresh `REPORT_CMD` with `SESSION=stage4-run2` rendered into
  `/tmp/t008-review/render` is byte-identical to `reports/stage4-run2/report.md` + all 5 figures,
  except the "Regenerate with" line that echoes `--out` (proof the committed render used
  `--out reports/stage4-run2`). `caveats.md` is the documented hand-written companion, not
  renderer output. Report headline numbers match the repro means (stock 9.10 / 853.9 / 75.9;
  tuned 6.30 / 2000.9 / 93.5), both cells 5/5, provenance commit `c4bdc4db4a`, snapshot
  `f66a698dee8dbca0`.
- **Gate:** re-ran `GATE_CMD` on `stage4-run2` myself — exit 0, PASS a to f (f: 0 of 17
  attempt-1 tuned+canary windows flagged; stock 1 of 5, rep 2), matching the conditions log's
  post-rerun gate. R2 not needed.
- **Kernel/driver confound:** verified from the authoritative env snapshots
  (`data/raw/stage3-64K/snapshots/66c04f6c276af71a.json`: `7.3.1-1-cachyos` / `615.78.08`;
  `data/raw/stage4-run2/snapshots/f66a698dee8dbca0.json`: `7.3.4-1-cachyos` / `620.70.06`).
  The fit-warning numbers in `caveats.md` (18 MiB short of the 1024 MiB target; 31 MiB drop,
  15803 → 15772) match `docs/stage4-run2-conditions.md:118-148`.
- **Number checkers:** `caveats.md` exit 0 (5 numbers), `docs/decisions.md` exit 0 (372 numbers)
  — both match the progress-log claims. The decisions.md S2 table equals the repro output.
- **Privacy:** `SCRUB_CMD` exit 0, 0 findings in 4458 files (courtesy scan; release scrub is T-013).
- **S4/S5:** no FAIL row, so no R4/R6 escalation was required; no R1 deviation to record; the
  progress-log entry is appended in §12.5 format.

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | MINOR | FIX-DOC (carry-forward; no T-008 rework) | PLAN.md:378 (card S3 "into reports/stage4/"); reports/stage4/README.md; reports/stage4-run2/report.md:8; docs/progress-log.md T-008 S3 bullet | The render landed in `reports/stage4-run2/`, not the card's literal `reports/stage4/`. **I accept the executor's interpretation:** `REPORT_CMD` is session-parameterized (`--out reports/$SESSION`), S1 says "use the run-2 session for everything below", and E-008 Scope keeps run-1 analysis outputs in the repo — overwriting `reports/stage4/` would destroy the run-1 render. A pointer README marks the supersession, and the render is proven tool-generated. The same literal path recurs in **T-009 S5** ("Re-render … reports/stage4/") and **T-010** `files_read`: carry the convention forward (valid render = `reports/stage4-run2/`; `reports/stage4/` = superseded run-1 diagnostic) so T-009/T-010 do not "fix" it by overwriting. The planning chat may ratify the path in plan v1.9 (T-011). Cheapest action is documentation carry-forward, not a directory move. |
| F-2 | NOTE | none for T-008 (already documented; carried to T-009/T-010) | reports/stage4-run2/report.md:59-62; src/smallpc/select.py:49-54; data/sanity/stage3-tuned.json (`cells` keys); reports/stage4-run2/caveats.md:42-49 | The eligibility table reads "output sanity check not run" / "No eligible candidate" for both cells. Cause verified read-only: `select.sanity_state` looks up `stock-64K`/`tuned-64K` in the sanity union whose keys are Stage 2 names (`P1-64K-b2048`, `tuned-64k`, …), so nothing matches. Pre-existing frozen-renderer behaviour, identical to the accepted Stage 3 and run-1 renders; the S2 verdict comes from the repro tool, not this table. The executor correctly deferred any change to a code-owning card. No T-008 action. |
| F-3 | NOTE | carry-forward to T-010 | reports/stage4-run2/caveats.md:18-27; data/raw/stage4-run2/snapshots/f66a698dee8dbca0.json; data/raw/stage3-64K/snapshots/66c04f6c276af71a.json; docs/stage4-run2-conditions.md:118-148 | The E-009-required kernel/driver caveat is present and accurate (S2 passed on `7.3.4-1-cachyos` / `620.70.06` vs Stage 3's `7.3.1-1-cachyos` / `615.78.08`), with the fit-warning second symptom. The snapshots also show CUDA driver-support 13.4 → 13.5 (same upgrade, covered by "changed driver"). This confound must survive into T-010's final report and write-up; it is a caveat on the S2 PASS, not a defect in T-008. |

No BLOCKER or MAJOR findings. The executor's report and my re-runs agree on every number,
hash and verdict I checked.

## Task verdict

accepted

## What I did not verify

- The full telemetry/link re-derivation (3,556 sustained-generation samples, 2,657 measured-cell
  rows, the two 0.5 s ramp rows): that is T-021's accepted evidence, ratified by DECISION E-009.
  I relied on it and spot-checked the conditions log's gate output and fit/kernel numbers; I did
  not re-filter the raw `telemetry/*.csv.gz` myself.
- The gate's **before-rerun** output: I re-ran the final-state gate only; the before-rerun
  verbatim output lives in the conditions log and was covered by T-021's review.
- Figure SVG internal numbers beyond byte-identity to the frozen renderer's fresh output
  (tool-generated; not independently re-derived from raw data).
- The bootstrap/t-interval internals in `smallpc.stats` (frozen, previously reviewed). I
  re-derived the S2 band rule and every row value, not the resampling itself.
- The run-1 render's internal numbers: it is an excluded diagnostic; I verified it is preserved
  unchanged, not re-analysed it.
- Release-grade scrub (T-013's card); `SCRUB_CMD` here was a courtesy scan, not the release check.
- T-007/T-021 work beyond what T-008's evidence leans on (their own review cycles cover them).
- The executor's chat reasoning (not available to the reviewer, per protocol).
