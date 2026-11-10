# Stage 2a paging diagnostic

**SCREENING, descriptive only.** Read-only: it changes no flag, eligibility rule or statistic and tests no cause.
Written by `tools/stage2_paging_diagnostic.py` from `data/raw/s2a-*`. Attempt 1 is the main session, attempt 2 the one `--rerun-flagged` pass (a fresh server whose first repetitions are the re-run units). Times: minutes since the start of the run that contains the window (attempt 1: the session; attempt 2: the re-run) and since that window's server was started.

## Flagged attempt-1 units, attempt 1 against attempt 2

| cell | rep | cell pos / min since run start / min since server start (a1) | a1 faults | a1 RssFile start→end | a1 swap act. / VmSwap start (MiB) | a1 host cache (prompts, MiB) | a1 min MemAvail (GiB) | a1 T_turn_400 / PP_fresh mid / TG | a2 flag | a2 min since run / server start | a2 faults | a2 RssFile start→end | a2 swap act. / VmSwap start | a2 host cache | a2 min MemAvail | a2 T_turn_400 / PP_fresh mid / TG |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `P2-128K-b4096-mtp2` | 0 | 1/5 / 3.6 / 0.4 | 1,646 | 20503.0→20501.0 | 551.0 / 0.0 | 1, 1,167 | 20.5 | 8.983 / 1867.0 / 62.6 | yes | 3.6 / 0.4 | 2,443 | 20469.0→20430.0 | 749.0 / 0.0 | 1, 1,167 | 20.9 | 8.980 / 1868.0 / 62.9 |
| `P2-128K-b4096-mtp2` | 1 | 1/5 / 6.0 / 2.9 | 2,893 | 20501.0→19403.0 | 319.1 / 551.0 | 2, 1,929 | 20.8 | 8.986 / 1871.0 / 60.2 | yes | 6.0 / 2.9 | 3,077 | 20430.0→20326.0 | -5.6 / 757.0 | 1, 762 | 21.0 | 8.871 / 1875.0 / 62.0 |
| `P2-128K-b4096-mtp3` | 0 | 3/5 / 28.8 / 0.5 | 2,379 | 20374.0→19606.0 | 771.3 / 110.0 | 1, 762 | 20.4 | 8.983 / 1867.0 / 62.5 | no | 8.9 / 0.4 | 0 | 20483.0→20072.0 | 0.0 / 0.0 | 1, 762 | 20.6 | 8.958 / 1870.0 / 61.9 |
| `P2-128K-b4096-mtp3` | 1 | 3/5 / 31.2 / 3.0 | 3,483 | 19607.0→19092.0 | -1.3 / 881.0 | 1, 1,167 | 21.2 | 9.192 / 1873.0 / 56.3 | no | 11.3 / 2.9 | 30 | 19205.0→15752.0 | 0.0 / 0.0 | 1, 1,167 | 20.7 | 9.107 / 1857.0 / 57.2 |
| `P2-128K-b4096-mtp3` | 2 | 3/5 / 33.6 / 5.4 | 4,184 | 19084.0→15105.0 | -16.2 / 880.0 | 1, 1,167 | 21.2 | 8.735 / 1874.0 / 61.5 | no | 13.8 / 5.3 | 11 | 15740.0→13313.0 | 0.0 / 0.0 | 1, 1,573 | 20.6 | 8.771 / 1874.0 / 61.1 |
| `P6-32K-b4096-mtp0` | 4 | 2/5 / 12.2 / 3.3 | 1,697 | 19265.0→18630.0 | 0.0 / 0.0 | 4, 1,796 | 22.8 | 5.734 / 2405.0 / 89.9 | no | 6.3 / 0.5 | 0 | 19983.0→19983.0 | 0.0 / 0.0 | 5, 1,826 | 22.2 | 5.698 / 2443.0 / 90.1 |
| `P6-32K-b4096-mtp1` | 2 | 1/5 / 6.7 / 1.9 | 8,296 | 20468.0→20459.0 | -8.2 / 848.0 | 4, 1,833 | 22.6 | 5.724 / 2185.0 / 100.0 | no | 3.6 / 0.4 | 0 | 20503.0→20502.0 | 0.0 / 0.0 | 4, 1,833 | 21.5 | 5.662 / 2177.0 / 99.9 |
| `P6-32K-b4096-mtp1` | 3 | 1/5 / 7.4 / 2.7 | 1,243 | 20460.0→20455.0 | -4.9 / 840.0 | 4, 1,833 | 22.7 | 5.554 / 2186.0 / 93.5 | no | 4.3 / 1.2 | 0 | 20502.0→20502.0 | 0.0 / 0.0 | 4, 1,833 | 21.3 | 5.609 / 2185.0 / 90.4 |
| `P6-32K-b4096-mtp1` | 4 | 1/5 / 8.1 / 3.4 | 1,683 | 20440.0→20091.0 | 2.0 / 844.0 | 4, 1,833 | 22.7 | 5.556 / 2180.0 / 101.3 | yes | 5.0 / 1.9 | 6,652 | 20489.0→18764.0 | 0.0 / 0.0 | 4, 1,833 | 21.3 | 5.665 / 2179.0 / 99.5 |
| `P6-64K-b4096-mtp1` | 2 | 1/5 / 8.7 / 3.0 | 20,153 | 19948.0→19374.0 | -295.5 / 927.0 | 2, 1,724 | 21.9 | 6.778 / 2023.0 / 84.5 | no | 3.6 / 0.4 | 0 | 20503.0→20502.0 | 0.0 / 0.0 | 2, 1,724 | 21.1 | 6.602 / 2056.0 / 89.0 |
| `P6-64K-b4096-mtp1` | 3 | 1/5 / 9.9 / 4.2 | 16,162 | 19373.0→18733.0 | -2.3 / 632.0 | 2, 1,321 | 21.7 | 6.564 / 2026.0 / 89.1 | no | 4.8 / 1.6 | 0 | 20501.0→20502.0 | 0.0 / 0.0 | 2, 1,321 | 21.5 | 6.414 / 2024.0 / 88.8 |
| `P6-64K-b4096-mtp1` | 4 | 1/5 / 11.2 / 5.5 | 18,550 | 18731.0→17185.0 | -3.9 / 629.0 | 3, 1,476 | 21.5 | 6.526 / 2025.0 / 90.2 | no | 6.0 / 2.8 | 23 | 20502.0→20496.0 | 486.5 / 0.0 | 3, 1,476 | 21.6 | 6.384 / 2060.0 / 91.6 |
| `P6-64K-b4096-mtp2` | 2 | 3/5 / 24.3 / 2.9 | 51,759 | 20494.0→20267.0 | 58.3 / 432.0 | 2, 1,726 | 22.0 | 6.970 / 1923.0 / 80.6 | no | 7.7 / 0.4 | 0 | 20497.0→20490.0 | 0.0 / 0.0 | 2, 1,726 | 21.3 | 6.745 / 2062.0 / 83.8 |
| `P6-64K-b4096-mtp2` | 3 | 3/5 / 25.6 / 4.2 | 4,687 | 20267.0→19224.0 | 8.6 / 490.0 | 2, 1,321 | 22.1 | 6.582 / 2022.0 / 88.0 | no | 8.9 / 1.7 | 0 | 20489.0→20453.0 | 0.0 / 0.0 | 2, 1,321 | 21.6 | 6.369 / 2060.0 / 89.2 |
| `P6-64K-b4096-mtp2` | 4 | 3/5 / 26.8 / 5.5 | 13,247 | 19226.0→19267.0 | -2.2 / 498.0 | 3, 1,882 | 21.9 | 6.518 / 2019.0 / 90.2 | no | 10.1 / 2.9 | 0 | 20445.0→20390.0 | 0.0 / 0.0 | 3, 1,882 | 21.7 | 6.405 / 2050.0 / 92.4 |

Middle depth: 32K context 24,576 tokens, 64K 32,768, 128K 65,536.

## Summary

- Attempt-1 windows: 75, paging-flagged: 15.
- Attempt-2 units run: 15; **clean: 12**; still flagged: `P2-128K-b4096-mtp2` rep 0, `P2-128K-b4096-mtp2` rep 1, `P6-32K-b4096-mtp1` rep 4.

### Concentration by cell type (attempt-1 flagged windows / windows)

| group | flagged / windows |
|---|---|
| 128K | 5 / 25 |
| 32K | 4 / 25 |
| 64K | 6 / 25 |
| MTP | 14 / 45 |
| P2 | 5 / 30 |
| P6 | 10 / 45 |
| no MTP | 1 / 30 |

| context and cell type | flagged / windows |
|---|---|
| 128K P2 mtp0 | 0 / 5 |
| 128K P2 mtp1 | 0 / 5 |
| 128K P2 mtp2 | 2 / 5 |
| 128K P2 mtp3 | 3 / 5 |
| 128K P6 mtp0 | 0 / 5 |
| 32K P2 mtp0 | 0 / 5 |
| 32K P6 mtp0 | 1 / 5 |
| 32K P6 mtp1 | 3 / 5 |
| 32K P6 mtp2 | 0 / 5 |
| 32K P6 mtp3 | 0 / 5 |
| 64K P2 mtp0 | 0 / 5 |
| 64K P6 mtp0 | 0 / 5 |
| 64K P6 mtp1 | 3 / 5 |
| 64K P6 mtp2 | 3 / 5 |
| 64K P6 mtp3 | 0 / 5 |

### Paired attempt 2 against attempt 1 (same repetition index of the same cell)

Percentage difference (attempt 2 relative to attempt 1), mean and range over the paired units. The same repetition index removes the repetition (prompt-variant) confound; it does not remove the effect of a fresh server (attempt 2 is the first repetition of a new server). **Anecdotal**: a handful of units, no interval.

| units | metric | n | mean % | min % | max % |
|---|---|---|---|---|---|
| all re-run units | t_turn_400 | 15 | -1.07 | -3.24 | +1.96 |
| all re-run units | pp_fresh_mid | 15 | +0.97 | -0.85 | +7.23 |
| all re-run units | tg_mid | 15 | +0.85 | -3.32 | +5.33 |
| attempt 2 clean only | t_turn_400 | 12 | -1.40 | -3.24 | +0.99 |
| attempt 2 clean only | pp_fresh_mid | 12 | +1.20 | -0.85 | +7.23 |
| attempt 2 clean only | tg_mid | 12 | +0.93 | -3.32 | +5.33 |

T_turn_400 lower, PP_fresh and TG higher in attempt 2 would mean the flagged attempt-1 window was the slower one.

### Flagged against unflagged windows of the same cell (attempt 1, T_turn_400, confounded by repetition)

| cell | flagged mean (n) | unflagged mean (n) | difference |
|---|---|---|---|
| `P2-128K-b4096-mtp2` | 8.985 (2) | 8.989 (3) | -0.05 % |
| `P2-128K-b4096-mtp3` | 8.97 (3) | 9.014 (2) | -0.49 % |
| `P6-32K-b4096-mtp0` | 5.734 (1) | 5.97 (4) | -3.96 % |
| `P6-32K-b4096-mtp1` | 5.611 (3) | 5.931 (2) | -5.39 % |
| `P6-64K-b4096-mtp1` | 6.623 (3) | 7.017 (2) | -5.62 % |
| `P6-64K-b4096-mtp2` | 6.69 (3) | 6.747 (2) | -0.84 % |

### Swap carried into the flagged window (descriptive)

| cell | rep | swap activity of the previous window (MiB) | VmSwap at the start of the flagged window (MiB) |
|---|---|---|---|
| `P2-128K-b4096-mtp2` | 0 | - | 0.0 |
| `P2-128K-b4096-mtp2` | 1 | 551.0 | 551.0 |
| `P2-128K-b4096-mtp3` | 0 | - | 110.0 |
| `P2-128K-b4096-mtp3` | 1 | 771.3 | 881.0 |
| `P2-128K-b4096-mtp3` | 2 | -1.3 | 880.0 |
| `P6-32K-b4096-mtp0` | 4 | 0.0 | 0.0 |
| `P6-32K-b4096-mtp1` | 2 | 848.3 | 848.0 |
| `P6-32K-b4096-mtp1` | 3 | -8.2 | 840.0 |
| `P6-32K-b4096-mtp1` | 4 | -4.9 | 844.0 |
| `P6-64K-b4096-mtp1` | 2 | 2,208.6 | 927.0 |
| `P6-64K-b4096-mtp1` | 3 | -295.5 | 632.0 |
| `P6-64K-b4096-mtp1` | 4 | -2.3 | 629.0 |
| `P6-64K-b4096-mtp2` | 2 | 431.6 | 432.0 |
| `P6-64K-b4096-mtp2` | 3 | 58.3 | 490.0 |
| `P6-64K-b4096-mtp2` | 4 | 8.6 | 498.0 |
