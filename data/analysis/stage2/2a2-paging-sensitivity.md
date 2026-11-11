# Stage 2a2: sensitivity to paging-flagged cells

Read-only recomputation (`tools/stage2_paging_sensitivity.py`). Every cell that is ineligible only because of paging-flagged units is treated as eligible on its clean units. Information only: the declared rule's result stands.

## Cells treated as eligible

None: no cell is ineligible only because of paging.

## Decision by context

| context | status | winner | runner_up | tied_with_winner |
|---|---|---|---|---|
| 32K | decided | s2a2-P6-32K-b4096-mtp2 | s2a2-P2-32K-b4096-mtp2 | [{'cell': 's2a2-P2-32K-b4096-mtp0', 'paired_difference_mean': 0.6855991766081873, 'ci': [0.5240384273768045, 0.84715992583957], 'tied': False, 'comparable': True}] |
| 64K | decided | s2a2-P6-64K-b4096-mtp1 | s2a2-P2-64K-b4096-mtp0 | [] |
| 128K | decided | s2a2-P6-128K-b4096-mtp0 | s2a2-P6-128K-b4096-mtp1 | [{'cell': 's2a2-P6-128K-b4096-mtp2', 'paired_difference_mean': 0.28120531278195526, 'ci': [0.19196729416786812, 0.3704433313960424], 'tied': False, 'comparable': True}, {'cell': 's2a2-P2-128K-b4096-mtp0', 'paired_difference_mean': 0.3789269550543029, 'ci': [0.043781890932432954, 0.7140720191761729], 'tied': False, 'comparable': True}] |

**Any decision changes: no.**
