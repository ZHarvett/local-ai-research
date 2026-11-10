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

## Session stage1-64K

- Pre-start (2026-11-10 00:08 UTC): tree clean, no llama-server, GPU lock free, GPU 3 MiB, MemAvailable 26.3 GiB,
  CPU busy 0.3 % (5 s), load 0.86 (1 min), swap 2.32 GiB used. Apps open (names): chrome, claude, antigravity-ide, cosmic-comp.
- Session ran 2026-11-10 00:08 to 01:20 UTC (1.20 h; estimate 1.28 h, upper bound 1.48 h), 11 polls. `systemd-inhibit sleep:idle`
  active. Code commit `18bd4634c4`, tree clean. Runner idle gate passed at the first check before every cell (highest 0.99 %,
  no waits, no retries).
- CPU busy (5 s samples): 0.7 to 27.2 %; above 10 % in three polls: 27.2 % (antigravity-ide, claude; during P2-64K-b2048
  repetition 1, short point), 20.3 % (antigravity-ide, claude; P1-64K-b4096) and 14.2 % (antigravity-ide, claude; stock-64K).
  Highest 27.2 %. ("claude" is this Claude Code session's own tool processes.)
- Memory: MemAvailable at the runner's preconditions 26.05 to 26.71 GiB, but between polls it fell as low as **20.2 GiB**
  (01:05, during stock-64K) and was 21.2 GiB at 00:51; the 20 GiB abort line was not crossed at any precondition.
- **Swap activity (note, not a flag):** 6 of the 38 measured windows had `swap_activity_mib` above 64 (P4-64K-b2048 359,
  P5-64K-b2048 730, P7-64K-b2048 2,557, P8-64K-b2048 500, P8-64K-b4096 2,665, stock-64K 6,172), all in repetition 1, the
  second repetition of the cell. Only stock-64K repetition 1 also had more than 1,000 major faults, so it alone carries
  the `paging` flag (7 requests, one window); it is a re-run candidate (phase 4). zram swap, swappiness 150.
- Apps open (names): chrome, claude, antigravity-ide, cosmic-comp.

## Session stage1-128K

- Pre-start (2026-11-10 01:22 UTC): tree clean, no llama-server, GPU lock free, GPU 3 MiB, MemAvailable 26.4 GiB,
  CPU busy 0.3 % (5 s), load 1.04 (1 min), swap 2.65 GiB used. Apps open (names): chrome, claude, antigravity-ide, cosmic-comp.
- Session ran 2026-11-10 01:22 to 03:34 UTC (2.19 h; estimate 2.18 h, upper bound 2.57 h), 19 polls. `systemd-inhibit sleep:idle`
  active. Code commit `47dfc69f58`, tree clean. Runner idle gate passed at the first check before every cell (highest 1.13 %,
  no waits, no retries); MemAvailable at the runner's preconditions 26.1 to 26.7 GiB.
- CPU busy (5 s samples): 1.7 to 38.8 %; above 10 % in six polls: 38.8 % (antigravity-ide, claude; P1-128K-b4096 short point,
  repetition 0), 17.4 % (antigravity-ide, claude; P9-128K-b2048), 15.8 % (antigravity-ide, python = the runner, claude), 14.2 %
  (kswapd0, claude, antigravity-ide), 12.2 % (chrome, antigravity-ide, claude), 10.4 % (claude, antigravity-ide). Highest 38.8 %.
- Memory between polls fell to **18.1 GiB** MemAvailable (03:08, during stock-128K), 19.3 GiB (02:26), 19.8 GiB (02:47) and 19.9 GiB
  (03:30); the kernel's `kswapd0` was seen busy once (02:04).
- **Paging flag: 14 of 38 measured windows (36.8 %).** All 14 are repetition 1 (the second repetition) of: P1-128K-b2048, P2 (both
  batches), P3 (both), P4 (both), P5 (both), P6 (both), P7 (both) and stock-128K. Swap growth in those windows 2.3 to 5.4 GiB (stock
  -128K: -0.5 GiB, i.e. swap-in). None in P1-b4096, P8 or P9 (explicit `--n-cpu-moe`). 20 windows had swap activity above 64 MiB.
  Gate criterion f (at most 20 %) FAILED: 14 of 38 windows flagged for paging, all in repetition 1, in cells with `--fit`, `-cmoe`
  or the stock placement, none in P1-b4096, P8 or P9. **Accepted by Zack and the step lead as a recorded deviation** (criterion f
  was a stop rule set for this run to get a human decision, not a plan rule; no rule was changed). G3 was not met.
- Apps open (names): chrome, claude, antigravity-ide, cosmic-comp.

## Re-run pass (plan: one `--rerun-flagged` per session, never twice, no attempt 3)

- **stage1-32K:** no repetition carries a re-runnable flag (0 of 326 requests flagged, window flags none, drift none), so nothing
  was re-run. A first attempt of the runbook command on 2026-11-10 08:33 UTC was refused by a bug in the runner
  (`--rerun-flagged` ignored the stored `--only`) and overwrote `session.json` / `progress.json`; both were restored from commit
  `18bd463` and the runner was fixed (`7b800c0`, `docs/decisions.md` "WP11 part 2: re-run mode fixes"). No re-run of 32K was made.
- **stage1-64K** (2026-11-10 08:46 to 08:56 UTC, code commit `7b800c0355`, tree clean): planned and ran 1 unit, stock-64K repetition 1
  (the only paging-flagged window), as attempt 2, plus its own start and end canaries (indices 110 to 115; re-run drift: no flag).
  Attempt 2 is clean (7 requests, no flags). `code_commit_changed` warning recorded, as expected. Machine: MemAvailable 25.3 GiB
  before, 22.6 to 26.1 GiB at the two polls; CPU busy 0.4 to 7.2 % (never above 10 %); apps open: chrome, claude, antigravity-ide, cosmic-comp.
  Note: a completed re-run sets `finished_utc` in `session.json` to the end of the re-run.
- **stage1-128K** (2026-11-10 08:57 to 09:48 UTC, code commit `60c3bfc6e7`, tree clean): planned and ran the 14 paging-flagged
  units (repetition 1 of P1-b2048, P2, P3, P4, P5, P6, P7 at both batches where flagged, and stock-128K) as attempt 2, plus its own
  start and end canaries (re-run drift: no flag). All 14 attempt-2 units are clean (98 requests, no flags). Machine: MemAvailable
  25.7 GiB before, 21.5 to 26.0 GiB at the 8 polls; CPU busy 6.7 to 7.3 % at every poll (never above 10 %); apps open: chrome,
  claude, antigravity-ide, cosmic-comp. Each attempt-2 unit ran as the first measured repetition of a fresh server (attempt 1 was the
  second repetition of a long-running one).
