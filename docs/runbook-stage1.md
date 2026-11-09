# Runbook: Stage 1 screening sweep (three sessions)

For Zack. Plan: `docs/plans/step-0-baseline.md` §5.4 (v1.4). Stage 1 is 57 cells in **three sessions**, one per
context (32K, 64K, 128K, 19 cells each), each started by you, each detached (it keeps running if you close the
terminal). The data is the measurement: **never edit or delete anything under `data/raw/`.**

## 1. The hard rule: start from a clean committed tree
A real session starts only from a clean, committed tree. **Commit everything first, and never use `--allow-dirty`.**
```
cd /mnt/data/local-ai-research
git status --short        # must print nothing
```
If it prints anything, commit it (or ask Claude to). `run-sweep.sh` refuses to start a new session when `src/`,
`configs/` or `scripts/` have uncommitted changes; `--allow-dirty` exists only for tests and would make the
recorded code commit wrong.

## 2. G3 checklist (before every session)
- [ ] Browser closed (all windows). Games, VMs, video calls and the like closed.
- [ ] The PC is on mains power (plugged in), and sleep/suspend is not something you trigger yourself.
- [ ] Nothing else uses the GPU: `nvidia-smi` shows about 2 to 400 MiB used and no compute process; `pgrep -a llama-server` prints nothing.
- [ ] You will run nothing else heavy during the session (no builds, downloads, large copies, other models).
- [ ] The PC is **not rebooted and you do not log out** until the session says `state=complete`.
- [ ] `git status --short` prints nothing (section 1).

## 3. The commands
Run them in this order, one at a time. Each session starts, prints a session id and returns at once.

| session | command | session id | expected duration |
|---|---|---|---|
| 32K  | `scripts/run-sweep.sh configs/sweeps/stage1.toml --only context=32K  --session-id stage1-32K`  | `stage1-32K`  | about 0.9 h (0.85 to 1.0) |
| 64K  | `scripts/run-sweep.sh configs/sweeps/stage1.toml --only context=64K  --session-id stage1-64K`  | `stage1-64K`  | about 1.3 h (1.3 to 1.5) |
| 128K | `scripts/run-sweep.sh configs/sweeps/stage1.toml --only context=128K --session-id stage1-128K` | `stage1-128K` | about 2.2 h (2.2 to 2.6) |

Do not start the next session until the previous one says `state=complete` (the GPU lock allows only one anyway).

- **Continue a session that stopped:** `scripts/run-sweep.sh configs/sweeps/stage1.toml --only context=32K --resume --session-id stage1-32K`
- **Re-run flagged repetitions (once, after a session is complete):** `scripts/run-sweep.sh configs/sweeps/stage1.toml --rerun-flagged stage1-32K`
  (no `--only` and no spec changes; it re-runs only the repetitions flagged `thermal`, `paging`, `warm_prefill`, `cache_miss` or `accounting`, as attempt 2, never attempt 3.)

## 4. Checking on a running session
```
scripts/sweep-status.sh stage1-32K
```
Healthy looks like: `state=running`, `runner running (pid …)`, `cells N/19 done` going up over time, `updated` within
the last few minutes, `last error none`, `records … torn_lines: 0, incomplete_batches: 0`.

| word | meaning |
|---|---|
| `state=running` | the runner is working (check that `runner running` agrees) |
| `state=complete` | every cell of the session finished or was recorded as did-not-fit; the end canary is done |
| `state=interrupted` | the runner was stopped (Ctrl-C, SIGINT); resumable |
| `state=aborted` | a session-level problem (GPU busy, no idle CPU, low memory, …); `last error` says which; resumable |
| `phase=` | `start`, `resolve` (finding N_fit / max-fit), `probe` (max-fit probing), `precondition_wait` (waiting for an idle machine, up to 10 min, 3 retries), `rerun`, `done` |
| `flags requests: {…}` | flags raised so far; `paging` (more than 1,000 faults), `thermal` and so on, re-run later. Some flags are normal; `accounting`, `warm_prefill` or `cache_miss` are not. Tell Claude |
| `drift` | start versus end canary; filled in only after the end canary |
| `runner NOT running` while `state=running` | the runner died without writing its end: follow section 5 |

A cell can be recorded `did_not_fit` (for example `oom_at_load`); that is a result, not a failure of the session.
The job log, if you need it: the `job dir:` line printed at start; `scripts/job-status.sh <job dir>`.

## 5. If a session stops (power cut, crash, hung command)
Do **not** delete or edit anything, and do not start a different session.
1. Look: `scripts/sweep-status.sh stage1-32K` and `pgrep -a llama-server`.
2. If the status says `runner running` and `updated` is only a few minutes old, it is fine; a single request at 128K can take about 10 minutes. Wait.
3. If `runner running` but `updated` has not moved for more than 20 minutes (a hung command): send a clean interrupt with `kill -INT <pid>` (the pid is in the status line), wait a minute, and check `state=interrupted`. Do not use `kill -9` on the runner unless `-INT` did nothing after 5 minutes.
4. After a power cut or reboot nothing is running. Check G3 (section 2) again; a leftover `llama-server` from the dead runner is stopped by the resume itself.
5. Resume with the `--resume` command of section 3, with the same `--only` and `--session-id`. It continues at the first missing repetition (a half-finished cell restarts with a fresh server and warm-up; the half-written repetition is discarded and kept in `events.jsonl`).
6. If it refuses (`GPU lock held`, a running llama-server you did not start, busy port) it says so and exits without touching data: close what holds the GPU, then repeat step 5.
7. If it refuses with a provenance error (spec, workload manifest or sampling settings changed since the session started): do not work around it; stop and ask Claude.
8. When it is `state=complete`, tell Claude. Resumes are normal and are recorded in `session.json`.

## 6. Expected duration (measured by the pre-flight of 9 Nov 2026)
The plan (§5.4) estimated 32K 1.5 h, 64K 2.3 h, 128K 4.2 h. The pre-flight (10 cells, 1 repetition, 29 minutes, no flags) ran at
**40 to 53 % of the plan's per-cell estimate**, because the estimate used the WP8 live check with the default `-ub 512`, while
every Stage 1 candidate runs `-b/-ub` 2048 or 4096: PP_fresh at 16K was 1,015 tok/s (mini-sweep, `-ub 512`), **2,316 tok/s at 2048
and 2,862 tok/s at 4096**; decode speed was unchanged (about 78 to 80 tok/s). Stock cells and the canary keep `-ub 512` and run at the old speed.

Measured per cell (seconds, one repetition = the "measure" phase; the rest of a cell is about 14 s fixed (10 s idle check, launch, stop)
plus 9 to 15 s warm-up):

| context | P1 | P3 | P6 | P7 | P8 | P9 | P1 at b4096 |
|---|---|---|---|---|---|---|---|
| 32K  | 47.4 | 52.3 | 50.9 | 56.0 | 51.0 | 46.6 | 41.9 |
| 128K | 148.7 | - | 165.8 | - | 159.3 | - | - |

Relative to P1: caches P3 to P5 +10 %, P6 +9 %, P7 +18 %, P8 +7 %, P9 -2 %, b4096 -12 % (one measurement). 64K was not run; it is scaled with
the same ratio to the live-check figures (52 %). Max-fit probing for P6 and P7 took 5 steps each: 27 s per step at 32K and 103 s per step
at 128K (about 52 s at 64K, interpolated), so one probe sequence costs 2.3 min at 32K and 8.6 min at 128K; Stage 1 needs one per
(context, batch) group, two per session. P8 and P9 need no probing (N_fit is read from P1's log). Canary: 3 min per end (mini-sweep, 181 to 188 s), two per session.

| session | cells (2 repetitions) | probing | canaries | **expected total** | upper bound |
|---|---|---|---|---|---|
| 32K  | 0.67 h | 4.5 min | 6.5 min | **0.85 h** | 0.97 h |
| 64K  | 1.02 h | 8.7 min | 6.5 min | **1.28 h** | 1.48 h |
| 128K | 1.79 h | 17.1 min | 6.5 min | **2.18 h** | 2.57 h |
| all three | | | | **4.3 h** | 5.0 h |

Per cell: 14 s + warm-up 12.5 s + 2 x repetition (P1 at b2048 as in the table, other placements by the ratios above, b4096 cells at 0.88,
stock at 0.96 x the live-check repetition, about 87 s at 32K). Upper bound: b4096 no faster, CPU-expert cells (P6 to P9) 25 % slower, 7 probe steps.
Allow extra time for a cold model load (12 s for the first cell of the pre-flight instead of 1 to 3 s) and for idle-CPU waits; a re-run of flagged
repetitions is extra. These are measured from one repetition per cell, so they are good to perhaps 15 %.

Note on probing: the pre-flight left two max-fit probes in `data/probes/cache.jsonl` (32K and 128K, batch b2048). The real sessions reuse them
(the session records `probe_cache` and `cached_from: preflight-20261109`), which saves about 11 minutes. The 64K contexts and all `b4096` cells are probed fresh.
