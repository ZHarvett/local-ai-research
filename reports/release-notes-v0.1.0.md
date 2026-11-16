# Release notes — v0.1.0 (Step 0 baseline)

<!-- sources: CHANGELOG.md, reports/baseline-report.md, data/analysis/stage3/headline.md, data/analysis/stage4/s2-summary.md, data/env/build-info.json, configs/model.toml, configs/harness.toml -->

First release: measured, reproducible stock-vs-tuned baselines for Ornith-1.5-35B-A3B
(Q4_K_M GGUF, MoE) on a 16 GB RTX 5060 Ti at 32K, 64K and 128K context, with mainline
llama.cpp. This is a measurement baseline, not a speed claim: Step 0 has no hard speed
targets. Every number here is copied from a named repo file (the `sources:` comment above)
or marked derived; `tools/check_doc_numbers.py` verifies this.

## Headline (Stage 3, quiet machine)

The tuned configuration is faster than stock on the standardised turn at every context.
Paired tuned/stock ratio of the estimated 400-token turn time (T_turn_400, lower is
faster), 5 paired repetitions per cell, geometric mean with 95% CI:

| context | headline basis | T_turn_400 tuned/stock [95% CI] |
|---|---|---|
| 32K | clean units | 0.705 [0.672, 0.739] |
| 64K | clean units | 0.690 [0.649, 0.734] |
| 128K | all units, includes paging-flagged stock windows | 0.706 [0.679, 0.735] |

The 128K headline uses all units and is labelled "includes paging-flagged stock windows"
(decision D1, the declared §5.4 headline rule; a recorded S4(d) deviation for 128K, not a
judgement call). The clean-units figures stand beside it in the baseline report; the two
versions agree in sign and in whether each interval excludes 1.0.

Fresh prefill is roughly 2.3–2.9× faster tuned than stock and decode roughly 1.1–1.2× faster at the measured depths. <!-- derived: range of pp_fresh ratios 2.304–2.926 and tg ratios 1.089–1.239 in headline.md -->

## Reproducibility (Stage 4, S2)

The next-day reproducibility check passes 6 of 6 rows on run 2 (2026-11-14), every row on
clean units. Run 1 is superseded (R5: its PCIe link ran at Gen3 x8 for the whole session)
and kept as an excluded diagnostic, never deleted. Run 2 ran on a changed kernel/driver
(E-009 caveat); the S2 comparison stands with that confound recorded.

## Release contents

- **Configs and launch.** The six released server configs
  (`configs/server/{stock,tuned}-{32k,64k,128k}.toml`) and `scripts/launch-server.sh`
  (TOML-rendered argv, GPU lock, `/health` wait), with `scripts/stop-server.sh`.
- **Sweep and analysis tools.** Parameterised sweep runner (`smallpc.sweep`), Stage 2
  decision tooling, Stage 3 headline / gate / repro, statistics (the wider of bootstrap
  and t intervals), report renderer with SVG figures, telemetry and flag detectors,
  environment snapshots, scrub, and the doc number checker. Python via `uv`, Bash for
  launch and long jobs; no extra packaging.
- **Data.** Append-only raw per-request JSONL for Stages 1–4 (`data/raw/`), environment
  snapshots, health and sanity checks, max-fit probes, microbenchmarks (PCIe, STREAM,
  NVMe) and per-cell telemetry. Stage 4 run 1 is kept as a superseded diagnostic (R5).
- **Reports.** Baseline report with 95% CIs (`reports/baseline-report.md`), rendered stage
  reports and figures, the narrative write-up (`reports/writeup.md`), and the README
  quick start and rerun guide.

## Provenance

- llama.cpp `b12208`, commit `57d04820dfef7a3519aac276d018a6fd71251895`, built with CUDA
  for sm_120 (`data/env/build-info.json`).
- Model `ornith-ai/Ornith-1.5-35B-A3B-GGUF`, revision
  `f60452672689e0040be350560267a614cc172a18`, SHA-256
  `42739874cc2ccfdb8523b23fbe52e29b2a7555c8176737ca9ca0b5d59859d41f` (`configs/model.toml`).
- Harnesses pinned by lockfile: OpenCode `opencode-ai` 1.19.5 and dsh `@deepseek-ai/dsh`
  0.2.1-rc.5 (`configs/harness.toml`).

## Known caveats

- Stages 1 and 2 were measured with the desktop apps open (a recorded deviation);
  Stages 3 and 4 on a quiet machine.
- The 128K headline rests on all units (D1 above); expert-cache hit rates include warm-up
  and the attempt-1 units of re-run windows (D9).
- Stage 4 run 2 carries the kernel/driver confound (E-009); run 1 is excluded (R5).

## Where to look

- `README.md` — quick start and rerun guide.
- `reports/baseline-report.md` — full results, flags, deviations and the S1–S5 criteria.
- `reports/writeup.md` — narrative write-up.
- `CHANGELOG.md` — release contents and work-package history.
