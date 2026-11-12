# VRAM accounting check (Stage 2 cells)

Load-log buffers against the measured peak used VRAM (MiB). `compute parsed` sums every
`CUDA0 compute buffer` line of the log, which is what the parser did before WP13 and what the
breakdown figure plotted; `other before` is the remainder (peak minus the parts) with it, negative
where the parts exceeded the peak (the bar then extended past the card's total). `compute resident`
is the figure now used (the last reservation of each llama_context; the scheduler of a
re-reserving context frees its old compute buffers first, llama.cpp `llama-context.cpp`
`sched_new`), and `other now` the remainder with it.

| cell | MTP | CUDA0 compute lines | compute parsed (before) | compute resident (now) | peak | other before | other now |
|---|---|---|---|---|---|---|---|
| s2a-P2-128K-b4096-mtp0 | no | [2034.16] | 2,034 | 2,034 | 15,762 | 344 | 344 |
| s2a-P2-128K-b4096-mtp1 | yes | [2034.16, 1344.12, 1344.12, 1872.16] | 6,595 | 3,216 | 15,890 | -2,862 | 517 |
| s2a-P2-128K-b4096-mtp2 | yes | [2034.16, 1344.12, 1344.12, 1872.16] | 6,595 | 3,216 | 15,806 | -2,862 | 516 |
| s2a-P2-128K-b4096-mtp3 | yes | [2034.16, 1344.12, 1344.12, 1872.16] | 6,595 | 3,216 | 15,868 | -2,863 | 516 |
| s2a-P2-32K-b4096-mtp0 | no | [1104.16] | 1,104 | 1,104 | 15,744 | 337 | 337 |
| s2a-P2-64K-b4096-mtp0 | no | [1360.16] | 1,360 | 1,360 | 15,766 | 340 | 340 |
| s2a-P6-128K-b4096-mtp0 | no | [2116.03] | 2,116 | 2,116 | 14,930 | 363 | 363 |
| s2a-P6-32K-b4096-mtp0 | no | [1348.03] | 1,348 | 1,348 | 14,932 | 359 | 359 |
| s2a-P6-32K-b4096-mtp1 | yes | [1348.03, 638.28, 638.28, 1348.03] | 3,973 | 1,986 | 15,116 | -1,462 | 524 |
| s2a-P6-32K-b4096-mtp2 | yes | [1348.03, 638.28, 638.28, 1348.03] | 3,973 | 1,986 | 15,180 | -1,461 | 525 |
| s2a-P6-32K-b4096-mtp3 | yes | [1348.03, 638.28, 638.28, 1348.03] | 3,973 | 1,986 | 15,242 | -1,462 | 524 |
| s2a-P6-64K-b4096-mtp0 | no | [1604.03] | 1,604 | 1,604 | 15,018 | 361 | 361 |
| s2a-P6-64K-b4096-mtp1 | yes | [1604.03, 832.12, 832.12, 1604.03] | 4,872 | 2,436 | 15,206 | -1,908 | 528 |
| s2a-P6-64K-b4096-mtp2 | yes | [1604.03, 832.12, 832.12, 1604.03] | 4,872 | 2,436 | 15,270 | -1,907 | 529 |
| s2a-P6-64K-b4096-mtp3 | yes | [1604.03, 832.12, 832.12, 1604.03] | 4,872 | 2,436 | 15,074 | -1,909 | 527 |
| s2a2-P2-128K-b4096-mtp0 | no | [2034.16] | 2,034 | 2,034 | 15,762 | 344 | 344 |
| s2a2-P2-32K-b4096-mtp0 | no | [1104.16] | 1,104 | 1,104 | 15,744 | 337 | 337 |
| s2a2-P2-32K-b4096-mtp2 | yes | [1104.16, 638.28, 638.28, 1104.16] | 3,485 | 1,742 | 15,696 | -1,230 | 513 |
| s2a2-P2-64K-b4096-mtp0 | no | [1360.16] | 1,360 | 1,360 | 15,766 | 340 | 340 |
| s2a2-P2-64K-b4096-mtp1 | yes | [1360.16, 832.12, 832.12, 1360.16] | 4,385 | 2,192 | 15,914 | -1,680 | 512 |
| s2a2-P6-128K-b4096-mtp0 | no | [2116.03] | 2,116 | 2,116 | 14,930 | 363 | 363 |
| s2a2-P6-128K-b4096-mtp1 | yes | [2116.03, 1344.12, 1344.12, 2116.03] | 6,920 | 3,460 | 15,252 | -2,928 | 532 |
| s2a2-P6-128K-b4096-mtp2 | yes | [2116.03, 1344.12, 1344.12, 2116.03] | 6,920 | 3,460 | 15,056 | -2,928 | 532 |
| s2a2-P6-32K-b4096-mtp2 | yes | [1348.03, 638.28, 638.28, 1348.03] | 3,973 | 1,986 | 15,180 | -1,461 | 525 |
| s2a2-P6-64K-b4096-mtp1 | yes | [1604.03, 832.12, 832.12, 1604.03] | 4,872 | 2,436 | 15,206 | -1,908 | 528 |
| s2b-P6-128K-b4096-mtp0-kvf16 | no | [2116.03] | 2,116 | 2,116 | 15,100 | 358 | 358 |
| s2b-P6-128K-b4096-mtp0-kvq8 | no | [2116.03] | 2,116 | 2,116 | 14,928 | 361 | 361 |
| s2b-P6-32K-b4096-mtp2-kvf16 | yes | [1348.03, 638.28, 638.28, 1348.03] | 3,973 | 1,986 | 15,222 | -1,463 | 524 |
| s2b-P6-32K-b4096-mtp2-kvq8 | yes | [1348.03, 638.28, 638.28, 1348.03] | 3,973 | 1,986 | 15,180 | -1,461 | 525 |
| s2b-P6-64K-b4096-mtp1-kvf16 | yes | [1604.03, 832.12, 832.12, 1604.03] | 4,872 | 2,436 | 15,290 | -1,913 | 523 |
| s2b-P6-64K-b4096-mtp1-kvq8 | yes | [1604.03, 832.12, 832.12, 1604.03] | 4,872 | 2,436 | 15,208 | -1,906 | 530 |

- cells with parsed parts above the peak: 19 of 31; MTP cells among them: 19; non-MTP cells among them: 0.
- `other` of the non-MTP cells: 337 to 363 MiB (the CUDA context and similar).
- `other` of the MTP cells with the resident compute buffers: 512 to 532 MiB (about 170 MiB above the non-MTP cells, the same at every context size; not a compute buffer of the log).
- cells with parsed parts above the peak after the fix: 0.
- In every cell peak + minimum free = the card's total, so the measured side is consistent; the overshoot was in the parsed side.
