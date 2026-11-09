# Stage 1 conditions log

Machine conditions of the three Stage 1 screening sessions (WP11 part 2, plan v1.5).

- **G3 was not met.** Zack's desktop apps stay open for all three sessions (browser, IDE, terminal tools and the
  desktop shell), and could not be closed. They are kept idle. This is a known, recorded deviation from the runbook's
  G3 checklist (§5.7 of the plan: "browser closed"). The runner's own idle-CPU gate (busy below 10% over 10 s) still
  applies before every cell.
- **Only process names are recorded** here: never window titles, URLs or command-line arguments.
- CPU "busy" is the share of non-idle time over the stated sample from `/proc/stat`. Memory is `MemAvailable`.
- Samples are taken with light commands only (`/proc/stat`, `/proc/meminfo`, `ps -o comm`, `nvidia-smi`), about every
  7 minutes during a session.

## Phase 0 check (2026-11-09 23:16 UTC, before any session)

| item | value |
|---|---|
| `git status --short` | empty |
| `pgrep -a llama-server` | empty |
| GPU lock (`.locks/gpu.lock`) | free |
| GPU memory.used | 3 MiB, no compute process |
| MemAvailable | 24.8 GiB (at or above the 24 GiB warn line) |
| CPU busy, 10 s sample | 0.5 % |
| load average (1, 5, 15 min) | 0.30, 0.40, 0.92 |
| swap | 1.66 GiB used of 30.46 GiB (zram) |
| top 5 by memory (names) | chrome, chrome, claude, kilo, antigravity-ide |
| top 5 by CPU (names) | cosmic-comp, chrome, claude, antigravity-ide, chrome |
