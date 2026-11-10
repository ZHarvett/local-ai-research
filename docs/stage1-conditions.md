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

## Session stage1-32K

- Pre-start (2026-11-09 23:17 UTC): tree clean, no llama-server, GPU lock free, GPU 3 MiB, MemAvailable 24.8 GiB,
  CPU busy 0.6 % (5 s), load 0.28, swap 1.65 GiB used. Apps open (names): chrome, claude, kilo, antigravity-ide, cosmic-comp.
- Session ran 2026-11-09 23:17 to 2026-11-10 00:07 UTC (0.83 h; estimate 0.85 h, upper bound 0.97 h), 7 polls at
  about 7-minute intervals. `systemd-inhibit sleep:idle` active (recorded in `session.json`). Code commit `77fbe02fd1`, tree clean.
- CPU busy (5 s samples, 7 polls): 0.3 to 19.1 %; above 10 % in two polls only: 16.6 % (names: antigravity-ide, claude)
  and 19.1 % (names: chrome, antigravity-ide). Highest 19.1 %. The runner's idle gate passed at its first check before
  every cell (highest 1.46 % over 10 s, no waits, no retries). MemAvailable at the preconditions 24.7 to 26.4 GiB
  (never below the 24 GiB warn line); between polls 22.7 to 26.2 GiB. No swap activity above 4 MiB in any window.
- Apps open (names): chrome, claude, kilo, antigravity-ide, cosmic-comp.
