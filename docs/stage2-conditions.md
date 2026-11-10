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

## Session s2a-32K (2a MTP, 32K), Phase 0 conditions, 2026-11-10T16:17Z
- pgrep llama-server: empty. GPU lock: free. nvidia-smi memory.used: 3 MiB. MemAvailable: 25.0 GiB. Swap in use: 2.46 GiB of 30.46 GiB.
- CPU busy over 10 s: 1.08 %. Load average (1 min): 0.68.
- Top 5 by memory (names): spotify 0.50 GiB, chrome 0.40 GiB, chrome 0.37 GiB, claude 0.34 GiB, chrome 0.30 GiB.
- Top 5 by CPU, ps lifetime average (names): chrome 9.1 %, antigravity-ide 1.2 %, claude 1.1 %, cosmic-comp 1.0 %, spotify 0.9 %.
- Desktop apps open (names): antigravity-ide chrome claude cosmic-comp kilo spotify 

### Session s2a-32K result (2026-11-10 16:17:10Z to 16:48:20Z)
- Duration 31.2 min (runbook estimate 32 min). Runner exit 0, state complete, `systemd-inhibit` active, one run. Code commit of the session: `60edde1`.
- Cells: 5 of 5 complete (P6-32K-b4096 at mtp0, mtp1, mtp2, mtp3; P2-32K-b4096 mtp0), none `did_not_fit`. Max-fit probes: MTP cells probed fresh (4 steps each, 4096, 11264, 11008, 10752); mtp0 read the Stage 1 probe (`probe_cache_hit`).
- Flags: `paging` only (28 request flags = 4 flagged windows of 25 measured attempt-1 windows, 16.0 %; gate criterion f PASS): P6-mtp1 repetitions 2, 3, 4 and P6-mtp0 repetition 4. No accounting, warm_prefill, cache_miss, thermal or short_gen flag; drift none.
- Runner idle gate: first check passed every time (busy at most 1.52 %), no idle waits, no retries; MemAvailable at the checks 24.5 GiB or more.
- Lowest minimum free VRAM: 567 MiB (P2-32K-b4096-mtp0); P6 cells 1,069 to 1,379 MiB.
- Polls (7 min apart; the first poll predates the "server share" column): busy 7.1 to 17.1 %; P6 cells run their experts on the CPU, so most of that is the server's own threads (the later polls show the server at 6.3 % and everything else at 0.8 to 7.5 %). No interfering process identified.
- Lowest MemAvailable: 21.5 GiB (telemetry, P6-mtp2), 22.0 GiB at a poll. Highest CPU Tctl 75 °C, GPU 68 °C.

## Session s2a-64K (2a MTP, 64K), Phase 0 conditions, 2026-11-10T16:49Z
- pgrep llama-server: empty. GPU lock: free. nvidia-smi memory.used: 3 MiB. MemAvailable: 25.2 GiB. Swap in use: 3.07 GiB of 30.46 GiB.
- CPU busy over 10 s: 1.14 %. Load average (1 min): 1.76.
- Top 5 by memory (names): chrome 0.40 GiB, spotify 0.33 GiB, claude 0.32 GiB, antigravity-ide 0.31 GiB, chrome 0.31 GiB.
- Top 5 by CPU, ps lifetime average (names): missioncenter-m 3.6 %, chrome 3.5 %, missioncenter 2.7 %, antigravity-ide 1.3 %, claude 1.2 %.
- Desktop apps open (names): antigravity-ide chrome claude cosmic-comp kilo spotify 

### Session s2a-64K result (2026-11-10 16:49:24Z to 17:35:51Z): gate criterion f FAILED
- Duration 46.5 min (runbook estimate 47 min). Runner exit 0, state complete, `systemd-inhibit` active, one run.
- Cells: 5 of 5 complete (P6-64K-b4096 mtp0 to mtp3, P2-64K-b4096 mtp0), none `did_not_fit`. MTP cells probed fresh (4 steps each); mtp0 read the Stage 1 probe.
- Flags: `paging` only (42 request flags = 6 flagged windows of 25 measured attempt-1 windows, **24.0 %**, criterion f FAIL): P6-mtp1 repetitions 2, 3, 4 and P6-mtp2 repetitions 2, 3, 4. No accounting, warm_prefill, cache_miss, thermal or short_gen flag; drift none.
- Runner idle gate: first check passed every time (busy at most 1.65 %), no idle waits, no retries; MemAvailable at the checks 25.0 GiB or more.
- Lowest minimum free VRAM: 545 MiB (P2-64K-b4096-mtp0); P6 cells 1,039 to 1,293 MiB.
- Polls (7 min apart): busy 0.6 to 14.7 %, of which the server's own share 0.0 to 14.5 % and everything else 0.2 to 1.1 %. `missioncenter` (a system-monitor app) was running at the start (top-CPU list, lifetime average 3.6 %), not in the 32K list. No interfering process identified.
- Lowest MemAvailable: 21.1 GiB (telemetry, P6-mtp3), 21.4 GiB at a poll. Highest CPU Tctl 75 °C, GPU 71 °C.
- Stopped here by the continuation's stop rule: the 128K session was not started, no re-run and no decision were made.

## Session s2a-128K (2a MTP, 128K), Phase 0 conditions, 2026-11-10T18:12Z
- pgrep llama-server: empty. GPU lock: free. nvidia-smi memory.used: 3 MiB. MemAvailable: 24.3 GiB. Swap in use: 2.83 GiB of 30.46 GiB.
- CPU busy over 10 s: 1.22 %. Load average (1 min): 0.85.
- Top 5 by memory (names): chrome 0.42 GiB, chrome 0.39 GiB, claude 0.35 GiB, chrome 0.33 GiB, antigravity-ide 0.32 GiB.
- Top 5 by CPU, ps lifetime average (names): chrome 4.9 %, missioncenter-m 3.5 %, missioncenter 2.4 %, antigravity-ide 1.3 %, claude 1.2 %.
- Desktop apps open (names): antigravity-ide chrome claude cosmic-comp kilo spotify 
- Also open: missioncenter (system monitor app), seen since the 64K session.

### Session s2a-128K result (2026-11-10 18:12:53Z to 19:20:10Z)
- Duration 67.3 min (runbook estimate 65 min). Runner exit 0, state complete, `systemd-inhibit` active, one run. Gate criteria a to e PASS.
- Cells: 5 of 5 complete (P2-128K-b4096 mtp0 to mtp3, P6-128K-b4096 mtp0), none `did_not_fit`. No probe steps (P2 is a fit placement; P6-mtp0 read the Stage 1 probe).
- Flags: `paging` only (35 request flags = 5 flagged windows of 25 measured attempt-1 windows, 20.0 %): P2-mtp2 repetitions 0, 1 (swap activity 551 and 319 MiB) and P2-mtp3 repetitions 0, 1, 2 (771, -1 and -16 MiB). Changed criterion f (at most 40 % flagged, no flagged window above 1,024 MiB swap activity): PASS (largest 771 MiB). No accounting, warm_prefill, cache_miss, thermal or short_gen flag; drift none.
- Runner idle gate: first check passed every time (busy at most 0.97 %), no idle waits, no retries; MemAvailable at the checks 24.4 GiB or more.
- **Lowest minimum free VRAM: 421 MiB (P2-128K-b4096-mtp1), 443 MiB (mtp3), 503 MiB (mtp2): three cells below the 512 MiB eligibility line**; P2-mtp0 549 MiB, P6-mtp0 1,381 MiB.
- Polls (7 min apart): busy 1.7 to 7.4 % with the server's own share 3.1 to 6.6 % and everything else 0.6 to 3.2 % (one sample, taken as the server exited, has no valid server/other split). No interfering process identified; `missioncenter` open as before.
- Lowest MemAvailable: 20.1 GiB (telemetry, P2-mtp1), 21.1 GiB at a poll. Highest CPU Tctl 74 °C, GPU 72 °C.

## Re-run pass for the 2a sessions (--rerun-flagged, once per session), Phase 0 conditions, 2026-11-10T19:22Z
- pgrep llama-server: empty. GPU lock: free. nvidia-smi memory.used: 3 MiB. MemAvailable: 25.2 GiB. Swap in use: 3.18 GiB of 30.46 GiB.
- CPU busy over 10 s: 0.78 %. Load average (1 min): 0.79.
- Top 5 by memory (names): chrome 0.40 GiB, claude 0.34 GiB, antigravity-ide 0.31 GiB, antigravity-ide 0.30 GiB, chrome 0.29 GiB.
- Top 5 by CPU, ps lifetime average (names): chrome 5.4 %, missioncenter-m 3.5 %, missioncenter 2.1 %, antigravity-ide 1.4 %, claude 1.3 %.
- Desktop apps open (names): antigravity-ide chrome claude cosmic-comp kilo spotify 
- Units to re-run (attempt-1 paging flags): s2a-32K 4 (P6-mtp0 rep 4; P6-mtp1 reps 2, 3, 4), s2a-64K 6 (P6-mtp1 and P6-mtp2 reps 2, 3, 4), s2a-128K 5 (P2-mtp2 reps 0, 1; P2-mtp3 reps 0, 1, 2).

### Re-run s2a-32K (--rerun-flagged, once): 2026-11-10 19:22:16Z to 19:32:22Z (10.1 min)
- 4 units re-run (attempt 2): P6-mtp0 repetition 4, P6-mtp1 repetitions 2, 3, 4. **3 clean, 1 still paging-flagged** (P6-mtp1 repetition 4, swap activity 0 MiB). The re-run adds `canary-rerun-start` and `canary-rerun-end`; drift none. Polls: busy 7.4 % (server 6.3 %), one sample 34.1 % of which the server 33.1 %; MemAvailable at least 21.7 GiB.

### Re-run s2a-64K (--rerun-flagged, once): 2026-11-10 19:34:47Z to 19:49:14Z (14.5 min)
- 6 units re-run (attempt 2): P6-mtp1 and P6-mtp2 repetitions 2, 3, 4. **6 clean** (one, P6-mtp1 repetition 4, grew VmSwap by 486 MiB without a flag). Drift none. Polls: busy 7.2 % (server 6.3 %), one sample 33.0 % of which the server 33.6 % (the end canary); MemAvailable at least 22.5 GiB.

### Re-run s2a-128K (--rerun-flagged, once): 2026-11-10 19:50:42Z to about 20:10Z
- 5 units re-run (attempt 2): P2-mtp2 repetitions 0, 1 and P2-mtp3 repetitions 0, 1, 2. **3 clean, 2 still paging-flagged** (P2-mtp2 repetition 0 with swap activity 749 MiB, repetition 1 with -6 MiB; both within the changed criterion f limit of 1,024 MiB). Drift none. Polls: busy 11.7 % (server 10.3 %), one sample 41.1 % of which the server 40.8 % (the end canary); MemAvailable at least 20.6 GiB.

## Stage 2a2 sessions (s2a2-32K, s2a2-64K, s2a2-128K), Phase 0 conditions, 2026-11-10T22:34Z
- Code: tree clean at the start; commits `b9b7ec5` (re-run summary writer fix), `93a00b0` (summary repair), `3a46517` (borrowed draft lengths), `a8417aa` (2a decision), `b6322a7` (2a2 spec). Spec `configs/sweeps/stage2-2a2.toml` (10 cells: 32K 3, 64K 3, 128K 4; `--cache-ram 2048`).
- pgrep llama-server: empty. GPU lock: free. nvidia-smi memory.used: 3 MiB. MemAvailable: 25.4 GiB. Swap in use: 1.61 GiB of 30.46 GiB.
- CPU busy over 10 s: 0.28 %. Load average (1 min): 0.21.
- Top 5 by memory (names): claude 0.38 GiB, antigravity-ide 0.36 GiB, antigravity-ide 0.32 GiB, antigravity-ide 0.29 GiB, cosmic-comp 0.22 GiB.
- Top 5 by CPU, ps lifetime average (names): antigravity-ide 1.4 %, claude 1.3 %, cosmic-comp 1.0 %, antigravity-ide 0.5 %, kswapd0 0.2 %.
- Desktop apps open (names): antigravity-ide claude cosmic-comp kilo 
- `missioncenter` (system monitor app) is no longer open.

### Session s2a2-32K result (2026-11-10 22:35:03Z to 22:53:33Z)
- Duration 18.5 min (sweep-check estimate for the three sessions together: 3.22 h). Runner exit 0, state complete, `systemd-inhibit` active, one run. Gate criteria a to f PASS.
- Cells: 3 of 3 complete (P2-32K mtp0, P2-32K mtp2, P6-32K mtp2), none `did_not_fit`. **No flags at all** (0 of 15 measured attempt-1 windows paging-flagged; no window with swap activity above 1,024 MiB); drift none.
- P6-32K-mtp2 took its expert-cache size from the runner's probe cache (`probe_cache_hit`, key `69cf427da1b214de5028`, 10,752 MiB, the same key as the 2a probe: same config, llama.cpp commit, model and GPU), not from a new binary search; minimum free VRAM 1,131 MiB, the same as in 2a.
- Lowest minimum free VRAM 567 MiB (P2-mtp0), P2-mtp2 615 MiB, P6-mtp2 1,131 MiB. Runner idle gate: first check passed every time (busy at most 0.51 %), no idle waits, no retries; lowest MemAvailable 22.3 GiB (telemetry). Polls: server's share 20.3 % at most, everything else at most 0.7 %. Highest CPU Tctl 75 °C, GPU 67 °C.
