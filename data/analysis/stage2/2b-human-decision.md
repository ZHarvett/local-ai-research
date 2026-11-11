# Stage 2b: human decision for 32K (2026-11-11)

**This file records a human decision (the step lead), not the output of the decision tool.** The tool's output is `2b.json` and `2b.md` next to this file, unchanged.

## Decision

| context | KV type of the tuned config | how decided |
|---|---|---|
| 32K | **FP16** (`-ctk f16 -ctv f16`) | human decision (tie broken by simplicity) |
| 64K | **FP16** | the rule (`ci_excludes_zero`); the swap sensitivity is inconclusive (1 paired unit left) |
| 128K | **FP16** | the rule (`ci_excludes_zero`); the swap sensitivity does not change it (3 paired units) |

## 32K: the two readings

| reading | winner | step | numbers |
|---|---|---|---|
| the rule (all 5 units per cell) | kvq8 | `t_reread` | T_turn_400: kvf16 5.546 s [5.291, 5.800], kvq8 5.596 s [5.437, 5.755]; paired difference (other minus best = kvq8 minus kvf16) +0.050 s [-0.050, +0.151], includes zero. T_reread: kvf16 7.408 s, kvq8 7.370 s; paired difference -0.038 s [-0.052, -0.025], excludes zero |
| swap sensitivity (repetition 1 of both cells removed: 699 and 637 MiB of swap growth; 4 paired units left) | kvf16 | `ci_excludes_zero` | T_turn_400: kvf16 5.469 s [5.261, 5.678], kvq8 5.552 s [5.401, 5.704]; paired difference +0.083 s [+0.019, +0.147] |

## Reason

The two readings disagree and neither is robust, so 32K is treated as a tie; both put the difference at about 1 % or less. The tie is broken by simplicity: FP16 is llama.cpp's default and
lossless, it won by the rule at 64K and 128K, and the tuned configs then need no KV flags.

Recorded in `docs/decisions.md`, section "Stage 2b 32K decision".
