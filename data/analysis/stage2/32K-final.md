# Eligibility and selection

> **RESULTS. Only cells with at least 5 clean repetitions are reportable.**

Mode **final**: a cell needs at least 5 clean repetitions, a complete status, at least 512 MiB free VRAM at its tightest, no flagged unit and a sanity check that has not failed (and must pass).

## 32K

> RESULTS. Only cells with at least 5 clean repetitions are reportable.

| cell | role | n_clean/n_total | mean T_turn_400 (s) [95% CI] | eligible | reasons it is not | sanity |
|---|---|---|---|---|---|---|
| s2a-P2-32K-b4096-mtp0 | candidate | 5/5 | 6.30 [6.28, 6.31] | yes | - | pass |
| s2a-P6-32K-b4096-mtp0 | candidate | 5/5 | 5.92 [5.61, 6.22] | yes | - | pass |
| s2a-P6-32K-b4096-mtp1 | candidate | 4/5 | 5.78 [5.43, 6.14] | no | flagged unit(s) s2a-32K:4 (paging); n_clean 4 is below 5 (final mode) | pass |
| s2a-P6-32K-b4096-mtp2 | candidate | 5/5 | 5.63 [5.45, 5.81] | no | failed the output sanity check | fail |
| s2a-P6-32K-b4096-mtp3 | candidate | 5/5 | 5.91 [5.60, 6.23] | yes | - | pass |

**Winner (32K):** `s2a-P6-32K-b4096-mtp0`. Decision: T_turn_400 tied; the paired T_reread CI excludes zero: lower T_reread wins.
Runner-up: `s2a-P6-32K-b4096-mtp3`.
- paired T_turn_400 difference (runner-up minus best mean), n = 5: 0.001 s, CI [-0.177, 0.180] (t).
- paired T_reread difference (runner-up minus best mean), n = 5: -0.788 s, CI [-0.861, -0.715] (t).


- `s2a-P6-32K-b4096-mtp0`: VRAM model 1303, KV 340, recurrent 63, compute 1348, expert cache 11520, other 358.6 MiB; minimum free 1379.0 MiB; expert-cache decode-batch hit rate 97.0%.
- `s2a-P6-32K-b4096-mtp3`: VRAM model 1326, KV 404, recurrent 251, compute 3973, expert cache 10750, other -1462.0 MiB; minimum free 1069.0 MiB; expert-cache decode-batch hit rate 95.4%.

## Provenance

| session | spec | spec sha256 | session code commit |
|---|---|---|---|
| s2a-32K | configs/sweeps/stage2-2a.toml | a4e031802c25d405 | 60edde1c8f |

- sanity file: `data/sanity/stage2-all.json` (sha256 974a4f5ff53232ec)
- plan version: 1.6
- code commit of this tool: 5b23955b11481ca0e9d4955cd07f4263a6306ef0 (dirty: False)
- llama.cpp commit: 57d04820dfef7a3519aac276d018a6fd71251895

### Rule text applied (plan v1.6, verbatim)

> "Top" means first in the Stage 1 order, even where the pair is too close to call at n = 2.

> - **2a MTP.** Per context, 6 cells: both shortlisted placements with MTP off (these are also the 5-repetition measurement of the shortlist), the top placement with draft lengths 1, 2 and 3, and the second placement with the best draft length of the top placement. The best draft length is chosen by the §3.3 rules among the three; if the CIs include zero, the smaller draft length wins. Cache sizes of P6 cells are re-probed with MTP on, because the head and its draft context cost VRAM. Record acceptance, and the effect on decode **and on prefill**. MTP joins a tuned config only if it wins by §3.3 on T_turn_400 and passes the output sanity check.

> A candidate is eligible for a context if:
> - its final cell status is complete (it started without errors and finished);
> - the minimum free VRAM across its measured windows, in the final attempt, is at least 512 MiB;
> - it has no unresolved flagged unit, where a unit is one repetition and an attempt-2 unit replaces the attempt-1 unit it re-ran;
> - it has enough clean units: 2 in screening, 5 in final selection;
> - it has not failed the output sanity check (§5.6). In screening the check may be "not run". In final selection it must have passed.
>
> Among eligible candidates, order them by the **mean T_turn_400** (the estimated standardised turn, §5.3): the mean over repetitions of each repetition's mean over the three depths of §5.3. A repetition counts only if all three depths are clean. Final selection then compares the best-mean candidate with the runner-up, using the paired per-repetition difference of T_turn_400 and its 95% CI (§5.5):
> 1. If the CI excludes zero, the best-mean candidate wins.
> 2. If the CI includes zero, compare the paired difference of **T_reread** in the same way. If that CI excludes zero, the candidate with the lower mean T_reread wins.
> 3. If both CIs include zero, the candidates are tied on speed: prefer fewer moving parts, which means no MTP over MTP, then no expert cache over a cache.
> 4. If still tied, prefer the lower peak VRAM use (total minus the minimum free VRAM over its windows).
>
> Any other eligible candidate whose paired T_turn_400 difference from the winner has a CI that includes zero is reported as "statistically tied with the winner", for information only. Screening (2 repetitions) applies no tie-break: its shortlist is simply the two eligible candidates with the lowest mean T_turn_400 per context, and pairs whose means differ by less than the larger of their two ranges are marked "too close to call at n = 2". The stock cell is a reference row and is never shortlisted.
