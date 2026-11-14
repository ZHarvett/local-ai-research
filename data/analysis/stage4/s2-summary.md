# Stage 4 S2 check (T-008): Stage 4 against the Stage 3 64K session

<!-- sources: data/analysis/stage4/repro-output.txt, docs/stage4-conditions.md -->

**Overall: FAIL — 5 of 6 rows fail.** Escalated under R4 (brief: `escalations/E-008.md`);
no re-measurement was run. The S2 verdict below is the frozen tool's output, copied verbatim.

Command: `REPRO_CMD` from `docs/recon/commands.env` with `SESSION=stage4`
(`docs/recon/stage4-session.txt`), full output in `data/analysis/stage4/repro-output.txt`:

```bash
source docs/recon/commands.env && SESSION="$(cat docs/recon/stage4-session.txt)" && eval "$REPRO_CMD"
# exit code: 1 (exit 0 = all PASS)
```

## Rows

Stage 3 values are the original means with their 95% CIs; the allowed range is the wider of
the CI and ±5% of the Stage 3 mean, exactly as the tool computes it. All numbers are copied
from `repro-output.txt`.

| cell | metric | Stage 3 mean [95% CI] | allowed range (wider of CI, ±5%) | Stage 4 mean | unit set | result |
|---|---|---|---|---|---|---|
| stock-64K | T_turn_400 (s) | 9.288 [9.238, 9.338] | [8.824, 9.753] | 11.797 | clean | FAIL |
| stock-64K | fresh prefill 32K (tok/s) | 844.155 [840.328, 847.982] | [801.947, 886.363] | 505.860 | clean | FAIL |
| stock-64K | decode at 32K depth (tok/s) | 73.881 [73.792, 73.970] | [70.187, 77.575] | 73.394 | clean | PASS |
| tuned-64K | T_turn_400 (s) | 6.413 [6.003, 6.824] | [6.003, 6.824] | 8.050 | clean | FAIL |
| tuned-64K | fresh prefill 32K (tok/s) | 2024.852 [2001.669, 2048.034] | [1923.609, 2126.094] | 1481.084 | clean | FAIL |
| tuned-64K | decode at 32K depth (tok/s) | 91.644 [85.476, 97.812] | [85.476, 97.812] | 76.480 | clean | FAIL |

The single PASS row (stock-64K decode) passes through the ±5% band: its Stage 4 mean lies
below the Stage 3 CI but inside the wider allowed range. For the two tuned rows whose CI is
wider than ±5%, the allowed range equals the CI.

## R1 (all-units fallback): not triggered

Both cells have 5 clean units of 5 on both days (Stage 3 64K and Stage 4, after the one
re-run pass), verified with the frozen `smallpc.stage3.views.Data` over `data/raw/stage3-64K`
and `data/raw/stage4`. The three paging-flagged tuned-64K attempt-1 windows re-ran clean
(`docs/stage4-conditions.md`); stock-64K had no flagged window. Accordingly the repro output
carries no all-units fallback banner and every row reads "evaluated on clean units". No
S4(d) deviation arises from R1.

## Reading

The failure is shared by both cells: fresh prefill at 32K and T_turn_400 are far outside the
allowed windows, tuned decode is also outside, and only stock decode reproduces. The session
itself passed every declared gate (a–f before and after the re-run, canaries clean, drift
unflagged, quiet-machine checks passed — `docs/stage4-conditions.md`), and the model,
llama.cpp commit, config hashes and driver are identical across the two days. The machine-state
difference found in the environment snapshots and telemetry (the PCIe link ran one generation
slower for the whole Stage 4 session), and the canary's absolute drop across days, are recorded
with their evidence in the escalation brief; they are context for the planning chat's R4
decision, not part of the S2 verdict.

Machine-readable companion: `data/analysis/stage4/s2-summary.json` (`overall: FAIL`, one key
per row).
