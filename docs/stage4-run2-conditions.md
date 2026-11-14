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

## Session stage4-run2, launch
- Launch: `scripts/run-sweep.sh configs/sweeps/stage4.toml --session-id stage4-run2` at 2026-11-14T14:30:49Z from HEAD
  `c4bdc4d` (whole tree clean; R3 re-verified at that HEAD: PASS). The start commit `c4bdc4d` adds only this log and the kit
  bookkeeping on top of `9cc1c16` — no code, config or data change. Job dir:
  `data/logs/jobs/sweep-stage4-run2-20261114T143049Z`; runner pid 9210, `state=running`, first cell canary-start
  (phase=preconditions at 14:30:50Z). Session id written to `docs/recon/stage4-session-run2.txt` (run 1's
  `docs/recon/stage4-session.txt` untouched; the two files differ).
- Start provenance (`session.json` git): commit `c4bdc4db4a4378282c68bd858a718ece74710c09`, `"dirty": false`,
  `"dirty_paths": []`; `allow_dirty: false`. `spec_sha256` `6a11e6b1…` identical to run 1's (same committed spec);
  `cell_order` tuned-64K, stock-64K (same seeded shuffle as run 1).

## Session stage4-run2, polls (quiet check + sweep-status + light sample + R7 link sample, ~7 min cadence)
- 14:39:12Z: QUIET (exit 0; 420 processes; busy 10.9% over 10 s, llama-server decoding — informational; the runner's idle
  gate applies at cell preconditions, as in run 1's loaded polls). **Link (R7): 5 of 5 samples "4, 8"** while generating
  (utilization.gpu 93%, power.draw 75.91 W). `state=running`, tuned-64K repetition 4 (A@32768); canary-start complete.
  Request flags: none (41 requests, `records.jsonl` via sweep-status). MemAvailable 24.6 GiB (25,841,748 kB, tuned server <!-- derived: kB / 1048576 -->
  loaded). Swap in use 39.5 MiB (40,460 kB). GPU 15,290 MiB, only the project's llama-server (pid 9624, 15,278 MiB).
  Top CPU (names): llama-server 144%, python 9.2%, claude 0.7%, ghostty 0.2%. ETA ~19 min. No stop rule fired.
- 14:47:51Z: QUIET (exit 0; 421 processes; busy 6.3% over 10 s). **Link (R7): 5 of 5 samples "4, 8"** while generating
  (utilization.gpu 97%, power.draw 74.60 W). `state=running`, tuned-64K complete (cells 1/2), stock-64K repetition 2
  (A@49152). Request flags: still none (64 requests) — tuned-64K finished all 5 repetitions unflagged (run 1 had 3 of 5
  paging-flagged). MemAvailable 20.4 GiB (21,420,728 kB, stock server loaded; the loaded dip matches the accepted Stage 3 / <!-- derived: kB / 1048576 -->
  run 1 pattern; the runner's cell preconditions all passed earlier). Swap in use 3.2 GiB (3,404,976 kB; 39.5 MiB at poll 1) — <!-- derived: SwapTotal - SwapFree, kB / 1048576 -->
  growth under the stock cell, the expected stock `--cache-ram 8192` paging (runbook §1.5: reported, never fails the gate).
  GPU 14,956 MiB, only the project's llama-server (pid 9936, fresh server for the stock cell). Top CPU (names):
  llama-server 174%, python 4.7%, claude 0.7%, ghostty 0.2%. ETA ~7 min. No stop rule fired.
- 14:55:43Z: QUIET (exit 0; 421 processes; busy 6.3% over 10 s). Link (R7), 5 samples at 1 s: **"4, 8", "2, 8", "2, 8",
  "1, 8", "4, 8"**; utilization.gpu 95%, power.draw 67.67 W queried immediately after the five samples. `state=running`,
  cells 2/2 done, canary-end repetition 104 (A@16384). Request flags: 7 `paging` (90 requests). MemAvailable 26.1 GiB <!-- derived: kB / 1048576 -->
  (27,351,312 kB, canary-end server loaded). Swap in use 430 MiB (440,264 kB; down from 3.2 GiB after the stock server <!-- derived: SwapTotal - SwapFree -->
  stopped). GPU 14,982 MiB, only the project's llama-server (pid 10446). Top CPU (names): llama-server 136%, python 5.8%,
  claude 0.7%, ghostty 0.2%. ETA ~0 min.
- **R7 investigation of the poll-3 link samples (executor judgement, flagged for the post-review).** The poll's five samples
  were not per-sample utilization-stamped, so "2, 8" / "1, 8" during a generating poll raised the R7 stop question. A
  30-sample burst at 2 Hz with per-sample utilization was taken immediately (14:56:52Z to 14:57:07Z, canary-end still
  running): **every sample at utilization ≥ 38% read "4, 8"** (65, 65, 64, 65, 38%, power.draw 107.8 to 75.5 W); as the
  request ended and utilization fell to 0% (power decaying 39 → 28 → 17 → 11 → 8 W), the link held "4, 8" for about 8 s,
  then downshifted "2, 8" → "1, 8" **only at 0% utilization**. The burst caught the downshift live: it is the documented
  idle downshift (`docs/recon/pcie-link.md`: idle Gen1 x8, max Gen4; T-020's pre-load "1, 8" sample was likewise excluded
  as not an under-load reading), with Gen2 an intermediate state of the transition. Poll 3's low readings therefore fell in
  an idle gap between canary requests, not while generating. Under-load link readings across the session: poll 1 5/5
  "4, 8" (93%), poll 2 5/5 "4, 8" (97%), poll 3 2/5 "4, 8" plus the burst 5/5 "4, 8" at 38–65% — **every confirmed-generation
  sample read "4, 8"**. R7's stop condition ("anything other than 4, 8 while a server is generating") was not met; no stop
  rule fired. Idle readings are recorded here as idle and never averaged into the data. The session reached `state=complete`
  at 14:56:54Z, before any stop decision would have been actionable. If the review reads R7 more strictly (any non-4, 8
  sample at a generating poll, regardless of per-sample load), this entry is the escalation point.
- 14:56:54Z: `state=complete`, runner exited (job `status.json`: `"exit_code": 0, "state": "done"`, end 14:56:54Z),
  cells 2/2, drift main no flag. Duration 26.1 min (14:30:49Z to 14:56:54Z; runbook estimate 26 min, 29 min with 10%). <!-- derived: job status.json start/end -->
  Request flags: 7 `paging`, all stock-64K repetition 2 (0-indexed), attempt 1 (`records.jsonl`); tuned-64K 0 flags,
  canaries 0 flags. Stock paging is reported only and never fails the gate (runbook §1.5, §4f).

## Session stage4-run2, gate before the re-run (S3)
- `GATE_CMD` with `SESSION=stage4-run2` (`docs/recon/commands.env`), exit 0: **PASS (a to f)**. Verbatim:
  ```
  gate for stage3 session stage4-run2: PASS
    [PASS] a: the runner exited with 0 and the state is complete: state 'complete'; job exit code 0, state 'done'
    [PASS] b: every cell has a final record: 2 of 2 cells final
    [PASS] c: no accounting, warm_prefill or cache_miss flag: none
    [PASS] d: no thermal or drift flag: thermal units none; drift {'main': None}
    [PASS] e: no did_not_fit with reason startup_failure, startup_timeout, crash_mid_cell, oom_runtime: did_not_fit: none
    [PASS] f: at most 40% of the tuned and canary windows paging-flagged and no flagged tuned or canary window above 1024 MiB of swap growth (stock windows excluded): 0 of 11 attempt-1 windows of the tuned cells and the canaries paging-flagged (0.0%, limit 40%); flagged windows above 1024 MiB of swap growth: none. Stock cells (reported, never fail the gate): 1 of 5 windows paging-flagged
    paging-flagged windows per cell (attempt 1; stock cells are reported only):
      canary-end [canary]: 0 of 3; largest swap growth 0 MiB; most major faults 0
      canary-start [canary]: 0 of 3; largest swap growth 0 MiB; most major faults 0
      stock-64K [stock]: 1 of 5 (repetitions [2]); largest swap growth 2752 MiB; most major faults 5562
      tuned-64K [tuned]: 0 of 5; largest swap growth 0 MiB; most major faults 0
    next: PASS: run the one `--rerun-flagged` pass for this session (only if a unit is flagged), then the next session
  ```
- R2 not needed (the gate passed; tuned-64K has no paging flags at all). One flagged unit → the one `--rerun-flagged`
  pass (S4): stock-64K repetition 2, attempt 2 on a fresh server with its own canaries.

## Session stage4-run2, re-run pass (once, `--rerun-flagged stage4-run2`)
- Started 14:59:35Z after `check-quiet.sh` (QUIET, exit 0; 412 processes; busy 0.2% over 10 s), MemAvailable
  28.5 GiB (29,902,388 kB), no llama-server, GPU lock free, GPU 2 MiB; idle link Gen1 x8, max Gen4 (the documented <!-- derived: kB / 1048576 -->
  idle downshift). Job dir: `data/logs/jobs/rerun-stage4-run2-20261114T145935Z`. Units to re-run: 1 (stock-64K
  repetition 2, paging). R7 link sampling continues at every poll while generating.
- Poll 15:06:48Z: QUIET (exit 0; 415 processes; busy 20.2% over 10 s, llama-server decoding — informational, as in
  Stage 3's loaded polls). **Link (R7): 5 of 5 samples "4, 8"**, per-sample utilization stamped: 0, 0, 0, 98, 98%
  (the 0% samples are an idle gap between canary requests, the link still at 4, 8; the 98% samples are generation).
  Re-run `state=running` (pid 11147), canary-rerun-end repetition 113 (A@16384); the re-run stock unit and
  canary-rerun-start already done (records: 118 requests, 6 cell records). Request flags unchanged: 7 `paging`, all
  attempt-1 — no new flags on the attempt-2 stock window or the re-run canaries. MemAvailable 26.6 GiB (27,866,304 kB, <!-- derived: kB / 1048576 -->
  server loaded). Swap in use 404 MiB (413,572 kB). GPU 14,982 MiB, only the project's llama-server (pid 11655).
  Top CPU (names): llama-server 117%, python 17.6%, claude 0.8%, ghostty 0.2%. ETA ~0 min. No stop rule fired.
- Ended 15:08:49Z (9.2 min; started 14:59:35Z), runner exit 0 (job `status.json`: `"exit_code": 0, "state": "done"`), <!-- derived: rerun job start/end -->
  state complete. Units re-run: 1 (stock-64K repetition 2, paging). Result: the attempt-2 window is clean — 0 major
  faults, swap activity 0.0 MiB (`cells/stock-64K-22dc1178.json`, attempt-2 window); still flagged 0 (the session's flag
  total stays at the 7 attempt-1 request flags). Re-run canaries: 6 of 6 windows clean (0 major faults, gate output
  below); drift: no flag for main or rerun. Attempt-2 measure 148.78 s; min free VRAM of the re-run stock cell
  1,355 MiB. End checks 15:09:37Z: QUIET (exit 0; 410 processes; busy 0.1% over 10 s), MemAvailable 28.5 GiB <!-- derived: kB / 1048576 -->
  (29,899,500 kB), `pgrep -x llama-server` empty, GPU lock free, GPU 2 MiB, no compute processes; idle link Gen1 x8,
  max Gen4. stock-64K now has 5 clean units and tuned-64K has 5 clean units — the R1 fallback is not needed for either
  cell (T-008's S2 check confirms).
- Gate after the re-run (`GATE_CMD`, exit 0): **PASS (a to f**; f at 0 of 17 attempt-1 tuned and canary windows = 0.0%,
  limit 40%; the denominator now includes the six re-run canary windows). Verbatim:
  ```
  gate for stage3 session stage4-run2: PASS
    [PASS] a: the runner exited with 0 and the state is complete: state 'complete'; job exit code 0, state 'done'
    [PASS] b: every cell has a final record: 2 of 2 cells final
    [PASS] c: no accounting, warm_prefill or cache_miss flag: none
    [PASS] d: no thermal or drift flag: thermal units none; drift {'main': None, 'rerun': None}
    [PASS] e: no did_not_fit with reason startup_failure, startup_timeout, crash_mid_cell, oom_runtime: did_not_fit: none
    [PASS] f: at most 40% of the tuned and canary windows paging-flagged and no flagged tuned or canary window above 1024 MiB of swap growth (stock windows excluded): 0 of 17 attempt-1 windows of the tuned cells and the canaries paging-flagged (0.0%, limit 40%); flagged windows above 1024 MiB of swap growth: none. Stock cells (reported, never fail the gate): 1 of 5 windows paging-flagged
    paging-flagged windows per cell (attempt 1; stock cells are reported only):
      canary-end [canary]: 0 of 3; largest swap growth 0 MiB; most major faults 0
      canary-rerun-end [canary]: 0 of 3; largest swap growth 0 MiB; most major faults 0
      canary-rerun-start [canary]: 0 of 3; largest swap growth 0 MiB; most major faults 0
      canary-start [canary]: 0 of 3; largest swap growth 0 MiB; most major faults 0
      stock-64K [stock]: 1 of 5 (repetitions [2]); largest swap growth 2752 MiB; most major faults 5562
      tuned-64K [tuned]: 0 of 5; largest swap growth 0 MiB; most major faults 0
    next: PASS: run the one `--rerun-flagged` pass for this session (only if a unit is flagged), then the next session
  ```

## Session stage4-run2, end summary
- Duration: main 26.1 min (14:30:49Z to 14:56:54Z), re-run 9.2 min (14:59:35Z to 15:08:49Z); both runners exit 0; <!-- derived: job status.json start/end pairs -->
  inhibit active for both (tags `smallpc-sweep-stage4-run2-1794666649`, `smallpc-sweep-stage4-run2-1794668375`, not refused).
- Start provenance (`session.json` git): commit `c4bdc4db4a4378282c68bd858a718ece74710c09`, `"dirty": false`,
  `"dirty_paths": []`; `allow_dirty: false`. R3 re-verified at that HEAD before the launch (PASS). The re-run ran at the
  same code commit `c4bdc4d` (no "code commit changed" warning, unlike run 1).
- Cells: 4 of 4 complete (canary-start, tuned-64K, stock-64K, canary-end) plus the attempt-2 stock instance and the two
  re-run canaries. Flags: stock-64K 7 request flags, all `paging` (repetition 2, attempt 1 — every request of that
  repetition); tuned-64K none; canaries none. Drift: no flag (main `pp_fresh_16k` relative difference 0.00406, rerun
  0.00373, threshold 0.05; `session.json`). Idle waits 0.0 s at all seven preconditions (27.93 to 28.47 GiB
  MemAvailable, all `ok: true`, busy 0.03 to 0.84%), 1 attempt per cell, no retries.
- Measured phase times (`cells/*.json` instances, attempt 1): stock-64K measure 750.30 s / 5 repetitions (150.1 s per <!-- derived: measure / 5 -->
  repetition; the runbook's Stage 1 basis was 153.3), tuned-64K measure 373.05 s / 5 (74.6 s per repetition; Stage 2 <!-- derived: measure / 5 -->
  basis 75.5), canaries measure 122.04 s and 123.36 s; re-run canaries 124.39 s and 121.88 s; attempt-2 stock 148.78 s.
  Run 2's pace matches the runbook bases, unlike run 1 (stock 239.4 s, tuned 100.0 s per repetition,
  `docs/stage4-conditions.md`) — recorded as measured; run 1 is the excluded diagnostic (R5), and the kernel/driver
  confound above applies to any comparison.
- Lowest min free VRAM (after warmup): 1,019 MiB (tuned-64K); stock-64K 1,353 MiB (attempt 1) / 1,355 MiB (attempt 2);
  canaries 1,329 MiB.
- Quiet check at the start, before the re-run, at the end and at 4 polls (14:39, 14:47, 14:55, 15:06Z): QUIET each time
  (exit 0); no quiet condition violated. Highest CPU busy at a poll 20.2% (15:06Z, llama-server decoding);
  lowest MemAvailable at a poll 20.4 GiB (14:47Z, stock server loaded — the accepted Stage 3 / run 1 loaded-dip
  pattern); lowest at a cell's preconditions 27.93 GiB.
- Stock windows paging-flagged (reported only): 1 of 5 (repetition 2; largest swap growth 2,752 MiB, most major faults
  5,562); its attempt-2 re-run is clean (0 major faults, 0.0 MiB swap activity). Tuned and canary windows: 0 of 11
  attempt-1 flagged (0 of 17 including the re-run canaries) — no MTP file-page faulting this run (run 1 and Stage 3 64K
  had it; D2). No stop rule fired at any point.
- Link (R7) summary: every confirmed-generation sample read "4, 8" — poll 1 5/5 (93% util), poll 2 5/5 (97%),
  poll-3 investigation burst 5/5 (38–65%), re-run poll 5/5 (per-sample util 0/0/0/98/98%). Non-4, 8 readings occurred
  only at 0% utilization (idle gaps and the idle end state), the documented idle downshift; see the R7 investigation
  entry above. Nothing was averaged into the data.