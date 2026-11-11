# Stage 2 summary (WP12), for the step lead and the executive chat

Tuned configurations per context, as measured on the Ornith-1.5-35B-A3B Q4 model, llama.cpp `57d04820`, 16 GB RTX 5060 Ti, 5 repetitions per cell. All carry `--cache-ram 2048`,
`-fa on`, `-np 1`, batch and ubatch 4096. Figures come from `smallpc.analysis` over the named session; the selections from the files named in the last column. The tuned configs are
**provisional**: 2c was not run and 2d was skipped (see the decisions below).

## Tuned configs

| context | placement | MTP draft length | KV type | expert cache (MiB, probed) | sanity | decided by |
|---|---|---|---|---|---|---|
| 32K | P6 (`-cmoe`) | off | 8-bit (default) | 11,520 | pass | final selection, `data/analysis/stage2/32K-final.md` (session `s2a-32K`) |
| 64K | P6 | 1 | FP16 | 9,472 | pass | 2a2 (`2a2.md`) then 2b (`2b.md`, rule) |
| 128K | P6 | off | FP16 | 8,704 | pass | 2a2 (`2a2.md`) then 2b (`2b.md`, rule) |

Rendered llama-server argument lists (binary `<repo>/third_party/llama.cpp/build/bin/llama-server`, model `<repo>/models/Ornith-1.5-35B-Q4_K_M.gguf`, `<repo>` = `/mnt/data/local-ai-research`):
```
32K  llama-server -m <model> --host 127.0.0.1 --port 8080 -c 32768 -cmoe --moe-cache-mib 11520 -b 4096 -ub 4096 -ctk q8_0 -ctv q8_0 -fa on -np 1 --cache-ram 2048 --metrics -lv 4
64K  llama-server -m <model> --host 127.0.0.1 --port 8080 -c 65536 -cmoe --moe-cache-mib 9472 -b 4096 -ub 4096 -ctk f16 -ctv f16 -fa on -np 1 --spec-type draft-mtp --spec-draft-n-max 1 --cache-ram 2048 --metrics -lv 4
128K llama-server -m <model> --host 127.0.0.1 --port 8080 -c 131072 -cmoe --moe-cache-mib 8704 -b 4096 -ub 4096 -ctk f16 -ctv f16 -fa on -np 1 --cache-ram 2048 --metrics -lv 4
```

## Results (PP_fresh and TG at the middle depth: 16,384 at 32K, 32,768 at 64K, 65,536 at 128K)

| context | cell | T_turn_400 s [95% CI] | T_reread s | PP_fresh tok/s | TG tok/s | min free VRAM MiB | MTP accept. (Request B) | session |
|---|---|---|---|---|---|---|---|---|
| 32K | **tuned** `s2a-P6-32K-b4096-mtp0` | 5.916 [5.608, 6.224] | 6.692 | 2,481.9 | 91.5 | 1,379 | - | s2a-32K |
| 32K | runner-up `s2a-P6-32K-b4096-mtp3` | 5.914 [5.602, 6.226] | 7.480 | 2,211.0 | 96.9 | 1,069 | 0.552 | s2a-32K |
| 32K | Stage 1 stock (screening, n = 2) | 8.451 [8.400, 8.501] | - | - | - | 1,385 | - | stage1-32K |
| 64K | **tuned** `s2b-P6-64K-b4096-mtp1-kvf16` | 6.486 [6.128, 6.845] | 16.756 | 1,997.3 | 90.4 | 1,019 | 0.771 | s2b |
| 64K | runner-up `s2a2-P2-64K-b4096-mtp0` | 7.108 [7.076, 7.140] | 12.192 | 2,767.7 | 70.7 | 545 | - | s2a2-64K |
| 64K | Stage 1 stock (screening, n = 2) | 9.360 [9.093, 9.628] | - | - | - | 1,353 | - | stage1-64K |
| 128K | **tuned** `s2b-P6-128K-b4096-mtp0-kvf16` | 7.967 [7.669, 8.266] | 36.002 | 1,907.4 | 71.0 | 1,211 | - | s2b-128K |
| 128K | runner-up `s2a2-P6-128K-b4096-mtp1` (8-bit KV) | 8.701 [8.222, 9.180] | 41.116 | 1,673.4 | 66.8 | 1,059 | 0.786 | s2a2-128K |
| 128K | Stage 1 stock (screening, n = 2) | 11.290 [10.892, 11.689] | - | - | - | 1,365 | - | stage1-128K |

32K: the two best candidates tie on T_turn_400 (paired difference 0.001 s, CI [-0.177, 0.180]); the lower T_reread of the MTP-off cell decides (paired -0.788 s [-0.861, -0.715]). 64K tuned against its
runner-up: P6 is faster on T_turn_400 by the rule (2a2) but slower on T_reread and prefill; 128K: FP16 KV is faster than 8-bit by 0.683 s [0.435, 0.932] (`2b.md`).

## Sanity check (plan §5.6)
MTP at draft length 2 fails prompt r0 (an 8-gram repeats 8 times, the reference 2) at 32K and at 64K, on four different placement, KV and context configs, deterministically; MTP off and draft lengths 1 and 3 pass
(`data/sanity/diagnostic-*.json`, `stage2-all.json`). The thresholds were not changed. Draft length 2 is excluded from all tuned configs.

## Human decisions and rule deviations in Stage 2 (one line each; where recorded)
1. 2f: `--cache-ram 2048` chosen (`docs/decisions.md`, "Stage 2f decision").
2. 2a 64K gate: criterion f changed to more than 40 % flagged or any flagged window above 1,024 MiB swap (`decisions.md`, "Stage 2a 64K gate").
3. Re-run summary writer bug: fixed in `src/`, 21 cell summaries repaired by script with an audit log, 2a decision regenerated (`decisions.md`, "Stage 2a decisions"; `data/raw/*/repairs.jsonl`).
4. `s2a-P6-32K-b4096-mtp1` ineligible (paging, n_clean 4): the rule stands, sensitivity reported (`decisions.md`, "Stage 2a decisions"; `2a-paging-sensitivity.md`).
5. 128K gap: when the top placement has no eligible MTP cell, 2a2 tests the second placement at the draft lengths that won elsewhere (a plan extension, `decisions.md`, "Stage 2a decisions").
6. Swap-sensitivity reading: fewer than 2 paired units left is "inconclusive" (`decisions.md`, "Stage 2b decision and extension"; code in `src/smallpc/stage2/decide.py`).
7. 2b extended to 32K and 128K (plan: 64K only), on the 2a2 winners (`decisions.md`, "Stage 2b decision and extension").
8. Probe-cache reuse for six P6 cells instead of fresh probes: accepted (same key and values as 2a) (`decisions.md`, "Stage 2b decision and extension").
9. 2b 32K: FP16 KV chosen by the step lead on the draft-length-2 cells; void for the tuned config after the sanity failure (`decisions.md`, "Stage 2b 32K decision" and "Stage 2 sanity result and closing decisions"; `2b-human-decision.md`).
10. Sanity failure of draft length 2: the rule stands, thresholds unchanged, diagnostic read as declared (`decisions.md`, "Stage 2 sanity result and closing decisions").
11. 2c (`--load-mode dio`) not run, 2d skipped (default threads 8): plan deviations (`decisions.md`, "Stage 2 sanity result and closing decisions").
12. 32K tuned config = the final-selection winner `s2a-P6-32K-b4096-mtp0` with 8-bit KV; FP16 against 8-bit was measured at 32K only on draft-length-2 cells, so the 32K KV type of this config is the default, not a 2b result (`32K-final.md`).
13. `--from-2f` used for the 2a spec instead of `--cache-ram 2048` (the tool refuses both together) (`progress-log.md`, part 2b).
14. The reference's own name cannot be run as a cell by the sanity runner; the self-check used a byte-identical copy of its resolved config (`stage2-conditions.md`, "Sanity diagnostic").
15. The Stage 2 report carries the label `screening` (as instructed) with a banner changed to carry no repetition count (`progress-log.md`, part 2g).
16. VRAM breakdown: bars of MTP cells extend past the card total because the log parser sums repeated compute-buffer reservations; documented, no measurement code changed (`reports/stage2/vram-accounting-check.md`).
