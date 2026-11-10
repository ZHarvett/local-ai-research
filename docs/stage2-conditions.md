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
