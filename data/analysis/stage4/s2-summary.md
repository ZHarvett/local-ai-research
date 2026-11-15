# Stage 4 S2 check (T-008): Stage 4 run 2 against the Stage 3 64K session

<!-- sources: data/analysis/stage4/repro-output.txt, docs/stage4-run2-conditions.md, docs/decisions.md, docs/recon/stage4-session-run2.txt -->

**Overall: PASS — 6 of 6 rows pass.** Run 2 (session `stage4-run2`,
`docs/recon/stage4-session-run2.txt`) is the S2 run under R5; run 1 (session `stage4`) is
superseded and kept as an excluded diagnostic in `data/analysis/stage4-run1-superseded/`.
E-009 (option A, `docs/decisions.md`) ratified run 2's under-load link reading and directed
T-008 to proceed on it. The S2 verdict below is the frozen tool's output, copied verbatim.

Command: `REPRO_CMD` from `docs/recon/commands.env` with `SESSION=stage4-run2`, full output in
`data/analysis/stage4/repro-output.txt`:

```bash
source docs/recon/commands.env && SESSION="$(cat docs/recon/stage4-session-run2.txt)" && eval "$REPRO_CMD"
# exit code: 0 (exit 0 = all PASS)
```

## Rows

Stage 3 values are the original means with their 95% CIs; the allowed range is the wider of
the CI and ±5% of the Stage 3 mean, exactly as the tool computes it. All numbers are copied
from `repro-output.txt`.

| cell | metric | Stage 3 mean [95% CI] | allowed range (wider of CI, ±5%) | Stage 4 mean | unit set | result |
|---|---|---|---|---|---|---|
| stock-64K | T_turn_400 (s) | 9.288 [9.238, 9.338] | [8.824, 9.753] | 9.100 | clean | PASS |
| stock-64K | fresh prefill 32K (tok/s) | 844.155 [840.328, 847.982] | [801.947, 886.363] | 853.861 | clean | PASS |
| stock-64K | decode at 32K depth (tok/s) | 73.881 [73.792, 73.970] | [70.187, 77.575] | 75.936 | clean | PASS |
| tuned-64K | T_turn_400 (s) | 6.413 [6.003, 6.824] | [6.003, 6.824] | 6.296 | clean | PASS |
| tuned-64K | fresh prefill 32K (tok/s) | 2024.852 [2001.669, 2048.034] | [1923.609, 2126.094] | 2000.895 | clean | PASS |
| tuned-64K | decode at 32K depth (tok/s) | 91.644 [85.476, 97.812] | [85.476, 97.812] | 93.459 | clean | PASS |

Which band each row passes through (comparisons of the table's own numbers):

- Inside the Stage 3 CI itself: tuned-64K T_turn_400 (6.296 in [6.003, 6.824]) and tuned-64K
  decode (93.459 in [85.476, 97.812]). For these two rows the CI is wider than ±5%, so the
  allowed range equals the CI.
- Outside the CI but inside the wider ±5% band: stock-64K T_turn_400 (9.100 below the CI's
  9.238), stock-64K fresh prefill (853.861 above the CI's 847.982), stock-64K decode (75.936
  above the CI's 73.970), and tuned-64K fresh prefill (2000.895 just below the CI's 2001.669).
  For these four rows the allowed range is the ±5% band.

## R1 (all-units fallback): not triggered

Both cells have 5 clean units of 5 on both days (Stage 3 64K and Stage 4 run 2, after the one
re-run pass), verified with the frozen `smallpc.stage3.views.Data` over `data/raw/stage3-64K`
and `data/raw/stage4-run2` (`n_clean`/`n_total`, threshold `rules.MIN_CLEAN_PAIRED` = 5):

```text
stage3-64K stock-64K: n_clean=5 n_total=5
stage3-64K tuned-64K: n_clean=5 n_total=5
stage4-run2 stock-64K: n_clean=5 n_total=5
stage4-run2 tuned-64K: n_clean=5 n_total=5
```

Run 2's only flagged unit was stock-64K repetition 2 attempt 1 (paging); its attempt-2 re-run
on a fresh server is clean, and tuned-64K had no flags at all (`docs/stage4-run2-conditions.md`).
Accordingly the repro output carries no all-units fallback banner and every row reads
"evaluated on clean units". No S4(d) deviation arises from R1.

## Context carried into the comparison

- Gates: `GATE_CMD` on `stage4-run2` passed (a to f) both before and after the one re-run pass
  (`docs/stage4-run2-conditions.md`, verbatim gate output there). R2 was not needed: the gate
  passed and tuned-64K has no paging flags.
- Link (R7, read per the E-009 clarification): every sample in the measured cell windows read
  "4, 8"; non-(4,8) samples occurred only at idle and at two 0.5 s idle-to-load ramp rows in
  the re-run canaries (`docs/stage4-run2-conditions.md`, telemetry verification re-derived from
  `data/raw/stage4-run2/telemetry/*.csv.gz`). Nothing was averaged into the data.
- Kernel/driver confound (handoff from `docs/stage4-run2-conditions.md`): run 2 ran on kernel
  `7.3.4-1-cachyos`, NVIDIA driver `620.70.06`; Stage 3 (and run 1) ran on `7.3.1-1-cachyos` /
  `615.78.08`. The S2 comparison carries this confound. A second concrete symptom is recorded
  in the same log: the tuned-64K fit warning (fit pass 18 MiB short of its free-memory target,
  aborted, launched server identical to run 1's) alongside a 31 MiB drop in CUDA-reported free
  device memory at launch. Correlation, not proven causation; no re-measure, the data stands.
- Run 1's S2 FAIL (5 of 6 rows, PCIe link at Gen3 x8 for the whole session) is preserved
  verbatim in `data/analysis/stage4-run1-superseded/` as the excluded diagnostic under R5; it
  is not part of this verdict.

Machine-readable companion: `data/analysis/stage4/s2-summary.json` (`overall: PASS`, one key
per row).
