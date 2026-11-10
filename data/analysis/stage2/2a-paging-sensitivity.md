# Stage 2a: sensitivity to paging-flagged cells

Read-only recomputation (`tools/stage2_paging_sensitivity.py`). Every cell that is ineligible only because of paging-flagged units is treated as eligible on its clean units. Information only: the declared rule's result stands.

## Cells treated as eligible

| cell | n_clean/n_total | reasons by the rule |
|---|---|---|
| `s2a-P6-32K-b4096-mtp1` | 4/5 | flagged unit(s) s2a-32K:4 (paging); n_clean 4 is below 5 (final mode) |

## Decision by context

| context | best_draft_length | mtp_wins_on_t_turn_400 | mtp_vs_off_winner | top_config_mtp | second_mtps |
|---|---|---|---|---|---|
| 32K | **2 -> 1** | True | **s2a-P6-32K-b4096-mtp2 -> s2a-P6-32K-b4096-mtp1** | **2 -> 1** | **[2] -> [1]** |
| 64K | 1 | True | s2a-P6-64K-b4096-mtp1 | 1 | [1] |
| 128K | None | None | None | 0 | **[1, 2] -> [1]** |

**Any decision changes: YES.**

```json
{
 "32K": {
  "best_draft_length": {
   "by_rule": 2,
   "if_treated_eligible": 1
  },
  "mtp_vs_off_winner": {
   "by_rule": "s2a-P6-32K-b4096-mtp2",
   "if_treated_eligible": "s2a-P6-32K-b4096-mtp1"
  },
  "top_config_mtp": {
   "by_rule": 2,
   "if_treated_eligible": 1
  },
  "second_mtps": {
   "by_rule": [
    2
   ],
   "if_treated_eligible": [
    1
   ]
  }
 },
 "128K": {
  "second_mtps": {
   "by_rule": [
    1,
    2
   ],
   "if_treated_eligible": [
    1
   ]
  }
 }
}
```
