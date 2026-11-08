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
