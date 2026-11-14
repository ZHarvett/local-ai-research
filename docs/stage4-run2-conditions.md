# Stage 4 run 2 machine conditions

Records the machine conditions of the Stage 4 reproducibility session, **run 2** (card T-021, plan §5.4; rules R5 to R7 in
`docs/decisions.md`). Run 1 (session `stage4`, id in `docs/recon/stage4-session.txt`) is invalid for S2 and superseded (R5: the
PCIe link ran at Gen3 x8 for the whole session); its data and conditions log (`docs/stage4-conditions.md`) stay untouched.
Gate G3 applies in full: the desktop apps are closed (`scripts/check-quiet.sh`, blocklist in `configs/quiet-check.toml`). Only
process **names** are recorded, never window titles, URLs or command-line arguments. Template: `docs/stage4-conditions.md`.

<!-- sources: docs/runbook-stage3.md, docs/stage4-conditions.md, scripts/check-quiet.sh, configs/sweeps/stage4.toml, docs/recon/pcie-link.md, docs/decisions.md -->

## Session stage4-run2 (stock-64K and tuned-64K), 2026-11-14 local (14:28 UTC), before the start
- `scripts/check-quiet.sh` output, verbatim (exit code 0):
  ```
  quiet-machine check: 405 processes (names only)
  no blocklisted app is running
  CPU idle check (informational): busy 0.3% over 10 s (the runner's precondition needs below 10%)
  RESULT: QUIET
  ```
- `pgrep -a llama-server`: empty. GPU lock (`.locks/gpu.lock`, `flock -n`): free.
- `nvidia-smi`: memory.used 2 MiB of 16,311 MiB; compute processes: none.
- MemAvailable: 28.0 GiB (29,410,316 kB). <!-- derived: /proc/meminfo MemAvailable kB / 1048576 --> Swap in use: 3,700 kB <!-- derived: SwapTotal 31,936,508 kB - SwapFree 31,932,808 kB, /proc/meminfo; zram leftover --> (0.00 GiB). Load (1 min): 0.27.
  Mains power: yes (desktop, no battery in `/sys/class/power_supply`; Zack confirmed at the gate). `git status --short`: only kit
  bookkeeping (`.workflow/state.json`, `PROGRESS.md`) before the start commit; this log is committed with them so the whole tree is
  clean at the start (card S1). HEAD before the start commit: `9cc1c16` (R3 re-verified at that HEAD: PASS).
- Top 5 by memory (names, resident): claude 339 MiB, cosmic-comp 238 MiB, ghostty 221 MiB, python3 154 MiB, Xwayland 123 MiB. <!-- derived: ps -eo comm=,rss= sorted, kB / 1024 -->
- Top 5 by CPU (names): claude 0.6%, ghostty 0.2%, cosmic-comp 0.2%, zsh 0.0%, zsh 0.0%.
- Anything else running (names): no blocklisted app among the 405 processes (check-quiet above); the top residents are the terminal
  (ghostty) with Claude Code, the desktop environment (cosmic-comp, Xwayland) and a python3 process (154 MiB, not blocklisted).
- Spec check: `uv run python -m smallpc.sweep check configs/sweeps/stage4.toml` → `"cells": 2, "cells_in_spec": 2`, stock-64K +
  tuned-64K, both `context=64K`, `"repetitions": 5`, `"canary": true`, spec estimate `"total_h": 0.58`. `data/raw/stage4-run2`
  absent before the start; `data/raw/stage4` (run 1, superseded) present and untouched.
- Session id: the runbook §6 command is `scripts/run-sweep.sh configs/sweeps/stage4.toml --session-id stage4`; that id belongs to
  run 1, and `run-sweep.sh` refuses to reuse an existing session dir ("session already exists", `scripts/run-sweep.sh`). Run 2
  therefore uses the same command with `--session-id stage4-run2` — a second session beside run 1 with no code change and no
  `--allow-dirty` (card T-021 S1; the acceptance requires the two session files to differ). `GATE_CMD`/`REPRO_CMD` read the id from
  `docs/recon/stage4-session-run2.txt`; `docs/recon/stage4-session.txt` is never touched.
- Human gate (card T-021): released on Zack's "go" (2026-11-14 ~16:28 local, 14:28 UTC). Date condition (R3): 14 November 2026,
  ≥ 13 November 2026.
- Kernel/driver confound (carried from `docs/recon/pcie-link.md`, as T-020's result directs): run 2 runs on kernel
  `7.3.4-1-cachyos`, NVIDIA driver `620.70.06`; Stage 3 and run 1 ran on `7.3.1-1-cachyos` / `615.78.08` (the upgrade at
  02:37 SAST on 14 November came after run 1). The S2 comparison (T-008) carries this confound.
- PCIe link (R7): idle before the start: current Gen1 x8, **max Gen4**, width 8 of 8 — the documented idle downshift
  (`docs/recon/pcie-link.md`), with the negotiated ceiling back at Gen4 (run 1's snapshot had max Gen3). T-020 verified the link
  at Gen4 x8 under load on 2026-11-14 (10 of 10 under-load samples "4, 8"; pinned H2D bandwidth 14.29 to 14.39 GB/s;
  `Result: link PASS`). R7 for this session: at every poll while a server is generating, sample
  `nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.width.current --format=csv,noheader`; anything other than "4, 8" while
  generating stops the session and escalates. Idle samples between cells are recorded as idle, never averaged into the data.

## Session stage4-run2, polls (quiet check + sweep-status + light sample + R7 link sample, ~7 min cadence)