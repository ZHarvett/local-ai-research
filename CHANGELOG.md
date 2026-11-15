# Changelog

All notable changes to this project are documented here.

<!-- sources: data/analysis/stage3/headline.md, data/analysis/stage4/s2-summary.md, data/env/build-info.json, configs/model.toml, configs/harness.toml, docs/progress-log.md -->

## v0.1.0 — Step 0 baseline

First release: measured, reproducible stock-vs-tuned baselines for Ornith-1.5-35B-A3B
(Q4_K_M GGUF, MoE) on a 16 GB RTX 5060 Ti at 32K, 64K and 128K context, with mainline
llama.cpp. Headline paired tuned/stock T_turn_400 ratios: 0.705 / 0.690 / 0.706 at
32K / 64K / 128K (95% CIs in the baseline report); the next-day reproducibility check (S2)
passes 6 of 6 rows on Stage 4 run 2.

Release contents:

- **Configs and launch.** The six released server configs
  (`configs/server/{stock,tuned}-{32k,64k,128k}.toml`) and `scripts/launch-server.sh`
  (TOML-rendered argv, GPU lock, `/health` wait), with `scripts/stop-server.sh`.
- **Sweep and analysis tools.** Parameterised sweep runner (`smallpc.sweep`, TOML specs in
  `configs/sweeps/`), Stage 2 decision tooling (`smallpc.stage2`), Stage 3 headline / gate /
  repro (`smallpc.stage3`), statistics (the wider of bootstrap and t intervals,
  `smallpc.stats`), analysis, selection, output sanity, report renderer with SVG figures,
  telemetry and flag detectors, environment snapshots, scrub, and the doc number checker
  (`tools/check_doc_numbers.py`). No extra packaging: Python via `uv`, Bash for launch and
  long jobs.
- **Data.** Append-only raw per-request JSONL for Stages 1–4 (`data/raw/`), environment
  snapshots, health and sanity checks, max-fit probes, microbenchmarks (PCIe, STREAM, NVMe)
  and per-cell telemetry. Stage 4 run 1 is kept as a superseded diagnostic (R5), never
  deleted.
- **Reports.** Baseline report with 95% CIs (`reports/baseline-report.md`), rendered stage
  reports and figures (`reports/stage1/` … `reports/stage4-run2/`), the narrative write-up
  (`reports/writeup.md`), and the README quick start and rerun guide.
- **Provenance.** llama.cpp `b12208`, commit `57d04820dfef7a3519aac276d018a6fd71251895`,
  built with CUDA for sm_120 (`data/env/build-info.json`); model
  `ornith-ai/Ornith-1.5-35B-A3B-GGUF`, revision `f60452672689e0040be350560267a614cc172a18`,
  SHA-256 `42739874cc2ccfdb8523b23fbe52e29b2a7555c8176737ca9ca0b5d59859d41f`
  (`configs/model.toml`); OpenCode `opencode-ai` 1.19.5 and dsh `@deepseek-ai/dsh` 0.2.1-rc.5
  pinned by lockfile (`configs/harness.toml`).

Work-package history (newest last):

- WP0: bootstrap repository (plans, conventions, licenses).
- WP2: Python skeleton (`smallpc`), pydantic config schemas, `smallpc.render`, `launch-server.sh`,
  `stop-server.sh`, `with-gpu-lock.sh`, CI workflow and tests.
- WP5: server bring-up and endpoint health checks (`smallpc.health`, `scripts/healthcheck.sh`,
  `configs/server/health-64k.toml`, log parsers, near-tie logic, `cache_ram` config field).
- WP6: telemetry sampler and flag detectors (`smallpc.telemetry`, `smallpc.flags`), environment
  snapshot and preconditions (`smallpc.envsnap`), `smallpc.stats`, `smallpc.scrub`, exact expert and
  KV sizes (`smallpc.sizes`), PCIe / STREAM / NVMe microbenchmarks (`scripts/run-microbench.sh`,
  `tools/pcie_bw.cu`, pinned `tools/stream/`), 60-second live sampler check.
- Plan v1.3 adopted. WP9: idle precondition from `/proc/stat`, paging flag on llama-server's own faults and
  `VmSwap`, `accounting` flag; the sweep runner (`smallpc.sweep`: spec expansion with placement tokens,
  append-only records, resume, probing of max-fit and N_fit, canaries and drift, re-run mode),
  `scripts/run-sweep.sh`, `scripts/sweep-status.sh`, a mock llama-server for CI, and the real mini-sweep
  (`configs/sweeps/mini.toml`, `data/raw/mini-20261109/`).
- Plan v1.4 adopted. WP11 part 1: paging flag on llama-server major faults only, swap growth recorded as
  `swap_activity_mib` (window summaries and request `flag_detail`, with the RssAnon/RssFile/RssShmem start and end),
  a "Swap sensitivity" report section, paired-ratio intervals as the wider of bootstrap and t on the log ratios.
- WP11 part 2: plan v1.5 adopted; Stage 1 sessions run. Fix: `--rerun-flagged` uses the session's stored `--only` filter, and a
  refused or failed start no longer overwrites `session.json` / `progress.json` (read-modify-write, nothing written before the session
  is loaded); `tests/test_sweep_refusals.py`.
- WP12: Stage 2 feature experiments. `--cache-ram 2048` chosen by the 2f rule; MTP draft length 2
  excluded by the output sanity check (deterministic 8-gram repetition at 32K and 64K); FP16 KV at
  64K and 128K, the 8-bit default at 32K; tuned winners per context (`docs/stage2-summary.md`).
  2c (`--load-mode dio`) not run and 2d (threads) skipped — recorded deviations. Re-run summary
  writer fixed (coords/resolution kept); Stage 2 report and VRAM accounting check.
- WP13: Stage 3 final comparison on a quiet machine — three sessions (one per context), 5 paired
  repetitions, start/end canaries, one re-run pass each; headline tuned/stock T_turn_400
  0.705 / 0.690 / 0.706 at 32K / 64K / 128K, the 128K headline on all units, labelled "includes
  paging-flagged stock windows" (D1, S4(d) deviation); sanity pass on the three tuned files;
  headline tool and rendered report. Stage 4 reproducibility: run 1 superseded (PCIe link at
  Gen3 x8 for the whole session, R5), kept as an excluded diagnostic; run 2 S2 PASS, 6 of 6 rows,
  every row on clean units, on a changed kernel/driver (E-009 caveat).
- Workflow kit: task-based plan execution (`scripts/wf.sh`, `scripts/wf-*.sh`, `.workflow/`),
  unattended loop (`wf-loop.sh`), reviewer calibration. Post-Stage-4 fixes (T-009): the §5.4
  headline rule in the rendered report, plan-version tests read the plan header, sweep-probe
  test flakiness fixed (port reservation and sampler settle), figure axes from 0 with
  `predicted_n` labels clear of the whiskers.
