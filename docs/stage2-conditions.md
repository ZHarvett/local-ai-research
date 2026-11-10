# Stage 2 machine conditions

Records the machine conditions of the Stage 2 sessions (WP12). Gate G3 is **not met**: the desktop apps stay open and idle, as in
Stage 1 (see `docs/stage1-conditions.md`); the runner's idle gate checks the CPU before every cell. Only process **names** are
recorded, never window titles, URLs or command-line arguments. Figures below are from light polls (`ps`, `/proc`, `nvidia-smi`), not
from the measurement telemetry.

## Phase 0 (before the 2f session), 2026-11-10
- `pgrep -a llama-server`: empty. GPU lock (`.locks/gpu.lock`): free (non-blocking flock acquired).
- `nvidia-smi`: memory.used 3 MiB of 16,311 MiB, 28 °C.
- MemAvailable: 24.8 GiB of 30.5 GiB (above the 20 GiB stop line). Swap in use: 2.01 GiB of 30.46 GiB (zram).
- CPU busy over a 10 s sample: 0.51 %. Load average (1 min): 0.16.
- Top 5 processes by resident memory (names): chrome 0.51 GiB, chrome 0.41 GiB, spotify 0.41 GiB, claude 0.34 GiB, antigravity-ide 0.31 GiB.
- Top 5 by CPU (names): antigravity-ide 1.2 %, claude 1.1 %, spotify 1.0 %, cosmic-comp 0.9 %, chrome 0.5 %.
- Desktop apps open (names): antigravity-ide(x15) chrome(x15) claude(x1) cosmic-comp(x1) kilo(x1) spotify(x10) 
- Spec check: `configs/sweeps/stage2-2f.toml` regenerated with `--out /tmp/stage2-2f-check.toml` differs from the committed file only in line 1 (the generator
  comment quotes its own `--out` path); lines 2 to the end are identical.

## Session s2f (2f host prompt cache), 2026-11-10 13:22:09Z to 14:26:03Z
- Duration 63.9 min (estimate 64 min). Runner exit 0, state complete, `systemd-inhibit` active (`sleep:idle`, block). Started from a clean tree at code commit `7b7daf1`.
- Cells: 6 of 6 complete (plus start and end canary), none `did_not_fit`. Attempt 1 only (no re-run). P6-64K max-fit read from the Stage 1 probe cache (11,008 MiB, `probe_cache_hit` twice).
- Flags: `paging` only (48 request flags = 6 flagged windows of 30; per cell in the decision report). No accounting, warm_prefill, cache_miss, thermal or short_gen flag; drift none (start/end canary PP_fresh 16K 945.0 vs 956.3 tok/s, +1.2 %).
- Runner idle gate: passed at its first check before every cell (busy 0.49 to 1.54 %, 10 s window), no idle waits, no precondition retries; MemAvailable at the checks 24.7 to 25.9 GiB.
- Lowest minimum free VRAM: 549 MiB (P2-128K cram2048 and cram4096), 551 MiB (cram0, cram8192); P6-64K 1,293 and 1,295 MiB.
- Polls (7 min apart, 5 s CPU samples): busy 0.3 to 7.9 % except one sample of 32.1 % at 13:43:40, taken seconds after the runner launched the P2-128K cram2048 server (warm-up phase); the system-wide CPU is not in the telemetry, so the cause of that one sample is not proven; the idle gate that preceded that cell read 0.49 %. The process names printed in the poll log for that sample come from `ps` lifetime averages and do not identify an interferer. Desktop apps open (names): antigravity-ide, chrome, claude, cosmic-comp, kilo, spotify; all at about 1 % CPU or less at rest.
- Lowest MemAvailable: 16.3 GiB at a poll (14:05, P6-64K cram8192), 15.7 GiB in the telemetry (P2-128K cram8192 cell; 16.8 GiB in P6-64K cram8192; 19.7 GiB cram4096; 20.9 to 23.1 GiB for cram2048 and cram0). Never below 15 GiB; the 3 GiB stop line was not approached.
- Highest CPU temperature (Tctl) 82 °C, highest GPU temperature 72 °C.
