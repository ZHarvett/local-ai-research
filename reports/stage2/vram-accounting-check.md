# VRAM accounting check (Stage 2 cells)

Parsed load-log buffers against the measured peak used VRAM (MiB). `other` is what the
breakdown figure plots as the remainder (peak minus the parsed parts); it is negative where
the parsed parts exceed the peak, and the bar then extends past the card's total. `resident`
counts the compute buffers as resident if each reservation replaces the earlier one of its
context (an MTP log lists target, draft, draft, target: the last two). This is an estimate
checked only by consistency (below), not by inspecting the allocator.

| cell | MTP | CUDA0 compute lines | compute parsed | compute resident | peak | other as plotted | other if resident |
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
- `other` of the MTP cells with the compute buffers counted as resident: 512 to 532 MiB.
- In every cell peak + minimum free = the card's total, so the measured side is consistent; the overshoot is in the parsed side.
