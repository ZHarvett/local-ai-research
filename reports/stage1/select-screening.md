# Eligibility and screening shortlist

Mode **screening**: a cell needs at least 2 clean repetitions, a complete status, at least 512 MiB free VRAM at its tightest, no flagged unit and a sanity check that has not failed (`not run` is allowed).

## 32K

| cell | role | n_clean/n_total | mean T_turn_400 (s) [95% CI] | eligible | reasons it is not | sanity |
|---|---|---|---|---|---|---|
| P1-32K-b2048 | candidate | 2/2 | 6.77 [6.69, 6.86] | yes | - | not run |
| P1-32K-b4096 | candidate | 2/2 | 6.51 [6.46, 6.56] | yes | - | not run |
| P2-32K-b2048 | candidate | 2/2 | 6.44 [6.43, 6.46] | no | minimum free VRAM 485 MiB is below 512 | not run |
| P2-32K-b4096 | candidate | 2/2 | 6.26 [6.24, 6.29] | yes | - | not run |
| P3-32K-b2048 | candidate | 2/2 | 7.96 [7.60, 8.31] | yes | - | not run |
| P3-32K-b4096 | candidate | 2/2 | 7.90 [7.72, 8.08] | yes | - | not run |
| P4-32K-b2048 | candidate | 2/2 | 7.07 [5.88, 8.26] | yes | - | not run |
| P4-32K-b4096 | candidate | 2/2 | 6.92 [6.13, 7.71] | yes | - | not run |
| P5-32K-b2048 | candidate | 2/2 | 6.71 [6.29, 7.14] | yes | - | not run |
| P5-32K-b4096 | candidate | 2/2 | 6.50 [6.40, 6.61] | yes | - | not run |
| P6-32K-b2048 | candidate | 2/2 | 6.46 [5.97, 6.95] | yes | - | not run |
| P6-32K-b4096 | candidate | 2/2 | 6.14 [3.57, 8.70] | yes | - | not run |
| P7-32K-b2048 | candidate | 2/2 | 7.11 [5.96, 8.27] | yes | - | not run |
| P7-32K-b4096 | candidate | 2/2 | 6.72 [3.53, 9.92] | yes | - | not run |
| P8-32K-b2048 | candidate | 2/2 | 7.08 [7.02, 7.15] | yes | - | not run |
| P8-32K-b4096 | candidate | 2/2 | 6.68 [6.58, 6.78] | yes | - | not run |
| P9-32K-b2048 | candidate | 2/2 | 6.72 [6.63, 6.82] | yes | - | not run |
| P9-32K-b4096 | candidate | 2/2 | 6.46 [5.92, 7.00] | yes | - | not run |
| stock-32K | reference (stock) | 2/2 | 8.45 [8.40, 8.50] | yes | - | not run |

**Shortlist (32K):** `P6-32K-b4096`, `P2-32K-b4096`. Reference: `stock-32K` (never shortlisted).

Ranking by mean T_turn_400: `P6-32K-b4096` < `P2-32K-b4096` < `P6-32K-b2048` < `P9-32K-b4096` < `P5-32K-b4096` < `P1-32K-b4096` < `P8-32K-b4096` < `P5-32K-b2048` < `P9-32K-b2048` < `P7-32K-b4096` < `P1-32K-b2048` < `P4-32K-b4096` < `P4-32K-b2048` < `P8-32K-b2048` < `P7-32K-b2048` < `P3-32K-b4096` < `P3-32K-b2048`

- `P6-32K-b4096` and `P2-32K-b4096`: too close to call at n = 2 (means differ by 0.130 s, larger range 0.403 s).
- `P6-32K-b4096` and `P6-32K-b2048`: too close to call at n = 2 (means differ by 0.326 s, larger range 0.403 s).
- `P6-32K-b4096` and `P9-32K-b4096`: too close to call at n = 2 (means differ by 0.326 s, larger range 0.403 s).
- `P6-32K-b2048` and `P9-32K-b4096`: too close to call at n = 2 (means differ by 0.000 s, larger range 0.085 s).

- `P6-32K-b4096`: VRAM model 1303, KV 340, recurrent 63, compute 1348, expert cache 11520, other 358.6 MiB; minimum free 1379.0 MiB; expert-cache decode-batch hit rate 96.2%.
- `P2-32K-b4096`: VRAM model 13900, KV 340, recurrent 63, compute 1104, expert cache 0, other 337.3 MiB; minimum free 567.0 MiB; expert-cache decode-batch hit rate -.

## 64K

| cell | role | n_clean/n_total | mean T_turn_400 (s) [95% CI] | eligible | reasons it is not | sanity |
|---|---|---|---|---|---|---|
| P1-64K-b2048 | candidate | 2/2 | 7.68 [7.62, 7.74] | yes | - | not run |
| P1-64K-b4096 | candidate | 2/2 | 7.39 [7.21, 7.58] | yes | - | not run |
| P2-64K-b2048 | candidate | 2/2 | 7.45 [7.38, 7.52] | yes | - | not run |
| P2-64K-b4096 | candidate | 2/2 | 7.16 [7.06, 7.26] | yes | - | not run |
| P3-64K-b2048 | candidate | 2/2 | 8.98 [8.03, 9.93] | yes | - | not run |
| P3-64K-b4096 | candidate | 2/2 | 9.03 [8.86, 9.21] | yes | - | not run |
| P4-64K-b2048 | candidate | 2/2 | 8.29 [8.29, 8.29] | yes | - | not run |
| P4-64K-b4096 | candidate | 2/2 | 8.12 [6.95, 9.29] | yes | - | not run |
| P5-64K-b2048 | candidate | 2/2 | 7.64 [6.67, 8.62] | yes | - | not run |
| P5-64K-b4096 | candidate | 2/2 | 7.33 [7.22, 7.45] | yes | - | not run |
| P6-64K-b2048 | candidate | 2/2 | 7.55 [6.51, 8.58] | yes | - | not run |
| P6-64K-b4096 | candidate | 2/2 | 7.00 [6.28, 7.72] | yes | - | not run |
| P7-64K-b2048 | candidate | 2/2 | 8.45 [6.49, 10.40] | yes | - | not run |
| P7-64K-b4096 | candidate | 2/2 | 7.82 [6.57, 9.07] | yes | - | not run |
| P8-64K-b2048 | candidate | 2/2 | 7.97 [7.79, 8.16] | yes | - | not run |
| P8-64K-b4096 | candidate | 2/2 | 7.59 [7.54, 7.64] | yes | - | not run |
| P9-64K-b2048 | candidate | 2/2 | 7.67 [7.65, 7.68] | yes | - | not run |
| P9-64K-b4096 | candidate | 2/2 | 7.31 [7.13, 7.48] | yes | - | not run |
| stock-64K | reference (stock) | 2/2 | 9.36 [9.09, 9.63] | yes | - | not run |

**Shortlist (64K):** `P6-64K-b4096`, `P2-64K-b4096`. Reference: `stock-64K` (never shortlisted).

Ranking by mean T_turn_400: `P6-64K-b4096` < `P2-64K-b4096` < `P9-64K-b4096` < `P5-64K-b4096` < `P1-64K-b4096` < `P2-64K-b2048` < `P6-64K-b2048` < `P8-64K-b4096` < `P5-64K-b2048` < `P9-64K-b2048` < `P1-64K-b2048` < `P7-64K-b4096` < `P8-64K-b2048` < `P4-64K-b4096` < `P4-64K-b2048` < `P7-64K-b2048` < `P3-64K-b2048` < `P3-64K-b4096`

- `P9-64K-b4096` and `P5-64K-b4096`: too close to call at n = 2 (means differ by 0.026 s, larger range 0.028 s).

- `P6-64K-b4096`: VRAM model 1303, KV 680, recurrent 63, compute 1604, expert cache 11007, other 358.8 MiB; minimum free 1295.0 MiB; expert-cache decode-batch hit rate 95.3%.
- `P2-64K-b4096`: VRAM model 13323, KV 680, recurrent 63, compute 1360, expert cache 0, other 337.8 MiB; minimum free 547.0 MiB; expert-cache decode-batch hit rate -.

## 128K

| cell | role | n_clean/n_total | mean T_turn_400 (s) [95% CI] | eligible | reasons it is not | sanity |
|---|---|---|---|---|---|---|
| P1-128K-b2048 | candidate | 2/2 | 9.51 [9.33, 9.70] | yes | - | not run |
| P1-128K-b4096 | candidate | 2/2 | 9.28 [8.93, 9.63] | yes | - | not run |
| P2-128K-b2048 | candidate | 2/2 | 9.29 [9.25, 9.34] | yes | - | not run |
| P2-128K-b4096 | candidate | 2/2 | 9.06 [8.30, 9.81] | yes | - | not run |
| P3-128K-b2048 | candidate | 2/2 | 11.36 [10.22, 12.50] | yes | - | not run |
| P3-128K-b4096 | candidate | 2/2 | 11.24 [10.15, 12.33] | yes | - | not run |
| P4-128K-b2048 | candidate | 2/2 | 10.24 [9.53, 10.95] | yes | - | not run |
| P4-128K-b4096 | candidate | 2/2 | 10.12 [10.10, 10.13] | yes | - | not run |
| P5-128K-b2048 | candidate | 2/2 | 9.65 [9.40, 9.89] | yes | - | not run |
| P5-128K-b4096 | candidate | 2/2 | 9.56 [9.42, 9.70] | yes | - | not run |
| P6-128K-b2048 | candidate | 2/2 | 9.26 [6.45, 12.06] | yes | - | not run |
| P6-128K-b4096 | candidate | 2/2 | 9.09 [8.88, 9.30] | yes | - | not run |
| P7-128K-b2048 | candidate | 2/2 | 10.30 [7.80, 12.80] | yes | - | not run |
| P7-128K-b4096 | candidate | 2/2 | 10.11 [10.09, 10.14] | yes | - | not run |
| P8-128K-b2048 | candidate | 2/2 | 9.92 [9.30, 10.53] | yes | - | not run |
| P8-128K-b4096 | candidate | 2/2 | 9.57 [9.56, 9.59] | yes | - | not run |
| P9-128K-b2048 | candidate | 2/2 | 9.49 [9.39, 9.58] | yes | - | not run |
| P9-128K-b4096 | candidate | 2/2 | 9.29 [9.09, 9.49] | yes | - | not run |
| stock-128K | reference (stock) | 2/2 | 11.29 [10.89, 11.69] | yes | - | not run |

**Shortlist (128K):** `P2-128K-b4096`, `P6-128K-b4096`. Reference: `stock-128K` (never shortlisted).

Ranking by mean T_turn_400: `P2-128K-b4096` < `P6-128K-b4096` < `P6-128K-b2048` < `P1-128K-b4096` < `P9-128K-b4096` < `P2-128K-b2048` < `P9-128K-b2048` < `P1-128K-b2048` < `P5-128K-b4096` < `P8-128K-b4096` < `P5-128K-b2048` < `P8-128K-b2048` < `P7-128K-b4096` < `P4-128K-b4096` < `P4-128K-b2048` < `P7-128K-b2048` < `P3-128K-b4096` < `P3-128K-b2048`

- `P2-128K-b4096` and `P6-128K-b4096`: too close to call at n = 2 (means differ by 0.032 s, larger range 0.119 s).
- `P2-128K-b4096` and `P6-128K-b2048`: too close to call at n = 2 (means differ by 0.198 s, larger range 0.442 s).
- `P6-128K-b4096` and `P6-128K-b2048`: too close to call at n = 2 (means differ by 0.166 s, larger range 0.442 s).
- `P6-128K-b2048` and `P1-128K-b4096`: too close to call at n = 2 (means differ by 0.022 s, larger range 0.442 s).

- `P2-128K-b4096`: VRAM model 11961, KV 1360, recurrent 63, compute 2034, expert cache 0, other 341.8 MiB; minimum free 551.0 MiB; expert-cache decode-batch hit rate -.
- `P6-128K-b4096`: VRAM model 1303, KV 1360, recurrent 63, compute 2116, expert cache 9725, other 361.2 MiB; minimum free 1383.0 MiB; expert-cache decode-batch hit rate 93.7%.

