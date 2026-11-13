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

## Session stage4, polls (quiet check + sweep-status + light sample, ~7 min cadence)
- 22:49:54Z: QUIET (exit 0; 459 processes; busy 6.3% over 10 s, llama-server decoding). `state=running`, tuned-64K
  repetition 1 (A@49152); canary-start complete, unflagged. Request flags: 7 `paging`, all tuned-64K repetition 1
  (`records.jsonl`) — the known MTP file-page faulting pattern (D2; Stage 3 64K had 7 per flagged repetition).
  MemAvailable 23.9 GiB (25,069,172 kB). GPU 15,290 MiB, only the project's llama-server (pid 1926919). Top CPU
  (names): llama-server 127%, python 10.1%, claude 1.9%. ETA ~19 min. No stop rule fired.
- 22:57:53Z: QUIET (exit 0; 460 processes; busy 6.3% over 10 s). `state=running`, tuned-64K complete, stock-64K
  repetition 1 (A@49152). Request flags: 21 `paging`, all tuned-64K, repetitions 1, 3 and 5 (7 each,
  `records.jsonl`); 3 of 5 tuned windows flagged, canary-start unflagged → 3 of 11 tuned+canary attempt-1 windows
  (27.3%, gate f limit 40%), canary-end pending. MemAvailable 25.4 GiB (26,645,924 kB). GPU 14,956 MiB, only the
  project's llama-server (pid 1927276, fresh server for the stock cell). Top CPU (names): llama-server 152%,
  python 5.1%, claude 1.6%. ETA ~9 min. No stop rule fired.
- 23:05:39Z: QUIET (exit 0; 460 processes; busy 6.3% over 10 s). `state=running`, stock-64K repetition 3
  (A@32768). Request flags unchanged: 21 `paging`, all tuned-64K; stock unflagged so far. MemAvailable 19.2 GiB
  (20,173,400 kB) **with the stock server loaded** — the runner's own cell preconditions all passed well above the
  20 GiB abort threshold (`events.jsonl`: canary-start 26.48 GiB, tuned-64K 27.62 GiB, stock-64K 27.71 GiB, all
  `ok: true`, no aborts/warnings); the loaded-server dip matches the accepted Stage 3 pattern (19.0–19.4 GiB at
  loaded polls, `docs/stage3-conditions.md`). Swap in use 1.0 GiB (1,047,840 kB; 0.63 GiB at start). GPU 14,956 MiB,
  only the project's llama-server (pid 1927276). Top CPU (names): llama-server 150%, python 3.5%, claude 1.4%.
  ETA ~9 min. No stop rule fired.
- 23:13:42Z: QUIET (exit 0; 456 processes; busy 17.7% over 10 s — llama-server decoding, informational only; the
  runner's idle gate applies at cell preconditions, as in Stage 3's 17.7%/20.2% loaded polls). `state=running`,
  stock-64K repetition 5 (A@49152, final repetition). Request flags unchanged: 21 `paging`, all tuned-64K; stock
  unflagged. MemAvailable 19.3 GiB (20,195,508 kB, stock server loaded; preconditions 26.5–27.7 GiB, see poll 3).
  GPU 14,956 MiB, only the project's llama-server (pid 1927276). Top CPU (names): llama-server 148%, python 2.6%,
  claude 1.3%. ETA ~9 min (canary-end after repetition 5). No stop rule fired.
- 23:21:14Z: QUIET (exit 0; 451 processes; busy 0.0% over 10 s). `state=complete`, runner exited, cells 2/2,
  drift main no flag. MemAvailable 27.9 GiB (29,217,512 kB, server unloaded). GPU 3 MiB, no compute processes;
  `pgrep -x llama-server` empty. Top CPU (names): claude 1.2%, cosmic-comp 1.0%, ghostty 0.4%. No stop rule fired.

## Session stage4, end
- Duration 38.3 min, 22:42:12Z to 23:20:30Z (runbook estimate 26 min, 29 min with 10%; spec-check estimate
  `"total_h": 0.58` ≈ 35 min); runner exit 0 (`data/logs/jobs/sweep-stage4-20261113T224212Z/status.json`:
  `"exit_code": 0, "state": "done"`); state complete; inhibit active (`session.json` inhibit tag
  `smallpc-sweep-stage4-1794609732`, not refused); gate (`stage3 gate`): **PASS (a to f**; f at 27.3% of tuned and
  canary windows, limit 40%; no flagged window above 1,024 MiB swap growth).
- Start provenance (`session.json` git): commit `1307244870bf817744736ea42794ea9af803a008`, `"dirty": false`,
  `"dirty_paths": []`; `allow_dirty: false`. R3 re-verified at that HEAD before the launch (PASS).
- Cells: 4 of 4 complete (canary-start, tuned-64K, stock-64K, canary-end). Flags: tuned-64K 21 request flags, all
  `paging` (repetitions 1, 3, 5 — every request of those repetitions; cell-level `paging`); stock-64K none;
  canaries none. Drift: no flag (main `pp_fresh_16k` relative difference 0.00046, threshold 0.05). Idle waits 0 s
  at all four preconditions (26.48 / 27.62 / 27.71 / 27.77 GiB MemAvailable, all `ok: true`), 1 attempt per cell,
  no retries.
- Measured phase times (`cells/*.json` instances, attempt 1): stock-64K measure 1,197.08 s / 5 repetitions
  (239.4 s per repetition; the runbook's Stage 1 basis was 153.3), tuned-64K measure 499.88 s / 5 (100.0 s per
  repetition; Stage 2 basis 75.5), canaries measure 167.23 s and 167.88 s. The longer stock repetitions explain
  the duration above the estimate; recorded as measured, for T-008's S2 check.
- Lowest min free VRAM (after warmup): 1,031 MiB (tuned-64K); stock-64K 1,355 MiB; canaries 1,329 MiB.
- Quiet check at 5 polls (22:49, 22:57, 23:05, 23:13, 23:21Z): QUIET each time; no quiet condition violated.
  Highest CPU busy at a poll 17.7% (23:13Z, llama-server decoding); lowest MemAvailable at a poll 19.2 GiB
  (23:05Z, stock server loaded); lowest at a cell's preconditions 26.48 GiB.
- Stock windows paging-flagged (reported only): 0 of 5 (largest swap growth 0 MiB, most major faults 41). Tuned
  and canary windows: 3 of 11, all in tuned-64K repetitions 1, 3, 5 (largest swap growth 220 MiB, most major
  faults 6,751) — the known MTP file-page faulting of D2, as in Stage 3 64K (which flagged repetitions 1 to 4).
- Gate output, verbatim (exit 0):
  ```
  gate for stage3 session stage4: PASS
    [PASS] a: the runner exited with 0 and the state is complete: state 'complete'; job exit code 0, state 'done'
    [PASS] b: every cell has a final record: 2 of 2 cells final
    [PASS] c: no accounting, warm_prefill or cache_miss flag: none
    [PASS] d: no thermal or drift flag: thermal units none; drift {'main': None}
    [PASS] e: no did_not_fit with reason startup_failure, startup_timeout, crash_mid_cell, oom_runtime: did_not_fit: none
    [PASS] f: at most 40% of the tuned and canary windows paging-flagged and no flagged tuned or canary window above 1024 MiB of swap growth (stock windows excluded): 3 of 11 attempt-1 windows of the tuned cells and the canaries paging-flagged (27.3%, limit 40%); flagged windows above 1024 MiB of swap growth: none. Stock cells (reported, never fail the gate): 0 of 5 windows paging-flagged
    paging-flagged windows per cell (attempt 1; stock cells are reported only):
      canary-end [canary]: 0 of 3; largest swap growth 0 MiB; most major faults 0
      canary-start [canary]: 0 of 3; largest swap growth -0 MiB; most major faults 383
      stock-64K [stock]: 0 of 5; largest swap growth 0 MiB; most major faults 41
      tuned-64K [tuned]: 3 of 5 (repetitions [0, 2, 4]); largest swap growth 220 MiB; most major faults 6751
    next: PASS: run the one `--rerun-flagged` pass for this session (only if a unit is flagged), then the next session
  ```
- Re-run pass: see the re-run entry below (3 flagged tuned-64K units).