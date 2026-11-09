# Eligibility and screening shortlist

> **FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.**

Mode **screening**: a cell needs at least 2 clean repetitions, a complete status, at least 512 MiB free VRAM at its tightest, no flagged unit and a sanity check that has not failed (`not run` is allowed).

## 32K

> FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this study; do not quote these numbers.

| cell | role | n_clean/n_total | mean T_turn_400 (s) [95% CI] | eligible | reasons it is not | sanity |
|---|---|---|---|---|---|---|
| fit-q8-32K | candidate | 2/2 | 8.23 [8.12, 8.34] | yes | - | not run |
| stock-32K | reference (stock) | 1/2 | 8.49 | no | flagged unit(s) mini-20261109:1 (paging); n_clean 1 is below 2 (screening mode) | not run |

**Shortlist (32K):** `fit-q8-32K` (only 1 eligible cell). Reference: `stock-32K` (never shortlisted).

- `fit-q8-32K`: VRAM model 14046, KV 340, recurrent 63, compute 318, other 274.8 MiB; minimum free 1269.0 MiB; expert-cache decode-batch hit rate -.
