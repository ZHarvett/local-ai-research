# Baseline report (functional-test)

> **FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.**

## Provenance

- Plan version: v1.3
- Regenerate with: `python -m smallpc.report render --sessions SESSIONS --out OUT --label functional-test`
- Statistics: mean, n, min, max and a 95% CI (wider of the percentile-bootstrap interval, 10,000 resamples, fixed seed, and the t interval); CIs shown for n of at least 2.

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| session | spec / sha-256 | manifest sha-256 | session commit | record commits | snapshot ids | llama.cpp | state |
|---|---|---|---|---|---|---|---|
| fx-1 | fixture `aaaaaaaaaaaaaaaa` | `bbbbbbbbbbbbbbbb` | ffffffffff (dirty) **--allow-dirty** | `abc1234567` | `5ca1ab1e5ca1ab1e` | `cccccccccc` | complete |
| fx-drift | fixture `aaaaaaaaaaaaaaaa` | `bbbbbbbbbbbbbbbb` | ffffffffff | `abc1234567` | `5ca1ab1e5ca1ab1e` | `cccccccccc` | complete |

Session `fx-1` was run with `--allow-dirty`: its recorded commit is not exact (uncommitted paths: `src/smallpc/sweep/`).

## Session health

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| session | systemd-inhibit | idle precondition | drift flag |
|---|---|---|---|
| fx-1 | checked True, active True | 10 checks, 0 failed, total wait 0 s, max busy 2.5 % | main: none |
| fx-drift | checked True, active True | 1 checks, 0 failed, total wait 0 s, max busy 2.5 % | main: drift |

Canaries (never part of cell statistics):

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| session | run | phase | reps | PP_fresh 16K (tok/s) | TG 16K (tok/s) | TG short (tok/s) | flags |
|---|---|---|---|---|---|---|---|
| fx-1 | main | start | 3 | 975.1 [972.7, 977.5] | 75.3 [74.9, 75.8] | 79.5 [79.1, 80.0] | - |
| fx-1 | main | end | 3 | 975.2 [970.6, 979.8] | 75.3 [74.7, 75.9] | 79.4 [79.2, 79.5] | - |
| fx-drift | main | start | 3 | 975.9 [972.8, 979.0] | 75.3 [74.5, 76.1] | 79.3 [78.5, 80.0] | - |
| fx-drift | main | end | 3 | 975.7 [971.3, 980.2] | 75.2 [74.4, 76.0] | 79.2 [78.8, 79.6] | - |

## Results

### 32K

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| cell | n_clean/n_total | PP_fresh 8K (tok/s) | PP_fresh 16K (tok/s) | PP_fresh 24K (tok/s) | TG 8K (tok/s) | TG 16K (tok/s) | TG 24K (tok/s) | T_turn_400 (s) | T_B (s) | T_reread (s) | TTFT (s) | acceptance | flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stock-32K | 5/5 | 937.9 [936.6, 939.1] | 926.8 [925.1, 928.4] | 913.8 [912.8, 914.8] | 75.6 [75.3, 76.0] | 73.1 [72.8, 73.4] | 70.8 [70.5, 71.1] | 8.90 [8.89, 8.91] | 8.90 [8.89, 8.91] (predicted_n 400) | 17.77 [17.75, 17.78] | 3.48 [3.48, 3.49] | - | - |
| MTP-32K | 5/5 | 977.1 [975.7, 978.5] | 966.4 [965.4, 967.5] | 953.9 [952.4, 955.4] | 92.5 [92.3, 92.7] | 90.3 [90.0, 90.7] | 87.8 [87.6, 88.1] | 7.73 [7.72, 7.74] | 7.73 [7.72, 7.74] (predicted_n 400) | 17.03 [17.02, 17.05] | 3.34 [3.34, 3.35] | 70.0 [70.0, 70.0] % (pooled 70.0 %) | - |
| P1-32K-b2048 | 5/5 | 989.4 [988.7, 990.1] | 976.2 [974.4, 978.0] | 964.0 [962.2, 965.7] | 81.4 [81.1, 81.8] | 79.3 [79.1, 79.5] | 76.8 [76.7, 77.0] | 8.32 [8.31, 8.32] | 8.32 [8.31, 8.32] (predicted_n 400) | 16.85 [16.84, 16.86] | 3.31 [3.31, 3.31] | - | - |
| P2-32K-b2048 | 5/5 | 989.5 [988.0, 991.0] | 978.7 [977.4, 980.1] | 965.6 [963.8, 967.4] | 81.2 [80.8, 81.6] | 78.7 [78.5, 78.8] | 76.3 [76.0, 76.6] | 8.34 [8.33, 8.35] | 8.34 [8.33, 8.35] (predicted_n 400) | 16.82 [16.81, 16.84] | 3.31 [3.30, 3.31] | - | - |
| rerun-ok-32K | 5/5 | 993.8 [992.3, 995.3] | 980.7 [979.2, 982.1] | 968.8 [967.1, 970.6] | 79.6 [79.3, 79.8] | 77.3 [77.0, 77.6] | 75.0 [74.8, 75.2] | 8.42 [8.41, 8.44] | 8.42 [8.41, 8.44] (predicted_n 400) | 16.77 [16.76, 16.79] | 3.29 [3.29, 3.30] | - | 1 unit(s) re-run (attempt 2 used) |
| rerun-bad-32K | 4/5 not reportable (n < 5) | 988.0 [986.4, 989.6] | 977.2 [975.4, 979.1] | 964.5 [963.9, 965.0] | 79.5 [79.0, 80.0] | 77.3 [77.0, 77.6] | 74.6 [74.4, 74.8] | 8.45 [8.42, 8.47] | 8.45 [8.42, 8.47] (predicted_n 400) | 16.85 [16.84, 16.85] | 3.31 [3.30, 3.31] | - | cache_miss, 1 unit(s) re-run (attempt 2 used) |
| shortgen-32K | 4/5 not reportable (n < 5) | 986.7 [985.3, 988.2] | 976.7 [975.2, 978.3] | 964.0 [961.8, 966.1] | 78.4 [78.1, 78.6] | 76.2 [75.9, 76.4] | 73.9 [73.5, 74.4] | 8.52 [8.51, 8.53] | 8.52 [8.51, 8.53] (predicted_n 400) | 16.86 [16.84, 16.88] | 3.31 [3.31, 3.32] | - | short_gen |
| P4-32K-b2048 | 5/5 | 998.2 [997.1, 999.2] | 985.3 [983.9, 986.7] | 975.0 [974.1, 976.0] | 77.6 [77.2, 77.9] | 75.4 [75.1, 75.7] | 72.9 [72.7, 73.0] | 8.54 [8.53, 8.56] | 8.54 [8.53, 8.56] (predicted_n 400) | 16.68 [16.67, 16.69] | 3.28 [3.27, 3.28] | - | - |
| dnf-context-32K | did_not_fit (context) | - | - | - | - | - | - | - | - | - | - | - | - |
| dnf-crash_mid_cell-32K | did_not_fit (crash_mid_cell) | - | - | - | - | - | - | - | - | - | - | - | - |
| dnf-hung_server-32K | did_not_fit (hung_server) | - | - | - | - | - | - | - | - | - | - | - | - |
| dnf-oom_at_load-32K | did_not_fit (oom_at_load) | - | - | - | - | - | - | - | - | - | - | - | - |
| dnf-oom_runtime-32K | did_not_fit (oom_runtime) | - | - | - | - | - | - | - | - | - | - | - | - |
| dnf-request_timeout-32K | did_not_fit (request_timeout) | - | - | - | - | - | - | - | - | - | - | - | - |
| dnf-startup_failure-32K | did_not_fit (startup_failure) | - | - | - | - | - | - | - | - | - | - | - | - |
| dnf-startup_timeout-32K | did_not_fit (startup_timeout) | - | - | - | - | - | - | - | - | - | - | - | - |
| drift-32K | 0/5 not reportable (n < 5) | - | - | - | - | - | - | - | - | - | - | - | drift |

Values are mean [95% CI] over clean repetitions. T_turn_400, T_B, T_reread and TTFT are means over the depths of §5.3 per repetition. T_turn_400 is an estimate (400 tokens); T_B is the measured time of Request B and is always shown with its `predicted_n`.

### 64K

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| cell | n_clean/n_total | PP_fresh 16K (tok/s) | PP_fresh 32K (tok/s) | PP_fresh 48K (tok/s) | TG 16K (tok/s) | TG 32K (tok/s) | TG 48K (tok/s) | T_turn_400 (s) | T_B (s) | T_reread (s) | TTFT (s) | acceptance | flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stock-64K | 5/5 | 876.3 [874.9, 877.7] | 852.0 [850.2, 853.7] | 829.1 [827.9, 830.2] | 65.2 [64.9, 65.5] | 60.4 [60.1, 60.8] | 55.6 [55.4, 55.9] | 10.27 [10.25, 10.29] | 10.27 [10.25, 10.29] (predicted_n 400) | 38.82 [38.78, 38.85] | 3.68 [3.67, 3.68] | - | - |
| P1-64K-b2048 | 5/5 | 926.2 [924.8, 927.5] | 902.0 [900.7, 903.2] | 877.4 [876.4, 878.3] | 71.2 [71.0, 71.4] | 66.4 [66.1, 66.6] | 61.5 [61.2, 61.9] | 9.48 [9.46, 9.50] | 9.48 [9.46, 9.50] (predicted_n 400) | 36.68 [36.64, 36.72] | 3.48 [3.48, 3.49] | - | - |

Values are mean [95% CI] over clean repetitions. T_turn_400, T_B, T_reread and TTFT are means over the depths of §5.3 per repetition. T_turn_400 is an estimate (400 tokens); T_B is the measured time of Request B and is always shown with its `predicted_n`.

### Cells without context information

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| cell | status | reason |
|---|---|---|
| NA-32K | not_applicable | n_cpu_moe: n_fit resolves to -1; not applicable |

Cells that never started (not_applicable) have no resolved configuration, so no context is known.

## Eligibility and selection

Mode **screening**: a cell needs at least 2 clean repetitions, a complete status, at least 512 MiB free VRAM at its tightest, no flagged unit and a sanity check that has not failed (`not run` is allowed).

### 32K

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| cell | role | n_clean/n_total | mean T_turn_400 (s) [95% CI] | eligible | reasons it is not | sanity |
|---|---|---|---|---|---|---|
| MTP-32K | candidate | 5/5 | 7.73 [7.72, 7.74] | yes | - | not run |
| P1-32K-b2048 | candidate | 5/5 | 8.32 [8.31, 8.32] | yes | - | not run |
| P2-32K-b2048 | candidate | 5/5 | 8.34 [8.33, 8.35] | yes | - | not run |
| P4-32K-b2048 | candidate | 5/5 | 8.54 [8.53, 8.56] | yes | - | not run |
| dnf-context-32K | candidate | 0/0 | - | no | final status is did_not_fit (context), not complete; no VRAM measurement (no final-attempt window); n_clean 0 is below 2 (screening mode) | not run |
| dnf-crash_mid_cell-32K | candidate | 0/0 | - | no | final status is did_not_fit (crash_mid_cell), not complete; no VRAM measurement (no final-attempt window); n_clean 0 is below 2 (screening mode) | not run |
| dnf-hung_server-32K | candidate | 0/0 | - | no | final status is did_not_fit (hung_server), not complete; no VRAM measurement (no final-attempt window); n_clean 0 is below 2 (screening mode) | not run |
| dnf-oom_at_load-32K | candidate | 0/0 | - | no | final status is did_not_fit (oom_at_load), not complete; no VRAM measurement (no final-attempt window); n_clean 0 is below 2 (screening mode) | not run |
| dnf-oom_runtime-32K | candidate | 0/0 | - | no | final status is did_not_fit (oom_runtime), not complete; no VRAM measurement (no final-attempt window); n_clean 0 is below 2 (screening mode) | not run |
| dnf-request_timeout-32K | candidate | 0/0 | - | no | final status is did_not_fit (request_timeout), not complete; no VRAM measurement (no final-attempt window); n_clean 0 is below 2 (screening mode) | not run |
| dnf-startup_failure-32K | candidate | 0/0 | - | no | final status is did_not_fit (startup_failure), not complete; no VRAM measurement (no final-attempt window); n_clean 0 is below 2 (screening mode) | not run |
| dnf-startup_timeout-32K | candidate | 0/0 | - | no | final status is did_not_fit (startup_timeout), not complete; no VRAM measurement (no final-attempt window); n_clean 0 is below 2 (screening mode) | not run |
| drift-32K | candidate | 0/5 | - | no | flagged unit(s) fx-drift:0, fx-drift:1, fx-drift:2, fx-drift:3, fx-drift:4 (drift); n_clean 0 is below 2 (screening mode) | not run |
| rerun-bad-32K | candidate | 4/5 | 8.45 [8.42, 8.47] | no | flagged unit(s) fx-1:1 (cache_miss) | not run |
| rerun-ok-32K | candidate | 5/5 | 8.42 [8.41, 8.44] | yes | - | not run |
| shortgen-32K | candidate | 4/5 | 8.52 [8.51, 8.53] | no | flagged unit(s) fx-1:1 (short_gen) | not run |
| stock-32K | reference (stock) | 5/5 | 8.90 [8.89, 8.91] | yes | - | not run |

**Shortlist (32K):** `MTP-32K`, `P1-32K-b2048`. Reference: `stock-32K` (never shortlisted).

Ranking by mean T_turn_400: `MTP-32K` < `P1-32K-b2048` < `P2-32K-b2048` < `rerun-ok-32K` < `P4-32K-b2048`

- `P1-32K-b2048` and `P2-32K-b2048`: too close to call at n = 2 (means differ by 0.024 s, larger range 0.024 s).

- `MTP-32K`: VRAM model 13500, KV 340, recurrent 63, compute 318, other 890.2 MiB; minimum free 1200.0 MiB; expert-cache decode-batch hit rate -.
- `P1-32K-b2048`: VRAM model 13500, KV 340, recurrent 63, compute 318, other 890.2 MiB; minimum free 1200.0 MiB; expert-cache decode-batch hit rate -.

### 64K

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| cell | role | n_clean/n_total | mean T_turn_400 (s) [95% CI] | eligible | reasons it is not | sanity |
|---|---|---|---|---|---|---|
| P1-64K-b2048 | candidate | 5/5 | 9.48 [9.46, 9.50] | yes | - | not run |
| stock-64K | reference (stock) | 5/5 | 10.27 [10.25, 10.29] | yes | - | not run |

**Shortlist (64K):** `P1-64K-b2048` (only 1 eligible cell). Reference: `stock-64K` (never shortlisted).

- `P1-64K-b2048`: VRAM model 13500, KV 340, recurrent 63, compute 318, other 890.2 MiB; minimum free 1200.0 MiB; expert-cache decode-batch hit rate -.

## Paired comparisons with stock

### 32K

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| candidate vs stock | pairs | T_turn_400 ratio | PP_fresh ratio | TG ratio |
|---|---|---|---|---|
| MTP-32K | 5 | 0.868 [0.867, 0.869] | 1.043 [1.042, 1.043] | 1.233 [1.230, 1.235] |
| P1-32K-b2048 | 5 | 0.934 [0.933, 0.935] | 1.054 [1.054, 1.055] | 1.082 [1.080, 1.084] |
| P2-32K-b2048 | 5 | 0.937 [0.936, 0.938] | 1.056 [1.055, 1.057] | 1.076 [1.074, 1.078] |
| rerun-ok-32K | 5 | 0.946 [0.945, 0.948] | 1.059 [1.059, 1.060] | 1.056 [1.054, 1.058] |
| rerun-bad-32K | 4 | 0.949 [0.947, 0.950] | 1.054 [1.053, 1.055] | 1.054 [1.052, 1.056] |
| shortgen-32K | 4 | 0.957 [0.956, 0.958] | 1.054 [1.053, 1.054] | 1.040 [1.038, 1.042] |
| P4-32K-b2048 | 5 | 0.960 [0.959, 0.961] | 1.065 [1.064, 1.065] | 1.029 [1.026, 1.031] |

### 64K

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| candidate vs stock | pairs | T_turn_400 ratio | PP_fresh ratio | TG ratio |
|---|---|---|---|---|
| P1-64K-b2048 | 5 | 0.923 [0.921, 0.925] | 1.058 [1.057, 1.059] | 1.098 [1.095, 1.102] |

Geometric mean of per-repetition ratios (candidate / stock, repetitions that are clean in both cells) with a 95% bootstrap CI (10,000 resamples), shown for 2 or more pairs. A T_turn_400 ratio below 1 means the candidate is faster; PP_fresh and TG ratios above 1 mean it is faster. The bootstrap CI alone is narrow at small n.

## VRAM breakdown

### 32K

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| cell | model | KV | recurrent state | compute buffers | other | peak used | min free (final windows) | expert layers on CPU |
|---|---|---|---|---|---|---|---|---|
| stock-32K | 13,400 | 340 (f16) | 63 | 318 | 990 | 15,111 | 1,200 | 14 |
| MTP-32K | 13,500 | 340 (q8_0) | 63 | 318 | 890 | 15,111 | 1,200 | 14 |
| P1-32K-b2048 | 13,500 | 340 (q8_0) | 63 | 318 | 890 | 15,111 | 1,200 | 14 |
| P2-32K-b2048 | 13,500 | 340 (q8_0) | 63 | 318 | 1,390 | 15,611 | 700 | 14 |
| rerun-ok-32K | 13,500 | 340 (q8_0) | 63 | 318 | 890 | 15,111 | 1,200 | 14 |
| rerun-bad-32K | 13,500 | 340 (q8_0) | 63 | 318 | 890 | 15,111 | 1,200 | 14 |
| shortgen-32K | 13,500 | 340 (q8_0) | 63 | 318 | 890 | 15,111 | 1,200 | 14 |
| P4-32K-b2048 | 13,000 | 340 (q8_0) | 63 | 318 | 1,390 | 15,111 | 1,200 | 14 |
| drift-32K | 13,500 | 340 (q8_0) | 63 | 318 | 890 | 15,111 | 1,200 | 14 |

### 64K

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| cell | model | KV | recurrent state | compute buffers | other | peak used | min free (final windows) | expert layers on CPU |
|---|---|---|---|---|---|---|---|---|
| stock-64K | 13,500 | 340 (f16) | 63 | 318 | 890 | 15,111 | 1,200 | 14 |
| P1-64K-b2048 | 13,500 | 340 (q8_0) | 63 | 318 | 890 | 15,111 | 1,200 | 14 |

MiB, from each cell summary's parsed placement (buffers on the GPU) and its windows. 'other' is peak used minus the listed buffers (CUDA context, graphs, allocator slack).

## Expert cache

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| cell | cache MiB | decode-batch hit rate | hits | misses | large-batch experts copied | uploaded MiB |
|---|---|---|---|---|---|---|
| P4-32K-b2048 | 2,048 | 62.0 % | 62,000 | 38,000 | 4,321 | 1,500 |

Limitation: the server's statistics give hit rates for **decode-sized batches only** (`ubatch <= 8`); prefill-sized batches report only how many experts were copied from the cache. The counts cover everything the server served (warm-up, every repetition and attempt), not only clean repetitions.

## Excluded diagnostic results

> excluded diagnostic result. FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| cell | session | repetition | attempt | flags | T_turn_400 (s), mean over depths | why |
|---|---|---|---|---|---|---|
| rerun-bad-32K | fx-1 | 1 | 1 | cache_miss | 8.44 | attempt 1 of a unit re-run as attempt 2 |
| rerun-bad-32K | fx-1 | 1 | 2 | cache_miss | 8.43 | flagged unit |
| rerun-ok-32K | fx-1 | 2 | 1 | paging | 8.42 | attempt 1 of a unit re-run as attempt 2 |
| shortgen-32K | fx-1 | 1 | 1 | short_gen | 8.61 | flagged unit |
| drift-32K | fx-drift | 0 | 1 | drift | 8.62 | flagged unit |
| drift-32K | fx-drift | 1 | 1 | drift | 8.61 | flagged unit |
| drift-32K | fx-drift | 2 | 1 | drift | 8.62 | flagged unit |
| drift-32K | fx-drift | 3 | 1 | drift | 8.60 | flagged unit |
| drift-32K | fx-drift | 4 | 1 | drift | 8.61 | flagged unit |

These units are not in any headline number above. Flagged units stay here with their flags; attempt 1 of a re-run unit is replaced by attempt 2.

## Appendix: screening data

Screening results (fewer than 5 clean repetitions) are used only for shortlisting and are never reported as results (§5.5).

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| cell | context | n_clean/n_total | T_turn_400 (s) |
|---|---|---|---|
| drift-32K | 32K | 0/5 not reportable (n < 5) | - |
| rerun-bad-32K | 32K | 4/5 not reportable (n < 5) | 8.45 [8.42, 8.47] |
| shortgen-32K | 32K | 4/5 not reportable (n < 5) | 8.52 [8.51, 8.53] |

## Figures

![Prefill speed (PP_fresh) vs prompt length](figures/prefill-speed.svg)

![Decode speed (TG) vs depth](figures/decode-speed.svg)

![T_turn_400 (estimated) and T_B (measured)](figures/turn-time.svg)

![VRAM breakdown per context](figures/vram-breakdown.svg)

![Expert-cache hit rate vs cache size](figures/expert-cache-hit-rate.svg)
