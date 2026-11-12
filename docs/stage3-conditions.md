# Stage 3 and Stage 4 machine conditions

Records the machine conditions of the Stage 3 and Stage 4 sessions (WP13). Gate G3 applies in full here: the desktop apps are closed
(`scripts/check-quiet.sh`, blocklist in `configs/quiet-check.toml`). Only process **names** are recorded, never window titles, URLs or
command-line arguments. Fill one block per session **before** it starts (copy the template), and add the end-of-session line when it is complete.

## Template (copy for each session)
```
## Session <id> (<what>), <date>, before the start
- `scripts/check-quiet.sh` output, verbatim (exit code <0|1>):
  <paste: "quiet-machine check: N processes (names only)", offenders, warnings, the CPU idle line, RESULT>
- `pgrep -a llama-server`: <empty>. GPU lock (`.locks/gpu.lock`): <free>.
- `nvidia-smi`: memory.used <N> MiB of 16,311 MiB; compute processes: <none>.
- MemAvailable: <N> GiB. Swap in use: <N> GiB. Mains power: <yes>. `git status --short`: <empty>. Code commit: <hash>.
- Anything else running (names): <none besides the terminal with Claude Code>.

## Session <id>, end
- Duration <min> (estimate <min>); runner exit <0>; state <complete>; gate (`stage3 gate`): <PASS|FAIL, criteria>; re-run pass: <units re-run, clean/flagged after>.
- Stock windows paging-flagged (reported only): <n of N>; tuned and canary windows: <n of N>.
```

(No session has been run yet. The Part C functional checks of WP13 used the desktop apps open and are not recorded here: they are functional-test data.)

---

## Phase 0 (all Stage 3 sessions), 2026-11-12, machine check before the first session
- `scripts/check-quiet.sh` output, verbatim (exit code 0):
  ```
  quiet-machine check: 457 processes (names only)
  no blocklisted app is running
  CPU idle check (informational): busy 0.2% over 10 s (the runner's precondition needs below 10%)
  RESULT: QUIET
  ```
- `pgrep -a llama-server`: empty. GPU lock (`.locks/gpu.lock`, `flock -n`): free.
- `nvidia-smi`: memory.used 3 MiB of 16,311 MiB; compute processes: none.
- MemAvailable: 27.2 GiB (28,461,792 kB at the first look). Swap in use: 0.72 GiB (zram, leftover from before the quiet period). 1-minute load average: 0.29. CPU busy over a 10-second sample: 0.3%.
  Mains power: desktop PC (no battery in `/sys/class/power_supply`); Zack was asked to plug in. `git status --short`: empty. HEAD: `8096461` (`Plan v1.8`).
- Top 5 by memory (names, resident): claude 359 MiB, cosmic-comp 274 MiB, ghostty 204 MiB, cosmic-bg 43 MiB, keyd 39 MiB.
- Top 5 by CPU (names): claude 3.8%, ghostty 1.2%, cosmic-comp 0.9%, kswapd0 0.1%, Xwayland 0.1%.
- Anything else running (names): none besides the terminal (ghostty) with Claude Code and the desktop environment (cosmic-*).

## Session stage3-32K (stock-32K and tuned-32K), 2026-11-12, before the start
- `scripts/check-quiet.sh` (exit 0): `quiet-machine check: 457 processes (names only)`; `no blocklisted app is running`; `CPU idle check (informational): busy 0.2% over 10 s`; `RESULT: QUIET`.
- `pgrep -a llama-server`: empty. GPU lock: free.
- `nvidia-smi`: memory.used 3 MiB of 16,311 MiB; compute processes: none.
- MemAvailable: 27.2 GiB. Swap in use: 0.72 GiB. CPU busy (10 s): 0.2%. Load (1 min): 0.59. Mains power: yes (desktop). `git status --short`: only this file (uncommitted conditions log; code tree clean). Code commit: `8096461`.
- Top 5 by memory: claude, cosmic-comp, ghostty, cosmic-bg, keyd. Top 5 by CPU: claude, ghostty, cosmic-comp, kswapd0, Xwayland.
- Anything else running (names): none besides the terminal with Claude Code.

## Session stage3-32K, end
- Duration 18.4 min, 11:53:01Z to 12:11:25Z (estimate 18 min); runner exit 0; state complete; inhibit active (`systemd-inhibit --what=sleep:idle`, not refused); gate (`stage3 gate`): PASS (a to f).
- Cells: 4 of 4 complete (canary-start, tuned-32K, stock-32K, canary-end). Flags: stock-32K 7 request flags, all `paging`, all repetition 3 (cell-level `paging`); tuned-32K none; canaries none. Drift: no flag. Idle waits 0 s, 1 attempt per cell, no retries.
- Lowest min free VRAM: 1,329 MiB (both canaries); measured cells 1,385 MiB (stock) and 1,379 MiB (tuned).
- Quiet check at 3 polls (12:00, 12:08, 12:15Z): QUIET each time; no quiet condition violated. Highest CPU busy at a poll 17.7% (12:08Z, llama-server decoding); busiest other processes then: ghostty 2.3%, cosmic-comp 0.9%, kswapd0 0.1%. Lowest MemAvailable: 20.0 GiB at the 12:08Z poll (server loaded), 27.1 GiB lowest at a cell's preconditions.
- Stock windows paging-flagged (reported only): 1 of 5 (repetition 3: 6,321 MiB swap growth, 12,456 major faults); tuned and canary windows: 0 of 11 (largest swap growth 145 MiB, most faults 963). Re-run pass: see the re-run entry below.

## Session stage3-32K, re-run pass (once, `--rerun-flagged stage3-32K`)
- Started 12:16:21Z after `check-quiet.sh` (QUIET), MemAvailable 27.9 GiB, no llama-server, GPU lock free; ended 12:24:35Z (8.2 min), runner exit 0, state complete. Poll at 12:23Z: QUIET, MemAvailable 25.5 GiB, CPU 6.4%.
- Units re-run: 1 (stock-32K repetition 3, paging). Result: attempt 2 clean (0 major faults, no flag); resolved 1, still flagged 0. Re-run canaries: start clean (3 windows, 0 faults), end 1 of 3 windows paging-flagged (repetition 115, 1,090 major faults), drift: no flag for main or rerun. No llama-server left.

## Session stage3-64K (stock-64K and tuned-64K), 2026-11-12, before the start
- `scripts/check-quiet.sh` (exit 0): `quiet-machine check: 427 processes (names only)`; `no blocklisted app is running`; `CPU idle check (informational): busy 0.2% over 10 s`; `RESULT: QUIET`.
- `pgrep -a llama-server`: empty. GPU lock: free.
- `nvidia-smi`: memory.used 3 MiB of 16,311 MiB; compute processes: none.
- MemAvailable: 27.9 GiB. Swap in use: 1.02 GiB. CPU busy (10 s): 0.2%. Load (1 min): 1.73 (lagging the 32K re-run). Mains power: yes (desktop). `git status --short`: empty. Code commit: `a80b2dd`.
- Top 5 by memory: claude, cosmic-comp, ghostty, cosmic-bg, keyd. Top 5 by CPU: claude, ghostty, cosmic-comp, kswapd0, Xwayland.
- Anything else running (names): none besides the terminal with Claude Code.

## Session stage3-64K, end
- Duration 26.4 min, 12:25:12Z to 12:51:33Z (estimate 26 min); runner exit 0; state complete; inhibit active (listed by `systemd-inhibit --list`, not refused); gate (`stage3 gate`): PASS (a to f; f at 36.4% of tuned and canary windows, limit 40%).
- Cells: 4 of 4 complete. Flags: tuned-64K 28 request flags, all `paging` (repetitions 1 to 4, every request of those repetitions); stock-64K none; canaries none. Drift: no flag. Idle waits 0 s, 1 attempt per cell, no retries.
- Lowest min free VRAM: 1,021 MiB (tuned-64K); stock-64K 1,355 MiB; canaries 1,329 MiB.
- Quiet check at 3 polls (12:32, 12:39, 12:47, 12:54Z): QUIET each time; no quiet condition violated. Highest CPU busy at a poll 6.6% (llama-server); no non-project process above 1%. Lowest MemAvailable at a poll: 19.4 GiB (12:47Z, server loaded); lowest at a cell's preconditions 27.8 GiB.
- Stock windows paging-flagged (reported only): 0 of 5 (largest swap growth 20 MiB, 60 faults). Tuned and canary windows: 4 of 11, all in tuned-64K (largest swap growth 586 MiB, most major faults 47,576). This is the reverse of what plan 5.4 expected (stock paging, tuned clean).

## Session stage3-64K, re-run pass (once, `--rerun-flagged stage3-64K`)
- Started 12:54:56Z after `check-quiet.sh` (QUIET), MemAvailable 27.9 GiB, no llama-server, GPU lock free; ended 13:06:31Z (11.6 min), runner exit 0, state complete. Polls 13:02Z and 13:09Z: QUIET, CPU 9.1% (llama-server) and 0.2%, MemAvailable 24.5 and 27.9 GiB.
- Units re-run: 4 (tuned-64K repetitions 1 to 4, paging). Result: all 4 attempt-2 windows clean (0 major faults, no thermal flag); resolved 4, still flagged 0. Re-run canaries: 6 of 6 windows clean; drift: no flag for main or rerun. min free VRAM of the re-run tuned cell 1,021 MiB. No llama-server left.

## Session stage3-128K (stock-128K and tuned-128K), 2026-11-12, before the start
- `scripts/check-quiet.sh` (exit 0): `quiet-machine check: 426 processes (names only)`; `no blocklisted app is running`; `CPU idle check (informational): busy 0.2% over 10 s`; `RESULT: QUIET`.
- `pgrep -a llama-server`: empty. GPU lock: free.
- `nvidia-smi`: memory.used 3 MiB of 16,311 MiB; compute processes: none.
- MemAvailable: 27.9 GiB. Swap in use: 1.03 GiB. CPU busy (10 s): 0.2%. Load (1 min): 0.48. Mains power: yes (desktop). `git status --short`: empty. Code commit: `b5b7396`.
- Top 5 by memory: claude, cosmic-comp, ghostty, cosmic-bg, keyd. Top 5 by CPU: claude, ghostty, cosmic-comp, kswapd0, Xwayland.
- Anything else running (names): none besides the terminal with Claude Code.

## Session stage3-128K, end
- Duration 45.9 min, 13:10:03Z to 13:55:58Z (estimate 46 min); runner exit 0; state complete; inhibit active (listed by `systemd-inhibit --list`, not refused); gate (`stage3 gate`): PASS (a to f; f 0 of 11 tuned and canary windows).
- Cells: 4 of 4 complete. Flags: stock-128K 14 request flags, all `paging` (repetitions 1 and 3); tuned-128K none; canaries none. Drift: no flag. Idle waits 0 s, 1 attempt per cell, no retries.
- Lowest min free VRAM: 1,211 MiB (tuned-128K); stock-128K 1,367 MiB; canaries 1,329 MiB.
- Quiet check at 7 polls (13:17 to 13:53Z): QUIET each time; no quiet condition violated. Highest CPU busy at a poll 20.2% (13:46Z, llama-server decoding); busiest other processes then: ghostty 2.4%, cosmic-comp 0.9%, kswapd0 0.1%. Lowest MemAvailable at a poll: 19.0 GiB (13:39Z, server loaded); lowest at a cell's preconditions 27.75 GiB.
- Stock windows paging-flagged (reported only): 2 of 5 (repetitions 1 and 3; largest swap growth 3,420 MiB, most major faults 2,657); tuned and canary windows: 0 of 11 (largest swap growth 0 MiB, 0 faults).
