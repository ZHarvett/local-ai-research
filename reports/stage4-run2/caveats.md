# Stage 4 run 2 — caveats and S2 verdict (T-008)

<!-- sources: docs/stage4-run2-conditions.md, docs/decisions.md, data/analysis/stage4/s2-summary.md, data/analysis/stage4/repro-output.txt, src/smallpc/select.py, data/sanity/stage3-tuned.json -->

Accompanies the frozen renderer's `report.md` (`REPORT_CMD` from `docs/recon/commands.env`,
`SESSION=stage4-run2`). The renderer is code-frozen until T-008 is accepted, so the caveats
required by DECISION E-009 and R5 are recorded here rather than in the generated file.

## S2 verdict

- **PASS, 6 of 6 rows** (exit 0). Full table, band analysis and unit sets:
  `data/analysis/stage4/s2-summary.md`; verbatim tool output:
  `data/analysis/stage4/repro-output.txt`.
- R1 not triggered: both cells have 5 clean units of 5 on both days (Stage 3 64K and run 2
  after its one re-run pass); every row is evaluated on clean units. No S4(d) deviation
  arises from R1.

## Kernel/driver caveat (DECISION E-009)

- **S2 passed on a changed kernel and driver.** Run 2 ran on kernel `7.3.4-1-cachyos`,
  NVIDIA driver `620.70.06`; Stage 3 (the S2 original) ran on `7.3.1-1-cachyos` /
  `615.78.08` (`docs/stage4-run2-conditions.md`). The comparison carries this confound.
- Second concrete symptom (same log): the tuned-64K fit warning — the fit pass was 18 MiB
  short of its free-memory target and aborted, with the launched server identical to run 1's
  (argv, resolved configs, offload and VRAM identity checks in the conditions log) — alongside
  a 31 MiB drop in CUDA-reported free device memory at launch. Correlation, not proven
  causation; no re-measure, the data stands.

## Link (R7 as clarified by E-009)

Every sample in the measured cell windows read "4, 8"; non-(4,8) samples occurred only at
idle and at two 0.5 s idle-to-load ramp rows in the re-run canaries. Telemetry verification
re-derived from `data/raw/stage4-run2/telemetry/*.csv.gz` is in
`docs/stage4-run2-conditions.md`. Nothing was averaged into the data.

## Run 1 superseded (R5)

`reports/stage4/` holds the run-1 render (session `stage4`): the excluded diagnostic, kept
untouched, never deleted. Its S2 outputs are in `data/analysis/stage4-run1-superseded/`.
Run 2 (`stage4-run2`) is the S2 run under R5; E-009 ratified it.

## Known render characteristic (not an S2 criterion)

The eligibility table reads "output sanity check not run" for both cells, identical to the
accepted Stage 3 and run-1 renders: `select.sanity_state` looks up the Stage 3/4 cell names
(`stock-64K`, `tuned-64K`) in the sanity union `data/sanity/stage3-tuned.json`, whose keys
are the Stage 2 names (`P1-64K-b2048`, `tuned-64k`, …), so no entry matches. The S2 verdict
above comes from the repro tool, not the eligibility table. Any change to this behaviour
belongs to a card that may touch code (T-009/T-010), not to T-008.
