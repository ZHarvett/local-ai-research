# Changelog

All notable changes to this project are documented here.

## Unreleased

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
