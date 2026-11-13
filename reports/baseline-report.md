# Baseline report — Ornith-1.5-35B-A3B (Q4) on a 16 GB RTX 5060 Ti

<!-- sources: data/analysis/stage3/headline.md, data/analysis/stage3/headline.json, reports/stage3/report.md, data/sanity/stage3-tuned.json, docs/stage2-summary.md, reports/stage1/select-screening.md, reports/stage2/report.md, docs/decisions.md, docs/plans/step-0-baseline.md, data/env/build-info.json, configs/model.toml, configs/harness.toml, configs/machine.toml -->

> **DRAFT (T-005).** Step 0 baseline. Stage 3 is the headline result; Stages 1 and 2 are
> selection data. The reproducibility check (S2, Stage 4) and the release (S5) are not yet
> done and are marked `<!-- TODO-T010 -->` below; T-010 finalises this report. Every number
> here is copied from a named repo file (declared in `sources:` comments) or marked as
> derived (`derived:` comments); `tools/check_doc_numbers.py` verifies this.

## 1. Summary

This report records what a 16 GB RTX 5060 Ti PC actually does with the Ornith-1.5-35B-A3B
MoE model (one Q4-class GGUF) under mainline llama.cpp, comparing a **stock** server
configuration (the plan's §3.1 defaults, unchanged) against a **tuned** configuration chosen
by a pre-declared rule, at 32K, 64K and 128K context.

The headline result (Stage 3, quiet machine, 5 paired repetitions per cell) is that the tuned
configuration is faster than stock on the standardised turn at every context. The paired
tuned/stock ratio of the estimated 400-token turn time (T_turn_400, lower is faster) is:

<!-- sources: data/analysis/stage3/headline.md -->

| context | headline basis | T_turn_400 tuned/stock, geometric mean [95% CI] | pairs |
|---|---|---|---|
| 32K | clean units | 0.705 [0.672, 0.739] | 5 |
| 64K | clean units | 0.690 [0.649, 0.734] | 5 |
| 128K | all units, includes paging-flagged stock windows | 0.706 [0.679, 0.735] | 5 |

At 128K the headline uses **all units** and is labelled "includes paging-flagged stock
windows" (decision D1, the declared §5.4 headline rule): stock-128K has 4 clean units after
its one re-run pass and tuned-128K has 5, so there are only 4 clean paired units — fewer than
the 5 the clean-units headline needs. The clean-units figures stand beside it (the 128K section below);
the two versions agree in sign and in whether each interval excludes 1.0. This is a recorded
S4(d) deviation for 128K, not a judgement call.

Fresh prefill is roughly 2.3–2.9× faster tuned than stock and decode roughly 1.1–1.2× faster at the measured depths <!-- derived: range of pp_fresh ratios 2.304–2.926 and tg ratios 1.089–1.239 in headline.md --> (Stage 3 below). The tuned configuration adds the expert cache (`-cmoe --moe-cache-mib`), a single slot (`-np 1`) and batch/ubatch 4096; MTP is enabled at 64K only.

Nothing here is a speed target met or missed: Step 0 has no hard speed targets (plan §2).
Stages 1 and 2 were measured with the desktop apps open (a recorded deviation); Stage 3 was
measured on a quiet machine.

## 2. Setup and provenance

<!-- sources: data/env/build-info.json, configs/model.toml, configs/harness.toml, configs/machine.toml, docs/decisions.md -->

**Machine.** RTX 5060 Ti, 16 GB VRAM, no display clients (both monitors on the motherboard
iGPU); AMD Ryzen 7 9700X (8 cores / 16 threads); 32 GB system RAM; repo, model and data on a
256 GB SK hynix NVMe SSD (btrfs, `compress=zstd:1`). Machine tuning is frozen for the project
and recorded with every run (plan §4, §5.7; `configs/machine.toml`, `docs/environment.md`).

**Engine.** Mainline llama.cpp, newest b-tag built at WP3: tag `b12208`, commit
`57d04820dfef7a3519aac276d018a6fd71251895` (the upstream semver tag `v0.9.0` is recorded only;
the b-tag is what is built). CUDA, `CMAKE_CUDA_ARCHITECTURES=120` (CMake rewrote it to `120a`),
Release. Built 2026-11-08. Source: `data/env/build-info.json`.

**Model.** Official `ornith-ai/Ornith-1.5-35B-A3B-GGUF`, file `Ornith-1.5-35B-Q4_K_M.gguf`
(21,713,463,040 bytes), pinned to revision `f60452672689e0040be350560267a614cc172a18`
(2026-08-24, the newest commit that changed the file's content; after the required
2026-08-23 MTP weights update). Base repo `ornith-ai/Ornith-1.5-35B-A3B` at
`10fbf86fed7ecee4a061f8b499a618f46001cac1`. License MIT. The chat template **embedded in the
GGUF** is used in every stage and config (WP5 decision); it differs from the official template
(7828 vs 7536 bytes after whitespace normalisation, the "Unsloth fixes – developer role, tool
calling" variant). Source: `configs/model.toml`, `docs/decisions.md` (WP4, WP5).

**Harnesses.** Control: OpenCode `opencode-ai` 1.19.5. Research: dsh `@deepseek-ai/dsh`
0.2.1-rc.5 (295 `@deepseek-ai/dsh-*` plugins, all at the same version). Runtime node 26.13.0,
npm 12.2.1. Pinned by the WP7 7-day rule; the whole lockfile (643 name@version pairs) was
checked against registry publish times, none too new. Source: `configs/harness.toml`.

Exact identifiers (verbatim from the source files above):

```text
llama.cpp tag        b12208
llama.cpp commit     57d04820dfef7a3519aac276d018a6fd71251895
llama-server sha256  c6b14a4bb904b323d927254ba8b092296d57a4eaddffa38f2e88f21865144e0b
model repo           ornith-ai/Ornith-1.5-35B-A3B-GGUF
model file           Ornith-1.5-35B-Q4_K_M.gguf
model revision       f60452672689e0040be350560267a614cc172a18
model sha256 (LFS)   42739874cc2ccfdb8523b23fbe52e29b2a7555c8176737ca9ca0b5d59859d41f
model size bytes     21713463040
base repo revision   10fbf86fed7ecee4a061f8b499a618f46001cac1
harness lockfile     d21af6e8f2daea1e6903e42b81268f4fde9385fbade49e78eec7d190e79ccb77
Stage 3 sessions     stage3-32K 80964618df · stage3-64K a80b2dd31a · stage3-128K b5b7396231
Stage 3 spec sha256  41a0e384d622fcb2 (configs/sweeps/stage3.toml, all three sessions)
```

The three Stage 3 session commits differ only by data and re-run commits; one code state
exists (decision E-001). The Stage 3 session commit of record is `8096461`
(`docs/recon/stage3-commit.txt`).

## 3. Method

The measurement design is the plan's §5 (`docs/plans/step-0-baseline.md`), not restated here:

- **§5.1–§5.3** — principles, workloads and the per-cell protocol. The standardised turn
  (§3.4) is a 3,000-token append (Request B) on a depth-d prefix (Request A); T_turn_400 is the
  *estimated* 400-token turn time, kept separate from the measured Request B time T_B (always
  shown with its `predicted_n`). K = 1024 tokens throughout (8K = 8,192 … 96K = 98,304).
- **§5.4** — the sweep stages (Stage 1 screening, Stage 2 feature experiments, Stage 3 final,
  Stage 4 reproducibility) and the headline rule quoted in the 128K section below.
- **§5.5** — statistics: per cell the mean, n, min, max and a 95% CI (the wider of a
  percentile-bootstrap interval, 10,000 resamples, fixed seed, and a t-interval); paired
  comparisons are the geometric mean of per-repetition ratios with the wider of a bootstrap CI
  and a t-interval on the log ratios. Swap sensitivity recomputes every table without the clean
  units whose window shows more than 64 MiB of llama-server swap growth.
- **§5.6** — flags (thermal, paging, drift, short_gen, warm_prefill, cache_miss, accounting,
  did_not_fit) and the output sanity check. The paging flag is more than 1,000 major page faults
  in a measured window; swap growth is recorded, not flagged. Flagged units are re-run once and,
  if still flagged, excluded from headline numbers and kept as excluded diagnostic results.

Every measured run has an environment snapshot, a warm-up and telemetry; llama-server response
`timings` are authoritative (no random-token llama-bench numbers for expert-cache or MTP
results). Servers are started only through `scripts/launch-server.sh`.

## 4. Stages 1 and 2 — selection data (desktop apps open)

> **Selection data, not headline results.** Stage 1 is screening (n = 2); Stage 2 chose the
> tuned configurations. Both ran with the desktop apps open and idle (gate G3 not met), a
> recorded deviation; the runner's idle-CPU gate checked CPU before every cell. Stage 3 (below)
> is the headline measurement on a quiet machine.

### Stage 1 screening shortlist (n = 2)

<!-- sources: reports/stage1/select-screening.md, docs/decisions.md -->

Mean T_turn_400 in seconds with the 95% interval; "top" is first in the Stage 1 order even
where the pair is too close to call at n = 2. Stock is a reference row, never shortlisted.

| context | rank | cell | mean T_turn_400 (s) [95% CI] | note |
|---|---|---|---|---|
| 32K | 1 | P6-32K-b4096 | 6.14 [3.57, 8.70] | too close to call at n = 2 |
| 32K | 2 | P2-32K-b4096 | 6.26 [6.24, 6.29] | too close to call at n = 2 |
| 32K | ref | stock-32K | 8.45 [8.40, 8.50] | - |
| 64K | 1 | P6-64K-b4096 | 7.00 [6.28, 7.72] | - |
| 64K | 2 | P2-64K-b4096 | 7.16 [7.06, 7.26] | - |
| 64K | ref | stock-64K | 9.36 [9.09, 9.63] | - |
| 128K | 1 | P2-128K-b4096 | 9.06 [8.30, 9.81] | too close to call at n = 2 |
| 128K | 2 | P6-128K-b4096 | 9.09 [8.88, 9.30] | too close to call at n = 2 |
| 128K | ref | stock-128K | 11.29 [10.89, 11.69] | - |

P6 is the `-cmoe --moe-cache-mib` expert-cache placement; P2 is a `--fit` placement. Stage 1
paging-flagged windows (more than 1,000 major faults) occurred only in repetition 1 of
long-running servers at 128K (14 of 38 windows) and 64K (1 of 38); all 15 attempt-2 windows on
fresh servers were clean (`reports/stage1/diagnostics.md`, `docs/decisions.md` WP12).

### Stage 2 tuned configurations (provisional winners)

<!-- sources: docs/stage2-summary.md, docs/decisions.md -->

Tuned configuration per context, as measured on llama.cpp `57d04820`, 5 repetitions per cell.
All carry `--cache-ram 2048`, `-fa on`, `-np 1`, batch and ubatch 4096. Figures are from
`smallpc.analysis` over the named session (middle depth: 16,384 at 32K, 32,768 at 64K, 65,536
at 128K).

| context | placement | MTP draft | KV type | expert cache (MiB) | sanity | decided by |
|---|---|---|---|---|---|---|
| 32K | P6 (`-cmoe`) | off | 8-bit (default) | 11,520 | pass | final selection, `data/analysis/stage2/32K-final.md` (s2a-32K) |
| 64K | P6 | 1 | FP16 | 9,472 | pass | 2a2 then 2b (rule) |
| 128K | P6 | off | FP16 | 8,704 | pass | 2a2 then 2b (rule) |

| context | cell | T_turn_400 s [95% CI] | T_reread s | PP_fresh tok/s | TG tok/s | min free VRAM MiB | MTP accept. (Req B) |
|---|---|---|---|---|---|---|---|
| 32K | tuned s2a-P6-32K-b4096-mtp0 | 5.916 [5.608, 6.224] | 6.692 | 2,481.9 | 91.5 | 1,379 | - |
| 64K | tuned s2b-P6-64K-b4096-mtp1-kvf16 | 6.486 [6.128, 6.845] | 16.756 | 1,997.3 | 90.4 | 1,019 | 0.771 |
| 128K | tuned s2b-P6-128K-b4096-mtp0-kvf16 | 7.967 [7.669, 8.266] | 36.002 | 1,907.4 | 71.0 | 1,211 | - |

Stage 2 findings carried into the text (corrections from `docs/decisions.md` WP13, verified
against the Stage 2 sessions):

- **MTP helped about 2 to 5% per turn** (4.6% at 32K on draft length 2, an excluded
  configuration; 2.4% at 64K on draft length 1), **costs 9 to 16% of prefill speed and 0.75 to
  1.5 GiB of VRAM** <!-- derived: 768 MiB = 0.75 GiB (32K), 1,536 MiB = 1.5 GiB (128K); decisions.md WP13 corrections item 3 -->.
  MTP joins a tuned config only at 64K (draft length 1).
- **The later Stage 2 sessions had 1 flagged window of 80** (not 100): the one flagged window is
  `s2b-P6-64K-b4096-mtp1-kvf16` repetition 2. (2a, the first sessions at `--cache-ram 2048`, had
  15 of 75 windows flagged; "removed the paging" holds for 2a2 and later, not 2a.)
- **`--cache-ram 2048`** was chosen by the 2f rule and used in every later candidate cell and
  tuned config; stock keeps the default 8192.
- **Output sanity:** MTP at draft length 2 fails the 8-gram rule deterministically at 32K and
  64K; the rule stands, thresholds unchanged, and draft length 2 is excluded from all tuned
  configs. MTP off and draft lengths 1 and 3 pass.
- **32K KV type:** the 32K tuned config uses 8-bit KV as measured (the sweep default). FP16 vs
  8-bit at 32K was measured only on draft-length-2 cells, which the sanity check excluded, so
  the 32K KV type is the default, not a 2b result. FP16 won at 64K and 128K by the rule.
- **Plan deviations:** 2c (`--load-mode dio`) was not run and 2d (threads) was skipped (the
  default thread count is already 8). Both are recorded in `docs/decisions.md`.

## 5. Stage 3 — headline results (quiet machine)

<!-- sources: data/analysis/stage3/headline.md, reports/stage3/report.md -->

Stage 3 measured the six released config files `configs/server/{stock,tuned}-{32k,64k,128k}.toml`
(the tuned files are the Stage 2 winners; stock is §3.1 unchanged, including its default host
prompt cache), 5 repetitions per cell, one session per context with start and end canaries,
from a clean committed tree, on a quiet machine (gate G3 in full). Stock and tuned of a context
share a session, so their repetitions are paired. One `--rerun-flagged` pass per session.
Stage 3 took about 2.1 hours <!-- derived: (90 minutes of sessions + 38 minutes of re-runs) / 60; planning-chat correction, card T-005 shared rule 8 -->.

The headline rule (plan §5.4, verbatim from `data/analysis/stage3/headline.md`):

> The headline for a context is the clean-units comparison if both cells have at least 5 clean,
> paired units after the re-run pass. Otherwise the headline is the all-units comparison,
> labelled "includes paging-flagged stock windows", with the clean-units figures beside it, and
> S4(d) is recorded as a deviation for that context. If the two versions disagree in sign, or
> one interval excludes 1.0 and the other does not, the report says so in its first paragraph.

The clean-units and all-units versions agree in every context (sign, and whether each interval
excludes 1.0). `data/analysis/stage3/headline.md` is authoritative for the headline (decision
D1); the rendered `reports/stage3/report.md` is used here for the VRAM breakdown, expert-cache
hit rates and excluded diagnostics.

### 32K

<!-- sources: data/analysis/stage3/headline.md -->

Tuned cell eligibility (final mode): eligible; n_clean 5 of 5; minimum free VRAM 1,379 MiB;
sanity pass. Headline: **clean units** (5 clean, paired units).

| metric | tuned / stock, geometric mean [95% CI] (n=5) | reading |
|---|---|---|
| t_turn_400 | 0.705 [0.672, 0.739] | lower is faster |
| t_reread | 0.378 [0.375, 0.381] | lower is faster |
| pp_fresh at 8K | 2.686 [2.671, 2.700] | higher is faster |
| pp_fresh at 16K | 2.664 [2.644, 2.684] | higher is faster |
| pp_fresh at 24K | 2.621 [2.586, 2.657] | higher is faster |
| tg at 8K | 1.173 [1.101, 1.249] | higher is faster |
| tg at 16K | 1.142 [1.089, 1.197] | higher is faster |
| tg at 24K | 1.089 [0.996, 1.190] | higher is faster |
| ttft at 8K | 0.431 [0.423, 0.440] | lower is faster |
| ttft at 16K | 0.451 [0.428, 0.475] | lower is faster |
| ttft at 24K | 0.455 [0.448, 0.462] | lower is faster |

Cell figures (clean units): stock-32K T_turn_400 8.339 [8.299, 8.379] s, T_reread 17.505
[17.421, 17.589] s, peak VRAM 14,926 MiB; tuned-32K T_turn_400 5.882 [5.594, 6.170] s, T_reread
6.617 [6.551, 6.683] s, peak VRAM 14,932 MiB.

Per-depth figures (clean units; PP in tok/s, T_B / T_reread / TTFT in s, predicted_n in tokens):

**stock-32K** (n_clean 5, n_total 5; min free VRAM 1,385 MiB; peak 14,926 MiB; MTP acceptance -)

| depth | PP_fresh | PP_inc | TG | T_B | predicted_n | T_reread | TTFT |
|---|---|---|---|---|---|---|---|
| 8K | 955.5 [945.2, 965.7] | 906.0 [895.1, 917.0] | 83.87 [83.56, 84.17] | 8.069 [8.042, 8.096] | 400.0 [400.0, 400.0] | 8.574 [8.482, 8.667] | 3.313 [3.273, 3.353] |
| 16K | 941.0 [936.9, 945.0] | 880.3 [868.4, 892.2] | 81.06 [80.14, 81.99] | 8.331 [8.292, 8.370] | 400.0 [400.0, 400.0] | 17.412 [17.337, 17.487] | 3.411 [3.365, 3.457] |
| 24K | 926.4 [920.9, 931.9] | 860.5 [851.4, 869.6] | 78.35 [77.50, 79.19] | 8.580 [8.514, 8.645] | 400.0 [400.0, 400.0] | 26.529 [26.372, 26.686] | 3.490 [3.454, 3.527] |

**tuned-32K** (n_clean 5, n_total 5; min free VRAM 1,379 MiB; peak 14,932 MiB; MTP acceptance -)

| depth | PP_fresh | PP_inc | TG | T_B | predicted_n | T_reread | TTFT |
|---|---|---|---|---|---|---|---|
| 8K | 2566.1 [2543.1, 2589.1] | 2102.6 [2066.4, 2138.7] | 98.43 [92.43, 104.44] | 5.489 [5.230, 5.747] | 400.0 [400.0, 400.0] | 3.193 [3.164, 3.221] | 1.429 [1.404, 1.454] |
| 16K | 2506.8 [2486.4, 2527.1] | 1954.4 [1842.5, 2066.3] | 92.59 [88.31, 96.88] | 5.852 [5.638, 6.066] | 400.0 [400.0, 400.0] | 6.536 [6.483, 6.589] | 1.541 [1.447, 1.634] |
| 24K | 2428.3 [2393.8, 2462.9] | 1893.2 [1871.1, 1915.3] | 85.48 [77.94, 93.03] | 6.273 [5.806, 6.739] | 400.0 [400.0, 400.0] | 10.122 [9.976, 10.268] | 1.589 [1.570, 1.607] |

**Swap sensitivity (plan §5.5, decision D3).** Removed (swap growth above 64 MiB): stock-32K
stage3-32K:2 (231 MiB), tuned-32K stage3-32K:2 (115 MiB), tuned-32K stage3-32K:4 (145 MiB) —
3 of 5 pairs dropped. The 32K swap sensitivity is **not material**: the point estimates barely
move (t_turn_400 0.705 [0.672, 0.739] → 0.712 [0.629, 0.807]) and the wider intervals come from
dropping 3 of 5 pairs. The 32K **decode gain is small and not robust** to excluding swap-active
units: tg@24576 moves from 1.089 [0.996, 1.190] to 1.057 [0.859, 1.300], whose interval now
includes 1.0. The T_turn_400 conclusions are unchanged.

### 64K

<!-- sources: data/analysis/stage3/headline.md -->

Tuned cell eligibility (final mode): eligible; n_clean 5 of 5; minimum free VRAM 1,021 MiB;
sanity pass. Headline: **clean units** (5 clean, paired units).

| metric | tuned / stock, geometric mean [95% CI] (n=5) | reading |
|---|---|---|
| t_turn_400 | 0.690 [0.649, 0.734] | lower is faster |
| t_reread | 0.423 [0.419, 0.427] | lower is faster |
| pp_fresh at 16K | 2.488 [2.459, 2.516] | higher is faster |
| pp_fresh at 32K | 2.399 [2.366, 2.431] | higher is faster |
| pp_fresh at 48K | 2.304 [2.287, 2.322] | higher is faster |
| tg at 16K | 1.225 [1.143, 1.313] | higher is faster |
| tg at 32K | 1.239 [1.158, 1.325] | higher is faster |
| tg at 48K | 1.213 [1.095, 1.343] | higher is faster |
| ttft at 16K | 0.479 [0.476, 0.482] | lower is faster |
| ttft at 32K | 0.506 [0.502, 0.510] | lower is faster |
| ttft at 48K | 0.551 [0.515, 0.590] | lower is faster |

Cell figures (clean units): stock-64K T_turn_400 9.288 [9.238, 9.338] s, T_reread 39.073
[38.896, 39.251] s, peak VRAM 14,956 MiB; tuned-64K T_turn_400 6.413 [6.003, 6.824] s, T_reread
16.534 [16.403, 16.664] s, peak VRAM 15,290 MiB, MTP acceptance 0.771 pooled over Request B
(per unit 0.771 [0.745, 0.798]).

Per-depth figures (clean units):

**stock-64K** (n_clean 5, n_total 5; min free VRAM 1,355 MiB; peak 14,956 MiB; MTP acceptance -)

| depth | PP_fresh | PP_inc | TG | T_B | predicted_n | T_reread | TTFT |
|---|---|---|---|---|---|---|---|
| 16K | 864.8 [856.4, 873.1] | 814.9 [804.2, 825.7] | 78.67 [78.49, 78.85] | 8.753 [8.700, 8.807] | 400.0 [400.0, 400.0] | 18.947 [18.763, 19.131] | 3.685 [3.636, 3.733] |
| 32K | 844.2 [840.3, 848.0] | 776.7 [765.4, 788.0] | 73.88 [73.79, 73.97] | 9.263 [9.208, 9.319] | 400.0 [400.0, 400.0] | 38.818 [38.642, 38.994] | 3.868 [3.812, 3.923] |
| 48K | 826.7 [823.9, 829.5] | 737.4 [728.4, 746.3] | 69.53 [69.41, 69.65] | 9.312 [7.945, 10.679] | 365.6 [270.1, 461.1] | 59.455 [59.253, 59.657] | 4.075 [4.026, 4.125] |

**tuned-64K** (n_clean 5, n_total 5; min free VRAM 1,021 MiB; peak 15,290 MiB; MTP acceptance 0.771)

| depth | PP_fresh | PP_inc | TG | T_B | predicted_n | T_reread | TTFT |
|---|---|---|---|---|---|---|---|
| 16K | 2151.3 [2142.8, 2159.9] | 1703.8 [1692.2, 1715.5] | 96.51 [89.82, 103.21] | 5.905 [5.608, 6.203] | 400.0 [400.0, 400.0] | 7.616 [7.585, 7.646] | 1.764 [1.752, 1.776] |
| 32K | 2024.9 [2001.7, 2048.0] | 1537.5 [1526.0, 1549.0] | 91.64 [85.48, 97.81] | 6.316 [6.005, 6.626] | 400.0 [400.0, 400.0] | 16.184 [15.996, 16.372] | 1.956 [1.941, 1.971] |
| 48K | 1905.1 [1891.7, 1918.5] | 1341.5 [1254.7, 1428.3] | 84.57 [76.14, 92.99] | 6.985 [6.342, 7.628] | 400.0 [400.0, 400.0] | 25.801 [25.618, 25.984] | 2.248 [2.092, 2.404] |

**Swap sensitivity (plan §5.5).** No unit of these cells shows swap growth above 64 MiB: nothing to
remove; the comparison is unchanged.

### 128K

<!-- sources: data/analysis/stage3/headline.md -->

Tuned cell eligibility (final mode): eligible; n_clean 5 of 5; minimum free VRAM 1,211 MiB;
sanity pass. Headline: **all units, labelled "includes paging-flagged stock windows"** (D1).
S4(d) deviation for this context: the headline rests on 1 stock unit with an unresolved flag
(stage3-128K:3, paging) because stock-128K has 4 clean and tuned-128K 5 clean units (4 paired;
at least 5 needed for the clean-units headline).

Headline (all units, n=5):

| metric | tuned / stock, geometric mean [95% CI] (n=5) | reading |
|---|---|---|
| t_turn_400 | 0.706 [0.679, 0.735] | lower is faster |
| t_reread | 0.382 [0.381, 0.384] | lower is faster |
| pp_fresh at 32K | 2.926 [2.904, 2.949] | higher is faster |
| pp_fresh at 64K | 2.701 [2.689, 2.712] | higher is faster |
| pp_fresh at 96K | 2.487 [2.475, 2.500] | higher is faster |
| tg at 32K | 1.143 [1.100, 1.189] | higher is faster |
| tg at 64K | 1.136 [1.074, 1.202] | higher is faster |
| tg at 96K | 1.125 [1.046, 1.209] | higher is faster |
| ttft at 32K | 0.418 [0.412, 0.424] | lower is faster |
| ttft at 64K | 0.473 [0.466, 0.480] | lower is faster |
| ttft at 96K | 0.521 [0.516, 0.526] | lower is faster |

Clean-units figures beside it (n=4):

| metric | tuned / stock, geometric mean [95% CI] (n=4) | reading |
|---|---|---|
| t_turn_400 | 0.711 [0.673, 0.750] | lower is faster |
| t_reread | 0.382 [0.380, 0.384] | lower is faster |
| pp_fresh at 32K | 2.932 [2.909, 2.955] | higher is faster |
| pp_fresh at 64K | 2.703 [2.690, 2.717] | higher is faster |
| pp_fresh at 96K | 2.487 [2.469, 2.506] | higher is faster |
| tg at 32K | 1.141 [1.078, 1.208] | higher is faster |
| tg at 64K | 1.123 [1.049, 1.202] | higher is faster |
| tg at 96K | 1.107 [1.017, 1.204] | higher is faster |
| ttft at 32K | 0.416 [0.411, 0.422] | lower is faster |
| ttft at 64K | 0.472 [0.464, 0.480] | lower is faster |
| ttft at 96K | 0.521 [0.514, 0.528] | lower is faster |

The two versions agree in sign and in whether each interval excludes 1.0.

Cell figures: stock-128K clean (n_clean 4, n_total 5) T_turn_400 11.192 [11.129, 11.255] s,
T_reread 94.250 [93.782, 94.717] s, peak VRAM 14,942 MiB; stock-128K all units (n=5) T_turn_400
11.191 [11.149, 11.234] s, T_reread 94.174 [93.796, 94.553] s; tuned-128K (n_clean 5, n_total 5)
T_turn_400 7.910 [7.609, 8.210] s, T_reread 35.977 [35.961, 35.994] s, peak VRAM 15,100 MiB.

Per-depth figures:

**stock-128K, all units** (headline basis; n_clean 5, n_total 5; min free VRAM 1,369 MiB; peak 14,942 MiB; MTP acceptance -)

| depth | PP_fresh | PP_inc | TG | T_B | predicted_n | T_reread | TTFT |
|---|---|---|---|---|---|---|---|
| 32K | 731.7 [726.6, 736.8] | 678.9 [667.6, 690.1] | 70.02 [69.82, 70.21] | 10.118 [10.056, 10.181] | 400.0 [400.0, 400.0] | 44.785 [44.471, 45.098] | 4.424 [4.352, 4.497] |
| 64K | 705.0 [701.6, 708.3] | 624.1 [615.3, 633.0] | 62.65 [62.53, 62.76] | 10.805 [9.797, 11.813] | 376.8 [312.4, 441.2] | 92.964 [92.524, 93.405] | 4.816 [4.748, 4.884] |
| 96K | 679.0 [675.9, 682.1] | 580.9 [574.4, 587.4] | 56.47 [55.37, 57.56] | 12.232 [12.121, 12.343] | 400.0 [400.0, 400.0] | 144.775 [144.119, 145.430] | 5.178 [5.121, 5.234] |

Units with an unresolved flag (counted in this view): stage3-128K:3 attempt 2 — paging, swap
growth 4200 MiB.

**stock-128K, clean units** (n_clean 4, n_total 5; min free VRAM 1,369 MiB; peak 14,942 MiB; MTP acceptance -)

| depth | PP_fresh | PP_inc | TG | T_B | predicted_n | T_reread | TTFT |
|---|---|---|---|---|---|---|---|
| 32K | 730.4 [725.1, 735.6] | 675.5 [666.1, 685.0] | 70.08 [69.98, 70.18] | 10.135 [10.070, 10.199] | 400.0 [400.0, 400.0] | 44.867 [44.547, 45.186] | 4.446 [4.384, 4.507] |
| 64K | 704.1 [700.7, 707.5] | 621.6 [613.9, 629.2] | 62.64 [62.47, 62.81] | 10.732 [9.271, 12.194] | 371.0 [278.7, 463.3] | 93.080 [92.634, 93.526] | 4.836 [4.776, 4.895] |
| 96K | 678.9 [674.4, 683.4] | 579.2 [572.5, 586.0] | 56.86 [56.69, 57.03] | 12.197 [12.120, 12.273] | 400.0 [400.0, 400.0] | 144.802 [143.839, 145.766] | 5.191 [5.131, 5.252] |

**tuned-128K** (clean units = all units; n_clean 5, n_total 5; min free VRAM 1,211 MiB; peak 15,100 MiB; MTP acceptance -)

| depth | PP_fresh | PP_inc | TG | T_B | predicted_n | T_reread | TTFT |
|---|---|---|---|---|---|---|---|
| 32K | 2141.1 [2138.7, 2143.6] | 1626.5 [1620.9, 1632.2] | 80.09 [77.04, 83.14] | 6.830 [6.633, 7.027] | 400.0 [400.0, 400.0] | 15.304 [15.286, 15.322] | 1.849 [1.843, 1.855] |
| 64K | 1903.8 [1902.2, 1905.5] | 1321.8 [1313.4, 1330.2] | 71.24 [67.31, 75.17] | 7.879 [7.548, 8.211] | 400.0 [400.0, 400.0] | 34.423 [34.393, 34.453] | 2.278 [2.263, 2.292] |
| 96K | 1688.9 [1687.9, 1690.0] | 1116.2 [1109.1, 1123.3] | 63.57 [59.75, 67.40] | 8.977 [8.569, 9.385] | 400.0 [400.0, 400.0] | 58.205 [58.169, 58.241] | 2.699 [2.682, 2.717] |

**Swap sensitivity (plan §5.5).** No sign change and no interval moved by more than its half-width.
Removed (swap growth above 64 MiB): stock-128K stage3-128K:3 (4200 MiB) — already excluded by a
flag, so it does not affect the clean-units view.

### VRAM breakdown

<!-- sources: reports/stage3/report.md -->

MiB, from each cell summary's parsed placement (buffers on the GPU) and its windows. "expert
cache" is the `--moe-cache-mib` size the server reports; "other" is peak used minus the listed
parts (CUDA context, graphs, allocator slack). Stock holds the whole model on the GPU (no
expert cache); tuned keeps only the dense backbone on the GPU and caches experts in host RAM.

| context | cell | model | KV | recurrent | compute | expert cache | other | peak used | min free | layers on CPU |
|---|---|---|---|---|---|---|---|---|---|---|
| 32K | stock-32K | 13,468 | 640 (f16) | 251 | 299 | 0 | 268 | 14,926 | 1,385 | 15 |
| 32K | tuned-32K | 1,303 | 340 (q8_0) | 63 | 1,348 | 11,520 | 359 | 14,932 | 1,379 | - |
| 64K | stock-64K | 12,825 | 1,280 (f16) | 251 | 331 | 0 | 269 | 14,956 | 1,355 | 16 |
| 64K | tuned-64K | 1,326 | 1,408 (f16) | 126 | 2,436 | 9,471 | 523 | 15,290 | 1,021 | - |
| 128K | stock-128K | 11,463 | 2,560 (f16) | 251 | 396 | 0 | 272 | 14,942 | 1,369 | 19 |
| 128K | tuned-128K | 1,303 | 2,560 (f16) | 63 | 2,116 | 8,701 | 358 | 15,100 | 1,211 | - |

### Expert-cache hit rates

<!-- sources: reports/stage3/report.md -->

| cell | cache MiB | decode-batch hit rate | hits | misses | large-batch experts copied | uploaded MiB |
|---|---|---|---|---|---|---|
| tuned-32K | 11,520 | 97.0 % | 2,585,352 | 79,316 | 1,484,937 | 146,491 |
| tuned-64K | 9,471 | 94.3 % | 4,257,457 | 257,252 | 3,894,861 | 473,795 |
| tuned-128K | 8,701 | 93.9 % | 2,501,814 | 162,842 | 3,569,853 | 301,304 |

**Caveats (decision D9 and plan §5.6).** The server's statistics give hit rates for **decode-sized
batches only** (`ubatch <= 8`); prefill-sized batches report only how many experts were copied
from the cache — there is no prefill hit rate. The counts cover everything the server served,
**including warm-up and the attempt-1 units of re-run windows**, not only clean repetitions
(D9). The workloads are popular public code (poetry, axum) the model may have seen in training,
so content-dependent rates need that caveat too.

### Paging picture

<!-- sources: reports/stage3/report.md, docs/decisions.md, data/analysis/stage3/headline.md -->

Stock keeps `--cache-ram 8192`, so its later repetitions may page at 64K and 128K; that is how
stock behaves on this machine, so it is reported, not hidden. Contrary to plan §5.4's
expectation, at 64K the **tuned** cell was paging-flagged in 4 of 5 attempt-1 windows (up to
47,576 major faults, 586 MiB swap growth) and the stock cell in none; at 32K and 128K stock
paged (1 and 2 windows) and tuned did not (`docs/decisions.md` WP13 part 2).

- **Tuned-64K paging (decision D2).** This is the known file-page faulting of the MTP cell seen
  in Stage 2a; it is not investigated. All four flagged tuned units re-ran clean in attempt 2
  (0 faults). Gate criterion f passed: the gate tool reported 36.4% of tuned and canary windows
  (4 of 11, re-run canary cells excluded), limit 40%. Per decision E-001 (A7), the denominator
  is 17 attempt-1 windows (tuned-64K 5, four canary cells × 3; stock excluded): 4 flagged =
  23.5%; true pass under both denominators.
- **Stock-128K (decision D1, S4(d) deviation).** Unit stage3-128K:3 is still paging-flagged in
  attempt 2 (22,810 major faults, 4,200 MiB swap growth; attempt 1 had 2,004 faults). The 128K
  headline therefore uses all units and says so (the 128K section above).

Excluded diagnostic results (not in any headline number; attempt 1 of a re-run unit is replaced
by attempt 2):

| cell | session | repetition | attempt | flags | T_turn_400 (s) | why |
|---|---|---|---|---|---|---|
| stock-128K | stage3-128K | 1 | 1 | paging | 11.19 | attempt 1 of a unit re-run as attempt 2 |
| stock-128K | stage3-128K | 3 | 1 | paging | 11.13 | attempt 1 of a unit re-run as attempt 2 |
| stock-128K | stage3-128K | 3 | 2 | paging | 11.19 | flagged unit |
| stock-32K | stage3-32K | 3 | 1 | paging | 8.19 | attempt 1 of a unit re-run as attempt 2 |
| tuned-64K | stage3-64K | 1 | 1 | paging | 7.23 | attempt 1 of a unit re-run as attempt 2 |
| tuned-64K | stage3-64K | 2 | 1 | paging | 6.42 | attempt 1 of a unit re-run as attempt 2 |
| tuned-64K | stage3-64K | 3 | 1 | paging | 6.37 | attempt 1 of a unit re-run as attempt 2 |
| tuned-64K | stage3-64K | 4 | 1 | paging | 6.17 | attempt 1 of a unit re-run as attempt 2 |

### Output sanity check

<!-- sources: data/sanity/stage3-tuned.json -->

The sanity check was run again on the three tuned config files (plan §5.4, §5.6). The output
file is **`data/sanity/stage3-tuned.json`** (decision D7: the runbook said `stage3-all.json`;
docs cite the actual name). All three tuned cells **pass**, with no failed prompts; the
reference cells (P1-32K-b2048, P1-64K-b2048, P1-128K-b2048) also pass.

| cell | resolved from | result | failed prompts |
|---|---|---|---|
| tuned-32k | configs/server/tuned-32k.toml | pass | none |
| tuned-64k | configs/server/tuned-64k.toml | pass | none |
| tuned-128k | configs/server/tuned-128k.toml | pass | none |

No tuned cell was ineligible and no sanity failure occurred in Stage 3.

## 6. Flags and deviations

<!-- sources: docs/decisions.md, data/analysis/stage3/headline.md -->

Recorded deviations and flags (from `docs/decisions.md`), carried into this report:

- **D1 / S4(d), 128K headline on all units.** The 128K headline includes one paging-flagged
  stock window (stage3-128K:3), labelled "includes paging-flagged stock windows", with the
  clean-units figures beside it. The declared §5.4 rule, not a judgement call.
- **D2, tuned-64K paging.** Known file-page faulting of the MTP cell (Stage 2a); not
  investigated. All four flagged units re-ran clean; gate passed under both denominators
  (36.4% tool / 23.5% per A7).
- **D3, 32K swap sensitivity not material.** Point estimates barely move; wider intervals come
  from dropping 3 of 5 pairs; the 32K decode gain is small and not robust to excluding
  swap-active units; T_turn_400 conclusions unchanged (the 32K section).
- **D7, sanity file name.** `data/sanity/stage3-tuned.json` (not the runbook's `stage3-all.json`).
- **D9, hit-rate caveat.** Hit rates include warm-up and the attempt-1 units of re-run windows;
  decode-batch only (the Expert-cache hit rates section).
- **Stages 1 and 2 apps-open.** Gate G3 not met for the selection stages; a recorded deviation.
  Stage 3 ran quiet (G3 in full).
- **Stage 2 plan deviations.** 2c (`--load-mode dio`) not run; 2d (threads) skipped (default 8).
  MTP draft length 2 excluded by the sanity rule (8-gram failure), thresholds unchanged.
- **32K tuned KV type.** 8-bit as measured (the default), not a 2b result (Stage 2 section).
- **D4 / D5 (tooling, not data).** Five test literals edited to "1.8" (commit 422eada) accepted;
  the flakiness of `tests/test_sweep_probe.py` is fixed before release (T-009). Neither changes
  a measured number.
- **Corrections carried into the text** (card T-005 shared rule 8; `docs/decisions.md` WP13):
  1 flagged window of 80 (not 100) in the later Stage 2 sessions; MTP helped about 2 to 5% per
  turn (not 3 to 5%), costs 9 to 16% of prefill speed and 0.75 to 1.5 GiB of VRAM; Stage 3 took
  about 2.1 hours (90 minutes of sessions plus 38 minutes of re-runs) <!-- derived: (90+38)/60; planning-chat correction, card T-005 shared rule 8 -->.

## 7. Step 0 success criteria (S1–S5)

<!-- sources: docs/plans/step-0-baseline.md -->

Status against the plan's §2 success criteria. S2 (reproducibility) awaits Stage 4 and S5
(release) awaits the release tasks; both are marked `<!-- TODO-T010 -->` for T-010 to finalise.
Final acceptance is assessed in the completion report (T-014).

| criterion | status | evidence / note |
|---|---|---|
| S1 Coverage | Stages 1–3 measured | Stage 1 screening (57 cells), Stage 2 feature experiments, Stage 3 final (6 cells, 5 reps); raw per-request JSONL committed under `data/raw/`. Stage 4 pending. |
| S2 Reproducibility | <!-- TODO-T010 --> | Awaits Stage 4 (T-007/T-008): stock-64K and tuned-64K re-measured on a different day, plus the README clean-shell walkthrough (T-012). |
| S3 Decisions | met | Stock and tuned config for each of 32K/64K/128K (`configs/server/{stock,tuned}-{32k,64k,128k}.toml`); tuned chosen by the §3.3 rule (Stage 2 section); each launches via `scripts/launch-server.sh`. |
| S4 Health checks | evidence recorded; deviations noted | MTP head tensor screen and acceptance (0.771 at 64K, draft 1); endpoints (`data/health/endpoints-2026-11-08.json`); sanity pass (Output sanity check section); env snapshot + warm-up every run. Deviations: 128K S4(d) headline on a flagged stock window (D1); Stages 1–2 apps-open. Full sub-item assessment in T-014. |
| S5 Release | <!-- TODO-T010 --> | Awaits the release checklist (§9) and tag v0.1.0 (T-013/T-015/T-016). |

## 8. Sources and verification

Every table above carries a `sources:` comment naming the file(s) its numbers come from;
derived numbers carry a `derived:` comment. The marker syntax is:

```text
<!-- sources: path/to/file.md, path/to/data.json -->
<!-- derived: how the number was computed -->
```

Run the checker with:

```text
uv run python tools/check_doc_numbers.py reports/baseline-report.md
```

Primary sources: `data/analysis/stage3/headline.md` (Stage 3 headline, authoritative per D1),
`reports/stage3/report.md` (VRAM, hit rates, excluded diagnostics), `data/sanity/stage3-tuned.json`
(sanity), `docs/stage2-summary.md` and `reports/stage1/select-screening.md` (selection data),
`docs/decisions.md` (deviations and corrections), `docs/plans/step-0-baseline.md` (method),
`data/env/build-info.json`, `configs/model.toml`, `configs/harness.toml`, `configs/machine.toml`
(provenance).
