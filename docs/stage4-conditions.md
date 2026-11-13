# Stage 4 machine conditions

Records the machine conditions of the Stage 4 reproducibility session (card T-007, plan §5.4). Gate G3 applies in
full: the desktop apps are closed (`scripts/check-quiet.sh`, blocklist in `configs/quiet-check.toml`). Only process
**names** are recorded, never window titles, URLs or command-line arguments. Template: `docs/stage3-conditions.md`.
Card T-007 names this file as the Stage 4 conditions log; the runbook's generic Stage 4 reference to
`docs/stage3-conditions.md` is honoured by a pointer there (both files are in the card's `files_write`).

<!-- sources: docs/runbook-stage3.md, docs/stage3-conditions.md, scripts/check-quiet.sh, configs/sweeps/stage4.toml, docs/recon/stage4-preflight.md -->

## Session stage4 (stock-64K and tuned-64K), 2026-11-14 local (2026-11-13 22:40 UTC), before the start
- `scripts/check-quiet.sh` output, verbatim (exit code 0):
  ```
  quiet-machine check: 475 processes (names only)
  no blocklisted app is running
  CPU idle check (informational): busy 0.2% over 10 s (the runner's precondition needs below 10%)
  RESULT: QUIET
  ```
- `pgrep -a llama-server`: empty. GPU lock (`.locks/gpu.lock`, `flock -n`): free.
- `nvidia-smi`: memory.used 3 MiB of 16,311 MiB; compute processes: none.
- MemAvailable: 26.6 GiB (27,844,124 kB). Swap in use: 0.63 GiB (664,360 kB of 31,936,508 kB, zram leftover). Load (1 min): 0.05.
  Mains power: yes (desktop, no battery in `/sys/class/power_supply`; Zack confirmed at the gate). `git status --short`: only kit
  bookkeeping (`.workflow/state.json`, `PROGRESS.md`) before the start commit; this log is committed with them so the whole tree is
  clean at the start (card S1, T-001 A15). Code commit: `33c9231` (R3-verified code state; the start commit adds only this log, the
  pointer in `docs/stage3-conditions.md` and the bookkeeping — no code, config or data change).
- Top 5 by memory (names, resident): claude 354 MiB, cosmic-comp 274 MiB, ghostty 205 MiB, cosmic-bg 44 MiB, keyd 39 MiB.
- Top 5 by CPU (names): claude 3.7%, ghostty 1.4%, cosmic-comp 1.0%, pipewire-pulse 0.1%, kswapd0 0.1%.
- Anything else running (names): none besides the terminal (ghostty) with Claude Code and the desktop environment (cosmic-*).
- Spec check: `uv run python -m smallpc.sweep check configs/sweeps/stage4.toml` → `"cells": 2, "cells_in_spec": 2`, stock-64K +
  tuned-64K, both `context=64K`, `"repetitions": 5`, `"canary": true`, spec estimate `"total_h": 0.58`. `data/raw/stage4` absent
  before the start.
- Human gate (card T-007): released on Zack's "go" (2026-11-14 ~00:40 local). Date condition met: 14 November local,
  13 November 22:40 UTC (≥ 13 November 2026).
- Launch: `scripts/run-sweep.sh configs/sweeps/stage4.toml --session-id stage4` at 2026-11-13T22:42:12Z from HEAD
  `1307244` (whole tree clean; R3 re-verified at that HEAD: PASS). Quiet re-check immediately before launch: QUIET,
  exit 0 (`448 processes`, `busy 0.2% over 10 s`). Job dir: `data/logs/jobs/sweep-stage4-20261113T224212Z`;
  runner pid 1926396, `state=running`, first cell canary-start. Session id written to `docs/recon/stage4-session.txt`.