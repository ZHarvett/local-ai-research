# What a 16 GB GPU actually does with a 35B MoE model

<!-- sources: reports/baseline-report.md, data/analysis/stage3/headline.md, docs/decisions.md, docs/plans/step-0-baseline.md, data/analysis/stage4/s2-summary.md, reports/stage4-run2/caveats.md, docs/recon/pcie-link.md -->

> **FINAL (T-010).** A narrative companion to `reports/baseline-report.md`, which carries the
> full tables, provenance and deviations. Stage 4 (reproducibility on a different day) passes
> 6 of 6 rows on run 2; the clean-shell walkthrough (T-012) and the scrub and release checks
> (T-013) pass; the v0.1.0 tag and publish are pending (T-015, T-016). Every number here is copied
> from a named repo file (the `sources:` line above) or marked `derived:`;
> `tools/check_doc_numbers.py` verifies this.

## The problem

Ornith-1.5-35B-A3B is a 35B mixture-of-experts coding model. Its Q4_K_M GGUF is
21,713,463,040 bytes — about 20 GiB, larger than the 16 GB of VRAM on an RTX 5060 Ti. Something
has to live outside the GPU, and the question is what that costs: how fast are agent-style
turns at 32K, 64K and 128K context, and how much does the server configuration matter?

The machine is a desktop: Ryzen 7 9700X (8 cores / 16 threads), 32 GB RAM, a 256 GB NVMe SSD,
monitors on the motherboard iGPU so the GPU is compute-only. Step 0 has no hard speed targets
(plan §2); it is a measured baseline that every later step is compared against.

## The approach

Mainline llama.cpp, pinned build (tag `b12208`, commit `57d04820`), CUDA. Two configurations
per context:

- **Stock** — what a typical user would run (plan §3.1): llama.cpp's automatic placement
  (`--fit`), default batches (`-b 2048 -ub 512`), FP16 KV, flash attention `auto`, default slot
  count, the default host prompt cache (`--cache-ram 8192`), no speculative decoding.
- **Tuned** — chosen by a selection rule declared before any speed measurement (plan §3.3),
  through staged sweeps: Stage 1 screening (57 cells, n = 2), Stage 2 feature experiments
  (placement, batch, MTP, KV type, host cache size), then Stage 3, the headline measurement.

The workload is a standardised turn: a 3,000-token append to a prefix of depth d, with
T_turn_400 the estimated time of a 400-token turn. llama-server's response timings are
authoritative. Stage 3 ran the six released config files on a quiet machine, 5 paired
repetitions per cell, with canaries, telemetry and an environment snapshot per run; it took
about 2.1 hours <!-- derived: (90 minutes of sessions + 38 minutes of re-runs) / 60; baseline-report.md §5 -->.
Windows with more than 1,000 major page faults are flagged, re-run once, and then resolved,
excluded, or explicitly labelled. Results carry 95% confidence intervals.

## The results

Tuned is faster than stock at every context. The paired tuned/stock ratio of T_turn_400
(lower is faster):

| context | headline basis | T_turn_400 tuned/stock [95% CI] | stock → tuned (s) |
|---|---|---|---|
| 32K | clean units (n=5) | 0.705 [0.672, 0.739] | 8.339 → 5.882 |
| 64K | clean units (n=5) | 0.690 [0.649, 0.734] | 9.288 → 6.413 |
| 128K | all units, includes paging-flagged stock windows (n=5) | 0.706 [0.679, 0.735] | 11.191 → 7.910 |

That is about 30% less time per turn <!-- derived: 1 - (0.690 to 0.706), the headline ratios above -->.
Fresh prefill is roughly 2.3–2.9× faster and decode roughly 1.1–1.2× faster at the measured
depths. Re-reading the prefix takes 0.378 / 0.423 / 0.382 of stock's time at 32K / 64K / 128K.

The 128K headline uses all units and says so (decision D1, the declared §5.4 rule): one stock
window stayed paging-flagged after its re-run, leaving only 4 clean paired units. The
clean-units figure stands beside it — 0.711 [0.673, 0.750] (n=4) — and the two versions agree
in sign and in whether each interval excludes 1.0. This is a recorded S4(d) deviation.

**The numbers reproduce.** Stage 4 re-measured stock-64K and tuned-64K on a different day
(2026-11-14): all 6 S2 rows pass — each re-measured mean inside its Stage 3 95% CI or within
±5%, whichever is wider (stock-64K T_turn_400 9.100 s against 9.288 [9.238, 9.338]; tuned-64K
6.296 s against 6.413 [6.003, 6.824]). The first attempt never counted: its PCIe link ran at
Gen3 x8 for the whole session, so run 1 is superseded and kept as an excluded diagnostic
(R5). The link was restored and verified at Gen4 x8 under load before run 2, whose measured
cell windows all read "4, 8" (R7). Run 2 also ran on a changed kernel and driver
(7.3.4-1-cachyos / 620.70.06 vs Stage 3's 7.3.1-1-cachyos / 615.78.08): the comparison carries
that confound, and the data stands (E-009).

**What the tuned configs change.** All experts move to host RAM (`-cmoe`), and the freed VRAM
becomes a probed max-fit expert cache: 11,520 / 9,472 / 8,704 MiB at 32K / 64K / 128K. Batch
and ubatch go to 4096, one slot, flash attention `on`, `--cache-ram 2048`. KV is 8-bit at 32K
(the sweep default) and FP16 at 64K and 128K. MTP speculative decoding is on at 64K only
(draft length 1, acceptance 0.771). Both configurations sit near the VRAM ceiling: peaks of
14,926 to 15,290 MiB, with tuned-64K leaving 1,021 MiB free at its lowest.

The expert cache does its job: decode-batch hit rates are 97.0% / 94.3% / 93.9%. Caveats
(decision D9): the counts cover everything the server served, including warm-up and the
attempt-1 units of re-run windows; they are decode-sized batches only (there is no prefill
hit rate); and the workloads are popular public code the model may have seen in training.

## What didn't work

**MTP draft length 2.** It fails the output sanity check deterministically at 32K and 64K:
a repeated phrase, maximum 8-gram repeat 8 against the reference's 2. The rule stands,
thresholds unchanged, so draft length 2 is excluded from every tuned config. Draft length 1
was recorded as bit-identical to MTP off in the plan's greedy checks (the committed sanity files
hold pass and fail only); draft length 3 passes. MTP overall helped only about 2 to 5% per
turn (4.6% at 32K on the excluded draft-length-2 config, 2.4% at 64K on draft length 1), and
costs 9 to 16% of prefill speed and 0.75 to 1.5 GiB of VRAM — so it joins a tuned config only
at 64K. At 128K no MTP cell had the required VRAM margin.

**`--fit` against the expert cache (P6).** Stock's automatic placement keeps most weights in
VRAM and offloads 15 / 16 / 19 expert layers to the CPU at 32K / 64K / 128K. P6 — all experts
host-side, a large VRAM expert cache — beat `--fit` in every context. In Stage 1 screening,
P6 with batch 4096 ran 6.14 s against stock's 8.45 s at 32K and 7.00 s against 9.36 s at 64K;
at 128K the fit placement P2 led 9.06 s to 9.09 s, too close to call at n = 2, and the final
selection went to P6. Larger batches alone more than double prefill speed over the default
(plan §13). One subtlety: `--fit`'s 1,024 MiB safety margin caps the probed expert cache
about 512 to 768 MiB below what a pure 512 MiB floor would allow (`docs/decisions.md`, WP11).

**The host prompt cache.** With the default `--cache-ram 8192`, a long-running server's host
prompt cache plus the 20 GiB memory-mapped model pushed this 32 GB machine into paging:
Stage 1 flagged 14 of 38 windows at 128K and 1 of 38 at 64K, all in repetition 1; all 15
attempt-2 windows on fresh servers were clean. Stage 2f tested smaller caches and the
pre-declared rule chose 2048: at 8192, 2 of 5 windows (128K) and 3 of 5 (64K) were flagged,
up to 159,451 faults in one window; at 2048, none. The later Stage 2 sessions had 1 flagged
window of 80. Paging did not vanish everywhere: in Stage 3 the tuned-64K cell (MTP) was
flagged in 4 of 5 attempt-1 windows — the known file-page faulting seen in Stage 2a — and all
four re-ran clean; stock-128K repetition 3 stayed flagged (22,810 faults, 4,200 MiB swap
growth), which is why the 128K headline is labelled. Stock keeps the default cache: that is
how stock behaves on this machine, reported, not hidden.

**Why 2c was skipped.** The planned remedy for paging was `--load-mode dio`: it reads the
model into pinned host memory (an 18.9 GiB `CUDA_Host` buffer) that the kernel cannot evict.
But `--cache-ram 2048` had already solved the paging problem, and dio would pin 18.9 GiB of
unswappable memory on a 32 GB machine with the desktop open. No problem was left for it to
solve, so 2c was not run — a recorded plan deviation. 2d (thread count) was skipped because
the default is already 8 in all 82 Stage 1 server logs.

## Limitations

One machine, one GPU, one model and quantisation, one pinned llama.cpp build. The turn is a
standardised synthetic workload (3,000 + 400 tokens), not a real agent task; Step 1 measures
real turns. Stages 1 and 2 ran with desktop apps open (a recorded deviation); Stages 3 and 4
were quiet. The 128K headline includes a paging-flagged stock window (labelled above). The 32K
decode gain is small and not robust to excluding swap-active units: tg at 24K moves from
1.089 [0.996, 1.190] to 1.057 [0.859, 1.300] when 3 of 5 pairs are dropped; the T_turn_400
conclusion is unchanged (0.712 [0.629, 0.807]). The 32K tuned KV type is the 8-bit default,
not a measured FP16 comparison. Expert-cache hit rates carry the caveats above. Five
repetitions per cell support the turn-time claim, not fine decode differences. Stage 4's
re-measurement passes (6 of 6 rows) but carries a kernel/driver confound and one superseded
run (above); the clean-shell walkthrough (T-012) and the release checks (T-013) pass; the tag
and publish are pending (T-015, T-016).

## Sources

Full tables, provenance hashes, flags and deviations: `reports/baseline-report.md`. Headline
numbers: `data/analysis/stage3/headline.md` (authoritative per decision D1). Stage 4 S2:
`data/analysis/stage4/s2-summary.md`, with the run-2 caveats in `reports/stage4-run2/caveats.md`
and the link evidence in `docs/recon/pcie-link.md`. Decisions and corrections:
`docs/decisions.md`. Method: `docs/plans/step-0-baseline.md` (§3, §5). Verify every decimal
number with `uv run python tools/check_doc_numbers.py reports/writeup.md`.