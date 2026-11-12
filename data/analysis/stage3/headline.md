# Stage 3 headline: stock against tuned (plan v1.7 section 5.4)

> **RESULTS. Only cells with at least 5 clean repetitions are reportable.**

The clean-units and all-units versions agree in every context (sign, and whether each interval excludes 1.0).

## 32K: stock-32K and tuned-32K

**Tuned cell eligibility (final mode):** eligible; n_clean 5 of 5; minimum free VRAM 1,379 MiB; sanity pass

**Headline: clean units** (5 clean, paired units).

| metric | tuned / stock, geometric mean [95% CI] (paired units) | reading |
|---|---|---|
| t_turn_400 | 0.705 [0.672, 0.739] (n=5) | lower is faster |
| t_reread | 0.378 [0.375, 0.381] (n=5) | lower is faster |
| pp_fresh at 8K | 2.686 [2.671, 2.700] (n=5) | higher is faster |
| pp_fresh at 16K | 2.664 [2.644, 2.684] (n=5) | higher is faster |
| pp_fresh at 24K | 2.621 [2.586, 2.657] (n=5) | higher is faster |
| tg at 8K | 1.173 [1.101, 1.249] (n=5) | higher is faster |
| tg at 16K | 1.142 [1.089, 1.197] (n=5) | higher is faster |
| tg at 24K | 1.089 [0.996, 1.190] (n=5) | higher is faster |
| ttft at 8K | 0.431 [0.423, 0.440] (n=5) | lower is faster |
| ttft at 16K | 0.451 [0.428, 0.475] (n=5) | lower is faster |
| ttft at 24K | 0.455 [0.448, 0.462] (n=5) | lower is faster |

Same comparison on all units (flagged units included):

| metric | tuned / stock, geometric mean [95% CI] (paired units) | reading |
|---|---|---|
| t_turn_400 | 0.705 [0.672, 0.739] (n=5) | lower is faster |
| t_reread | 0.378 [0.375, 0.381] (n=5) | lower is faster |
| pp_fresh at 8K | 2.686 [2.671, 2.700] (n=5) | higher is faster |
| pp_fresh at 16K | 2.664 [2.644, 2.684] (n=5) | higher is faster |
| pp_fresh at 24K | 2.621 [2.586, 2.657] (n=5) | higher is faster |
| tg at 8K | 1.173 [1.101, 1.249] (n=5) | higher is faster |
| tg at 16K | 1.142 [1.089, 1.197] (n=5) | higher is faster |
| tg at 24K | 1.089 [0.996, 1.190] (n=5) | higher is faster |
| ttft at 8K | 0.431 [0.423, 0.440] (n=5) | lower is faster |
| ttft at 16K | 0.451 [0.428, 0.475] (n=5) | lower is faster |
| ttft at 24K | 0.455 [0.448, 0.462] (n=5) | lower is faster |

### Figures

**stock-32K, clean units**: n_clean 5, n_total 5; T_turn_400 8.339 [8.299, 8.379] s; T_reread 17.505 [17.421, 17.589] s; minimum free VRAM 1,385 MiB; peak VRAM 14,926 MiB; MTP acceptance -

| depth | PP_fresh (tok/s) | PP_inc (tok/s) | TG (tok/s) | T_B (s) | predicted_n | T_reread (s) | TTFT (s) |
|---|---|---|---|---|---|---|---|
| 8K | 955.5 [945.2, 965.7] | 906.0 [895.1, 917.0] | 83.87 [83.56, 84.17] | 8.069 [8.042, 8.096] | 400.0 [400.0, 400.0] | 8.574 [8.482, 8.667] | 3.313 [3.273, 3.353] |
| 16K | 941.0 [936.9, 945.0] | 880.3 [868.4, 892.2] | 81.06 [80.14, 81.99] | 8.331 [8.292, 8.370] | 400.0 [400.0, 400.0] | 17.412 [17.337, 17.487] | 3.411 [3.365, 3.457] |
| 24K | 926.4 [920.9, 931.9] | 860.5 [851.4, 869.6] | 78.35 [77.50, 79.19] | 8.580 [8.514, 8.645] | 400.0 [400.0, 400.0] | 26.529 [26.372, 26.686] | 3.490 [3.454, 3.527] |

**tuned-32K, clean units**: n_clean 5, n_total 5; T_turn_400 5.882 [5.594, 6.170] s; T_reread 6.617 [6.551, 6.683] s; minimum free VRAM 1,379 MiB; peak VRAM 14,932 MiB; MTP acceptance -

| depth | PP_fresh (tok/s) | PP_inc (tok/s) | TG (tok/s) | T_B (s) | predicted_n | T_reread (s) | TTFT (s) |
|---|---|---|---|---|---|---|---|
| 8K | 2566.1 [2543.1, 2589.1] | 2102.6 [2066.4, 2138.7] | 98.43 [92.43, 104.44] | 5.489 [5.230, 5.747] | 400.0 [400.0, 400.0] | 3.193 [3.164, 3.221] | 1.429 [1.404, 1.454] |
| 16K | 2506.8 [2486.4, 2527.1] | 1954.4 [1842.5, 2066.3] | 92.59 [88.31, 96.88] | 5.852 [5.638, 6.066] | 400.0 [400.0, 400.0] | 6.536 [6.483, 6.589] | 1.541 [1.447, 1.634] |
| 24K | 2428.3 [2393.8, 2462.9] | 1893.2 [1871.1, 1915.3] | 85.48 [77.94, 93.03] | 6.273 [5.806, 6.739] | 400.0 [400.0, 400.0] | 10.122 [9.976, 10.268] | 1.589 [1.570, 1.607] |

### Swap sensitivity (section 5.5)

headline comparison changes: t_turn_400; t_reread; pp_fresh@8192; pp_fresh@24576; tg@8192; tg@16384; tg@24576; ttft@8192; ttft@24576

Removed (swap growth above 64 MiB): stock-32K stage3-32K:2 (231 MiB); tuned-32K stage3-32K:2 (115 MiB); tuned-32K stage3-32K:4 (145 MiB)

- t_turn_400: interval moved: 0.705 [0.672, 0.739] -> 0.712 [0.629, 0.807]
- t_reread: interval moved: 0.378 [0.375, 0.381] -> 0.378 [0.371, 0.385]
- pp_fresh@8192: interval moved: 2.686 [2.671, 2.700] -> 2.691 [2.661, 2.721]
- pp_fresh@24576: interval moved: 2.621 [2.586, 2.657] -> 2.615 [2.521, 2.712]
- tg@8192: interval moved: 1.173 [1.101, 1.249] -> 1.157 [0.981, 1.365]
- tg@16384: interval moved: 1.142 [1.089, 1.197] -> 1.142 [0.999, 1.305]
- tg@24576: interval moved: 1.089 [0.996, 1.190] -> 1.057 [0.859, 1.300]
- ttft@8192: interval moved: 0.431 [0.423, 0.440] -> 0.430 [0.413, 0.446]
- ttft@24576: interval moved: 0.455 [0.448, 0.462] -> 0.456 [0.437, 0.476]

## 64K: stock-64K and tuned-64K

**Tuned cell eligibility (final mode):** eligible; n_clean 5 of 5; minimum free VRAM 1,021 MiB; sanity pass

**Headline: clean units** (5 clean, paired units).

| metric | tuned / stock, geometric mean [95% CI] (paired units) | reading |
|---|---|---|
| t_turn_400 | 0.690 [0.649, 0.734] (n=5) | lower is faster |
| t_reread | 0.423 [0.419, 0.427] (n=5) | lower is faster |
| pp_fresh at 16K | 2.488 [2.459, 2.516] (n=5) | higher is faster |
| pp_fresh at 32K | 2.399 [2.366, 2.431] (n=5) | higher is faster |
| pp_fresh at 48K | 2.304 [2.287, 2.322] (n=5) | higher is faster |
| tg at 16K | 1.225 [1.143, 1.313] (n=5) | higher is faster |
| tg at 32K | 1.239 [1.158, 1.325] (n=5) | higher is faster |
| tg at 48K | 1.213 [1.095, 1.343] (n=5) | higher is faster |
| ttft at 16K | 0.479 [0.476, 0.482] (n=5) | lower is faster |
| ttft at 32K | 0.506 [0.502, 0.510] (n=5) | lower is faster |
| ttft at 48K | 0.551 [0.515, 0.590] (n=5) | lower is faster |

Same comparison on all units (flagged units included):

| metric | tuned / stock, geometric mean [95% CI] (paired units) | reading |
|---|---|---|
| t_turn_400 | 0.690 [0.649, 0.734] (n=5) | lower is faster |
| t_reread | 0.423 [0.419, 0.427] (n=5) | lower is faster |
| pp_fresh at 16K | 2.488 [2.459, 2.516] (n=5) | higher is faster |
| pp_fresh at 32K | 2.399 [2.366, 2.431] (n=5) | higher is faster |
| pp_fresh at 48K | 2.304 [2.287, 2.322] (n=5) | higher is faster |
| tg at 16K | 1.225 [1.143, 1.313] (n=5) | higher is faster |
| tg at 32K | 1.239 [1.158, 1.325] (n=5) | higher is faster |
| tg at 48K | 1.213 [1.095, 1.343] (n=5) | higher is faster |
| ttft at 16K | 0.479 [0.476, 0.482] (n=5) | lower is faster |
| ttft at 32K | 0.506 [0.502, 0.510] (n=5) | lower is faster |
| ttft at 48K | 0.551 [0.515, 0.590] (n=5) | lower is faster |

### Figures

**stock-64K, clean units**: n_clean 5, n_total 5; T_turn_400 9.288 [9.238, 9.338] s; T_reread 39.073 [38.896, 39.251] s; minimum free VRAM 1,355 MiB; peak VRAM 14,956 MiB; MTP acceptance -

| depth | PP_fresh (tok/s) | PP_inc (tok/s) | TG (tok/s) | T_B (s) | predicted_n | T_reread (s) | TTFT (s) |
|---|---|---|---|---|---|---|---|
| 16K | 864.8 [856.4, 873.1] | 814.9 [804.2, 825.7] | 78.67 [78.49, 78.85] | 8.753 [8.700, 8.807] | 400.0 [400.0, 400.0] | 18.947 [18.763, 19.131] | 3.685 [3.636, 3.733] |
| 32K | 844.2 [840.3, 848.0] | 776.7 [765.4, 788.0] | 73.88 [73.79, 73.97] | 9.263 [9.208, 9.319] | 400.0 [400.0, 400.0] | 38.818 [38.642, 38.994] | 3.868 [3.812, 3.923] |
| 48K | 826.7 [823.9, 829.5] | 737.4 [728.4, 746.3] | 69.53 [69.41, 69.65] | 9.312 [7.945, 10.679] | 365.6 [270.1, 461.1] | 59.455 [59.253, 59.657] | 4.075 [4.026, 4.125] |

**tuned-64K, clean units**: n_clean 5, n_total 5; T_turn_400 6.413 [6.003, 6.824] s; T_reread 16.534 [16.403, 16.664] s; minimum free VRAM 1,021 MiB; peak VRAM 15,290 MiB; MTP acceptance 0.771 pooled over Request B, per unit 0.771 [0.745, 0.798]

| depth | PP_fresh (tok/s) | PP_inc (tok/s) | TG (tok/s) | T_B (s) | predicted_n | T_reread (s) | TTFT (s) |
|---|---|---|---|---|---|---|---|
| 16K | 2151.3 [2142.8, 2159.9] | 1703.8 [1692.2, 1715.5] | 96.51 [89.82, 103.21] | 5.905 [5.608, 6.203] | 400.0 [400.0, 400.0] | 7.616 [7.585, 7.646] | 1.764 [1.752, 1.776] |
| 32K | 2024.9 [2001.7, 2048.0] | 1537.5 [1526.0, 1549.0] | 91.64 [85.48, 97.81] | 6.316 [6.005, 6.626] | 400.0 [400.0, 400.0] | 16.184 [15.996, 16.372] | 1.956 [1.941, 1.971] |
| 48K | 1905.1 [1891.7, 1918.5] | 1341.5 [1254.7, 1428.3] | 84.57 [76.14, 92.99] | 6.985 [6.342, 7.628] | 400.0 [400.0, 400.0] | 25.801 [25.618, 25.984] | 2.248 [2.092, 2.404] |

### Swap sensitivity (section 5.5)

no unit of these cells shows swap growth above 64 MiB: nothing to remove

## 128K: stock-128K and tuned-128K

**Tuned cell eligibility (final mode):** eligible; n_clean 5 of 5; minimum free VRAM 1,211 MiB; sanity pass

**Headline: all units, labelled "includes paging-flagged stock windows".** S4(d) deviation for this context: the headline rests on 1 stock unit(s) with an unresolved flag (stage3-128K:3: paging) because stock-128K has 4 clean and tuned-128K 5 clean unit(s) (4 paired; at least 5 needed for the clean-units headline). Rule S4(d): No selected or recommended configuration, and no headline number, rests on a measurement with an unresolved flag.

| metric | tuned / stock, geometric mean [95% CI] (paired units) | reading |
|---|---|---|
| t_turn_400 | 0.706 [0.679, 0.735] (n=5) | lower is faster |
| t_reread | 0.382 [0.381, 0.384] (n=5) | lower is faster |
| pp_fresh at 32K | 2.926 [2.904, 2.949] (n=5) | higher is faster |
| pp_fresh at 64K | 2.701 [2.689, 2.712] (n=5) | higher is faster |
| pp_fresh at 96K | 2.487 [2.475, 2.500] (n=5) | higher is faster |
| tg at 32K | 1.143 [1.100, 1.189] (n=5) | higher is faster |
| tg at 64K | 1.136 [1.074, 1.202] (n=5) | higher is faster |
| tg at 96K | 1.125 [1.046, 1.209] (n=5) | higher is faster |
| ttft at 32K | 0.418 [0.412, 0.424] (n=5) | lower is faster |
| ttft at 64K | 0.473 [0.466, 0.480] (n=5) | lower is faster |
| ttft at 96K | 0.521 [0.516, 0.526] (n=5) | lower is faster |

Clean-units figures beside it:

| metric | tuned / stock, geometric mean [95% CI] (paired units) | reading |
|---|---|---|
| t_turn_400 | 0.711 [0.673, 0.750] (n=4) | lower is faster |
| t_reread | 0.382 [0.380, 0.384] (n=4) | lower is faster |
| pp_fresh at 32K | 2.932 [2.909, 2.955] (n=4) | higher is faster |
| pp_fresh at 64K | 2.703 [2.690, 2.717] (n=4) | higher is faster |
| pp_fresh at 96K | 2.487 [2.469, 2.506] (n=4) | higher is faster |
| tg at 32K | 1.141 [1.078, 1.208] (n=4) | higher is faster |
| tg at 64K | 1.123 [1.049, 1.202] (n=4) | higher is faster |
| tg at 96K | 1.107 [1.017, 1.204] (n=4) | higher is faster |
| ttft at 32K | 0.416 [0.411, 0.422] (n=4) | lower is faster |
| ttft at 64K | 0.472 [0.464, 0.480] (n=4) | lower is faster |
| ttft at 96K | 0.521 [0.514, 0.528] (n=4) | lower is faster |

### Figures

**stock-128K, clean units**: n_clean 4, n_total 5; T_turn_400 11.192 [11.129, 11.255] s; T_reread 94.250 [93.782, 94.717] s; minimum free VRAM 1,369 MiB; peak VRAM 14,942 MiB; MTP acceptance -

| depth | PP_fresh (tok/s) | PP_inc (tok/s) | TG (tok/s) | T_B (s) | predicted_n | T_reread (s) | TTFT (s) |
|---|---|---|---|---|---|---|---|
| 32K | 730.4 [725.1, 735.6] | 675.5 [666.1, 685.0] | 70.08 [69.98, 70.18] | 10.135 [10.070, 10.199] | 400.0 [400.0, 400.0] | 44.867 [44.547, 45.186] | 4.446 [4.384, 4.507] |
| 64K | 704.1 [700.7, 707.5] | 621.6 [613.9, 629.2] | 62.64 [62.47, 62.81] | 10.732 [9.271, 12.194] | 371.0 [278.7, 463.3] | 93.080 [92.634, 93.526] | 4.836 [4.776, 4.895] |
| 96K | 678.9 [674.4, 683.4] | 579.2 [572.5, 586.0] | 56.86 [56.69, 57.03] | 12.197 [12.120, 12.273] | 400.0 [400.0, 400.0] | 144.802 [143.839, 145.766] | 5.191 [5.131, 5.252] |

**stock-128K, all units**: n_clean 5, n_total 5; T_turn_400 11.191 [11.149, 11.234] s; T_reread 94.174 [93.796, 94.553] s; minimum free VRAM 1,369 MiB; peak VRAM 14,942 MiB; MTP acceptance -

| depth | PP_fresh (tok/s) | PP_inc (tok/s) | TG (tok/s) | T_B (s) | predicted_n | T_reread (s) | TTFT (s) |
|---|---|---|---|---|---|---|---|
| 32K | 731.7 [726.6, 736.8] | 678.9 [667.6, 690.1] | 70.02 [69.82, 70.21] | 10.118 [10.056, 10.181] | 400.0 [400.0, 400.0] | 44.785 [44.471, 45.098] | 4.424 [4.352, 4.497] |
| 64K | 705.0 [701.6, 708.3] | 624.1 [615.3, 633.0] | 62.65 [62.53, 62.76] | 10.805 [9.797, 11.813] | 376.8 [312.4, 441.2] | 92.964 [92.524, 93.405] | 4.816 [4.748, 4.884] |
| 96K | 679.0 [675.9, 682.1] | 580.9 [574.4, 587.4] | 56.47 [55.37, 57.56] | 12.232 [12.121, 12.343] | 400.0 [400.0, 400.0] | 144.775 [144.119, 145.430] | 5.178 [5.121, 5.234] |

Units with an unresolved flag (counted in this view): stage3-128K:3 attempt 2: paging, swap growth 4200 MiB

**tuned-128K, clean units**: n_clean 5, n_total 5; T_turn_400 7.910 [7.609, 8.210] s; T_reread 35.977 [35.961, 35.994] s; minimum free VRAM 1,211 MiB; peak VRAM 15,100 MiB; MTP acceptance -

| depth | PP_fresh (tok/s) | PP_inc (tok/s) | TG (tok/s) | T_B (s) | predicted_n | T_reread (s) | TTFT (s) |
|---|---|---|---|---|---|---|---|
| 32K | 2141.1 [2138.7, 2143.6] | 1626.5 [1620.9, 1632.2] | 80.09 [77.04, 83.14] | 6.830 [6.633, 7.027] | 400.0 [400.0, 400.0] | 15.304 [15.286, 15.322] | 1.849 [1.843, 1.855] |
| 64K | 1903.8 [1902.2, 1905.5] | 1321.8 [1313.4, 1330.2] | 71.24 [67.31, 75.17] | 7.879 [7.548, 8.211] | 400.0 [400.0, 400.0] | 34.423 [34.393, 34.453] | 2.278 [2.263, 2.292] |
| 96K | 1688.9 [1687.9, 1690.0] | 1116.2 [1109.1, 1123.3] | 63.57 [59.75, 67.40] | 8.977 [8.569, 9.385] | 400.0 [400.0, 400.0] | 58.205 [58.169, 58.241] | 2.699 [2.682, 2.717] |

**tuned-128K, all units**: n_clean 5, n_total 5; T_turn_400 7.910 [7.609, 8.210] s; T_reread 35.977 [35.961, 35.994] s; minimum free VRAM 1,211 MiB; peak VRAM 15,100 MiB; MTP acceptance -

| depth | PP_fresh (tok/s) | PP_inc (tok/s) | TG (tok/s) | T_B (s) | predicted_n | T_reread (s) | TTFT (s) |
|---|---|---|---|---|---|---|---|
| 32K | 2141.1 [2138.7, 2143.6] | 1626.5 [1620.9, 1632.2] | 80.09 [77.04, 83.14] | 6.830 [6.633, 7.027] | 400.0 [400.0, 400.0] | 15.304 [15.286, 15.322] | 1.849 [1.843, 1.855] |
| 64K | 1903.8 [1902.2, 1905.5] | 1321.8 [1313.4, 1330.2] | 71.24 [67.31, 75.17] | 7.879 [7.548, 8.211] | 400.0 [400.0, 400.0] | 34.423 [34.393, 34.453] | 2.278 [2.263, 2.292] |
| 96K | 1688.9 [1687.9, 1690.0] | 1116.2 [1109.1, 1123.3] | 63.57 [59.75, 67.40] | 8.977 [8.569, 9.385] | 400.0 [400.0, 400.0] | 58.205 [58.169, 58.241] | 2.699 [2.682, 2.717] |

### Swap sensitivity (section 5.5)

no sign change and no interval moved by more than its half-width

Removed (swap growth above 64 MiB): stock-128K stage3-128K:3 (4200 MiB)

## Provenance

- plan version: 1.8
- code commit of this tool: 17c17cdee326f9a06ea5346ed1c75f6f07239d70 (dirty: False)
- llama.cpp commit: 57d04820dfef7a3519aac276d018a6fd71251895
- sanity file: data/sanity/stage3-tuned.json
- session `stage3-32K`: spec `configs/sweeps/stage3.toml` sha256 41a0e384d622fcb2, session code commit 80964618df, state complete, filters {'context': '32K'}
- session `stage3-64K`: spec `configs/sweeps/stage3.toml` sha256 41a0e384d622fcb2, session code commit a80b2dd31a, state complete, filters {'context': '64K'}
- session `stage3-128K`: spec `configs/sweeps/stage3.toml` sha256 41a0e384d622fcb2, session code commit b5b7396231, state complete, filters {'context': '128K'}
- config file sha256: stock-128k.toml 23290bf84a00, stock-32k.toml a5fcd6ee55d5, stock-64k.toml 398ec7e6293d, tuned-128k.toml 88ef17758630, tuned-32k.toml dd1ba72640d8, tuned-64k.toml 538ce78cbf49

### Rules applied (plan v1.7 section 5.4, verbatim)

> - **Configurations.** The six cells are the released config files, `configs/server/{stock,tuned}-{32k,64k,128k}.toml`. The tuned files are the Stage 2 winners above. Stock is §3.1 unchanged, including its default host prompt cache. The measured argument lists are exactly what those files render, plus `--metrics -lv 4`.

> - **Sessions.** One session per context, each with its own start and end canaries, from a clean committed tree. Stock and tuned of a context share a session, so their repetitions are paired.

> - **Re-runs.** One `--rerun-flagged` pass per session, as before.

> - **Stock paging.** Stock keeps `--cache-ram 8192`, so its later repetitions may be paging-flagged at 64K and 128K. That is how stock behaves on this machine, so it is reported, not hidden. Every stock-against-tuned comparison is computed twice: on clean units only, and on all units with the flags shown.

> - **Headline rule.** The headline for a context is the clean-units comparison if both cells have at least 5 clean, paired units after the re-run pass. Otherwise the headline is the all-units comparison, labelled "includes paging-flagged stock windows", with the clean-units figures beside it, and S4(d) is recorded as a deviation for that context. If the two versions disagree in sign, or one interval excludes 1.0 and the other does not, the report says so in its first paragraph.

> - **Tuned cells.** A tuned cell must be eligible in final mode (§3.3): 5 clean units, at least 512 MiB of VRAM free, and a sanity pass. The sanity check is run again on the three tuned config files. If a tuned cell is not eligible, the step lead decides; nothing is substituted automatically.

> - **Reported figures.** Per context: T_turn_400, T_B with `predicted_n`, T_reread, PP_fresh and PP_inc per depth, TG per depth, TTFT, the VRAM breakdown, and the paired ratios tuned/stock with 95% CIs (§5.5), plus the swap sensitivity.

> Stock-64K and tuned-64K, 5 repetitions each, in one session with canaries. S2 is checked with `report repro` on T_turn_400, fresh prefill at 32K and decode at 32K depth. If stock-64K has too few clean units on either day, S2 is evaluated for it on all units, and the report says so.
