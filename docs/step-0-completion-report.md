# Step 0 completion report — Local AI on a Small PC

<!-- sources: reports/baseline-report.md, reports/writeup.md, data/analysis/stage3/headline.md, data/analysis/stage4/s2-summary.md, docs/decisions.md, docs/plans/step-0-baseline.md, docs/progress-log.md, README.md, CHANGELOG.md, configs/harness.toml, configs/model.toml, data/env/build-info.json, data/health/endpoints-2026-11-08.json, docs/recon/scrub-report.md -->

> **For the executive (planning) chat.** Step 0 (baseline setup) is complete: criteria S1–S5
> hold with recorded deviations; tag v0.1.0 and the public release were published 2026-11-16
> (T-015/T-016). Full tables, provenance hashes and per-depth figures: `reports/baseline-report.md`;
> narrative: `reports/writeup.md`. Every decimal number here is copied from a named repo file
> (the `sources:` line) or marked `derived:`; `tools/check_doc_numbers.py` verifies this.
> Date: 2026-11-15; §7 statuses updated 2026-11-16 by T-016. Plan: `docs/plans/step-0-baseline.md` v1.9.

## 1. What was built

A measured, reproducible stock-vs-tuned baseline for Ornith-1.5-35B-A3B (Q4_K_M GGUF, MoE,
21,713,463,040 bytes — about 20 GiB, larger than the 16 GB VRAM) on a 16 GB RTX 5060 Ti
(Ryzen 7 9700X, 32 GB RAM, NVMe), mainline llama.cpp `b12208` (commit `57d04820`, built
2026-11-08), at 32K / 64K / 128K context:

- **Six released server configs** (`configs/server/{stock,tuned}-{32k,64k,128k}.toml`) and
  `scripts/launch-server.sh` / `stop-server.sh` (TOML-rendered argv, GPU lock, `/health` wait).
- **Sweep and analysis tooling** (`smallpc`): parameterised sweep runner (TOML specs), canaries,
  telemetry, flag detectors, environment snapshots, max-fit probing, statistics (wider of
  bootstrap and t intervals), selection, output sanity, report renderer with SVG figures, scrub,
  and the doc number checker. Python via uv, Bash for launch/long jobs; no extra packaging.
- **Data**: append-only raw per-request JSONL for Stages 1–4 under `data/raw/`, microbenchmarks
  (PCIe, STREAM, NVMe), health and sanity results; Stage 4 run 1 kept as a superseded diagnostic.
- **Reports**: baseline report with 95% CIs, rendered stage reports, the write-up, README quick
  start and rerun guide, `docs/methodology.md`, CHANGELOG with a v0.1.0 entry.
- **Harnesses**: OpenCode `opencode-ai` 1.19.5 (control) and dsh `@deepseek-ai/dsh` 0.2.1-rc.5
  (research), pinned by the 7-day rule with a full lockfile age check (643 name@version pairs).
- **Workflow kit pilot**: task-based plan execution (`scripts/wf.sh`), lanes, reviews, escalations,
  unattended loop — the process this report closes out.

## 2. Results (headline)

Tuned is faster than stock at every context. Paired tuned/stock ratio of the estimated 400-token
turn time T_turn_400 (lower is faster), Stage 3, quiet machine, 5 paired repetitions per cell:

| context | headline basis | T_turn_400 tuned/stock [95% CI] | stock → tuned (s) |
|---|---|---|---|
| 32K | clean units (n=5) | 0.705 [0.672, 0.739] | 8.339 → 5.882 |
| 64K | clean units (n=5) | 0.690 [0.649, 0.734] | 9.288 → 6.413 |
| 128K | all units, includes paging-flagged stock windows (n=5) | 0.706 [0.679, 0.735] | 11.191 → 7.910 |

About 30% less time per turn <!-- derived: 1 - (0.690 to 0.706), the headline ratios above -->.
Fresh prefill roughly 2.3–2.9× faster, decode roughly 1.1–1.2× faster at the measured depths;
re-reading the prefix takes 0.378 / 0.423 / 0.382 of stock's time at 32K / 64K / 128K.

**The numbers reproduce (S2).** Stage 4 run 2 (2026-11-14, different day) re-measured stock-64K
and tuned-64K: **PASS, 6 of 6 rows**, every row on clean units — each mean inside its Stage 3
95% CI or within ±5%, whichever is wider (e.g. stock-64K T_turn_400 9.100 s vs 9.288
[9.238, 9.338]; tuned-64K 6.296 s vs 6.413 [6.003, 6.824]). Run 1 is superseded (R5: its PCIe
link ran at Gen3 x8 for the whole session) and kept as an excluded diagnostic. Run 2 carries a
kernel/driver confound (E-009). The clean-shell half of S2 passed too: T-012 launched all six
configs with only the README commands — 6/6 PASS, and all 45 under-load link samples read "4, 8".

**What the tuned configs change.** All experts to host RAM (`-cmoe`) with a probed max-fit VRAM
expert cache (11,520 / 9,472 / 8,704 MiB), batch/ubatch 4096, one slot, flash attention on,
`--cache-ram 2048`; KV 8-bit at 32K (the sweep default), FP16 at 64K/128K; MTP draft length 1 at
64K only (acceptance 0.771). Decode-batch expert-cache hit rates 97.0% / 94.3% / 93.9% (caveats
in §4, D9). Both configurations sit near the VRAM ceiling; tuned-64K leaves 1,021 MiB free at its
lowest. Stage 3 took about 2.1 hours; Stage 4 run 2 took 26.1 minutes plus a 9.2-minute re-run pass.

## 3. Deviations (from docs/decisions.md)

- **D1 / S4(d) — 128K headline on all units.** One stock window (stage3-128K:3) stayed
  paging-flagged after its re-run (22,810 major faults, 4,200 MiB swap growth), leaving 4 clean
  paired units. The headline is labelled "includes paging-flagged stock windows"; the clean-units
  figure stands beside it — 0.711 [0.673, 0.750] (n=4) — and both versions agree in sign and in
  whether each interval excludes 1.0. The declared §5.4 rule, not a judgement call.
- **D2 — tuned-64K paging** is the known file-page faulting of the MTP cell (Stage 2a); not
  investigated. All four flagged units re-ran clean; the gate passed under both denominators
  (36.4% tool / 23.5% per A7, limit 40%).
- **D3 — 32K swap sensitivity not material.** Point estimates barely move; the 32K decode gain is
  small and not robust to excluding swap-active units (tg@24K 1.089 [0.996, 1.190] → 1.057
  [0.859, 1.300] when 3 of 5 pairs are dropped); T_turn_400 conclusions unchanged.
- **D7 — sanity file name** is `data/sanity/stage3-tuned.json` (runbook said `stage3-all.json`).
- **D8 / E-006 / E-014 — history scrub, no rewrite.** The current tree has 0 findings. The
  history scan finds exactly 6 known lines across four allowlisted
  commit×path pairs: `26faadd` and `dfcd7d9` × docs/decisions.md (the WP0 account-name occurrence
  and its removal side — **the E-014 pair, option A, recorded here per the decision's scope**),
  and `3f41e18` and `bc8e0c3` × docs/recon/loop-states.md. The account name is already public as
  the author on every commit; history is not rewritten. File and commit counts are in
  docs/recon/scrub-report.md; they change with every commit.
- **D9 — hit-rate caveat.** Rates include warm-up and attempt-1 units of re-run windows, are
  decode-batch only (no prefill hit rate), and the workloads are public code the model may have
  seen in training.
- **R5 / E-008 — Stage 4 run 1 superseded** (Gen3 x8 link), never deleted; run 2 is the S2 run and
  the only re-run (R6); every measured-window sample read Gen4 x8 (R7 as clarified by E-009).
- **E-009 — kernel/driver confound.** Run 2 ran on 7.3.4-1-cachyos / 620.70.06 vs Stage 3's
  7.3.1-1-cachyos / 615.78.08, with a fit-warning second symptom (18 MiB short, 31 MiB free-memory
  drop). Correlation, not proven causation; no re-measure, the data stands.
- **Stages 1–2 ran with desktop apps open** (gate G3 not met) — selection data, not headline.
  Stages 3–4 were quiet (G3 in full).
- **Stage 2 plan deviations.** 2c (`--load-mode dio`) not run — `--cache-ram 2048` had already
  removed the paging and dio would pin 18.9 GiB on a 32 GB machine; 2d (threads) skipped — the
  default is already 8. MTP draft length 2 excluded by the sanity rule (deterministic 8-gram
  repetition), thresholds unchanged. The 32K tuned KV type is the 8-bit default, not a 2b result.
- **D4 / D5 (tooling, not data).** Test version literals and sweep-probe test flakiness fixed in
  T-009; no measured number changed.
- **Corrections carried into all text** (shared rule 8): 1 flagged window of 80 (not 100) in the
  later Stage 2 sessions; MTP helped about 2 to 5% per turn (not 3 to 5%), costs 9 to 16% of
  prefill speed and 0.75 to 1.5 GiB of VRAM; Stage 3 took about 2.1 hours.

## 4. Open issues

1. **MTP draft length 2** gives a deterministic repeated phrase on one of three sanity prompts,
   on four configurations; unresolved whether a speculative-path fault or a threshold artifact.
   Upstream draft written, **not filed** (`docs/upstream/llama-cpp-mtp-draft2-repeated-phrase.md`).
   Steps 3b and 7 should look at it before relying on draft lengths above 1.
2. **#28619 comment draft** (`docs/upstream/llama-cpp-28619-comment-draft-state.md`), not filed.
   The upstream re-check (§8) now confirms the issue closed as completed on 2026-10-15 via merged
   PR #30574 — the draft's "may already be fixed" premise is confirmed. Decision (E-015): the
   comment is retired and not filed. The issue is closed as completed (PR #30574, merged
   2026-10-15) and the draft has no negative control. The draft stays in docs/upstream/ as a
   record that the draft state survived save/restore on b12208 up to 8,192 tokens.
3. **Unexplained VRAM residual**: 512–532 MiB (MTP cells) vs 337–363 MiB (without MTP) at every
   context; the 170 MiB difference is not a logged compute buffer and was not attributed.
4. **Run 1's Gen4→Gen3 link drop has no proven cause**; the 2026-11-12 suspend/resume is the only
   candidate. A recurrence is escalation material, not a re-run. Run 2's kernel/driver confound
   (E-009) travels with the S2 result.
5. **zram swap behaviour**: with swappiness 150 the kernel swaps cold llama-server pages even with
   about 20 GiB available; Step 1 runs on this PC will see the same. Stock pages at 32K too (one
   Stage 3 window: 12,456 major faults, 6,321 MiB swap growth).
6. **T-021 F-6 carry-forward**: release archive vs the gitignored job `status.json` files — for T-015.
7. **Number-checker blind spots** (T-010 review F-1): the checker guarantees decimal-token presence
   in declared sources only; integers and whole `derived:` lines are exempt. T-013's check c and
   the T-016 publish gate rely on the manual coverage recorded in the reviews.
8. **E-011 option-B kit repair** (decision-recording order; plan amends preserving `steps_done`)
   is queued after the release.
9. **Upstream drift** (§8): llama.cpp v1.0.0 released and b-tags advanced past the pin; dsh's
   `latest` moved to the 0.2.2 series. Re-pin decisions belong to the next step, under the 7-day rule.
10. **Provenance note** (T-010 review F-2): "draft length 1 is bit-identical to MTP off" is the
    plan's recorded finding, not re-derivable from the committed sanity JSONs (pass/fail only).

## 5. Notes for the executive chat (plan §13, carried forward)

- **MTP and parallel slots**: MTP works with `-np 2` on the pinned build (both slots draft, context
  split) — the Step 4/5 "second server slot" designs are not blocked by MTP.
- **Control harness**: OpenCode chosen; the project plan text still says "OpenCode or Claude Code".
- **Sweep tooling**: expert-cache and MTP results come from llama-server with real prompts, not
  random-token llama-bench (kept as a labelled cross-check).
- **Estimates replaced by measurement**: mean bytes per expert 1,904,640 = +5.8% vs the plan's
  1.8 MB; KV bytes per token 20,480 at f16 (+2.4%) and 10,880 at q8_0 (+8.8%). No material difference.
- **MTP draft state across save/restore** survived on b12208 (identical draft counts at 181 and
  3,191 tokens of history; no negative control, no history above 8,192 tokens). #28619 is now
  confirmed fixed upstream (§8); Step 3b and Step 5 should verify on their own pinned build.
- **MTP draft length 2**: see open issue 1.
- **What moved the numbers in Stage 2**: batch 4096 more than doubles prefill over the default;
  P6 (all experts host-side, large VRAM expert cache) beat `--fit` in every context; FP16 KV beat
  8-bit at 64K/128K; MTP helped about 2 to 5% per turn and not at all at 128K (VRAM margin).
- **Host prompt cache on 32 GB**: the default `--cache-ram 8192` plus the 20 GiB mmap model pushed
  the machine into paging; 2048 was chosen by the 2f rule. Step 5's host-RAM state parking competes
  for the same memory.
- **Real agent turns**: the 3,000 + 400 turn is standardised; Step 1 should report per-turn new and
  generated tokens from real tasks.
- **Idle desktop apps cost about 1%**: Stage 3 quiet-machine means were 0.7 to 1.3% faster than the
  Stage 1/2 selection figures for the same configurations.
- **Release**: Step 0 follows the lighter standard — a tagged baseline release in the umbrella repo.

## 6. Suggested project-plan changes

1. Replace "OpenCode or Claude Code" with OpenCode (control harness decided, WP7).
2. Steps 3b/5: #28619 is fixed upstream (closed completed 2026-10-15, PR #30574 merged) — verify on
   the build Step 3b pins.
3. Steps 3b/7: investigate the draft-length-2 repeated phrase before relying on draft lengths > 1;
   the issue draft is ready for Zack to file.
4. Step 3b: `--moe-cache-audit` depends on PR #30594, still open — keep the router-hook fallback.
5. Step 5: host-RAM state parking competes with the mmap model and prompt cache on 32 GB (paging
   measured); carry the `--cache-ram 2048` result and the zram behaviour into its design.
6. Step 1: report real per-turn token counts; expect the same swap behaviour on this PC.
7. Use the measured KV/expert sizes (§5) instead of the plan estimates in all later sizing.
8. At the next step boundary: re-evaluate the llama.cpp pin (v1.0.0 / newest b-tag, §8) with the
   canary set, and the dsh pin (0.2.2 series published) under the 7-day rule. OpenCode unchanged.

## 7. Release checklist (plan §9) with evidence

| # | item | status | evidence |
|---|---|---|---|
| 1 | v0.1.0 tagged + CHANGELOG entry | done (T-015) | `CHANGELOG.md` v0.1.0 entry (T-010); annotated tag v0.1.0 on `6c83c15` pushed to origin (T-015 S4); T-016 precheck `git ls-remote origin refs/tags/v0.1.0` PASS |
| 2 | README coverage (5 bullets) | done | `README.md` (T-010); T-010 review A4 checked all five §9 bullets |
| 3 | stock+tuned configs 32K/64K/128K + launch script | done | `configs/server/` six files; T-012 launched all six from a clean shell |
| 4 | sweep/analysis scripts documented, parameterised | done | README rerun guide, `configs/sweeps/` TOML specs, `docs/methodology.md` |
| 5 | unit tests local + CI green on GitHub | done (T-015/T-016) | T-009: `pytest -m "not gpu"` 1070 passed, 2 deselected; CI_CMD green 5× locally; GitHub CI run 43937943935 on tag commit `6c83c15` success (T-015); newest main run 43939214824 on `10d0767` success (T-016 S1, `gh run list`, 2026-11-16) |
| 6 | raw JSONL, env snapshots, microbenchmarks, health, report with CIs, exact commands | done | `data/raw/` (Stages 1–4, run 1 superseded kept), `data/env/`, `data/health/`, `reports/baseline-report.md`, `docs/recon/commands.env` |
| 7 | provenance (tag, commit, flags; model repo/revision/SHA-256; harness versions) | done | `data/env/build-info.json`, `configs/model.toml`, `configs/harness.toml`; baseline report §2 |
| 8 | data scrubbed; prompts as recipes only | done | T-013: `scripts/release-check.sh` exit 0 — 0 findings; history: 4 allowlisted pairs (§3, D8/E-014); `docs/recon/scrub-report.md` |
| 9 | write-up draft reviewed (GitHub only) | done (E-015) | planning-chat review of this report and reports/writeup.md, E-015, edits listed in docs/decisions.md |
| 10 | LICENSE (MIT) + LICENSE-DATA.md (CC BY 4.0) | done | release-check e) both present |
| 11 | upstream bug drafts with evidence | done (the #28619 draft is retired; the draft-length-2 issue draft is not filed, Zack's choice) | `docs/upstream/` two drafts (T-011) |
| 12 | progress log complete + completion report delivered | this report; delivery via the review | `docs/progress-log.md`; this file |

**Success criteria (plan §2), final assessment:**

| criterion | verdict | evidence |
|---|---|---|
| S1 Coverage | met | Stage 1 screening 57 cells (n=2, eligibility table in `reports/stage1/select-screening.md`); Stage 2 features (2c/2d recorded not-run); Stage 3 six cells ×5; Stage 4 two cells ×5 (run 2); raw JSONL committed |
| S2 Reproducibility | met | 6/6 rows PASS on run 2 (`data/analysis/stage4/s2-summary.md`); clean-shell walkthrough 6/6 PASS, all 45 link samples "4, 8" (`data/health/readme-walkthrough.log`, T-012) |
| S3 Decisions | met | six configs, tuned chosen by the §3.3 rule; each launches via `scripts/launch-server.sh` |
| S4 Health checks | met, deviations recorded | (a) tensor screen: no known broken-head signature (`data/health/model-check.json`); acceptance 0.771 ≥ 0.5 on the code workload (Stage 2a), WP5 greedy 0.886 <!-- derived: 0.8855507868383404 rounded to 3 decimals, data/health/endpoints-2026-11-08.json -->; (b) Appendix B endpoints work (`data/health/endpoints-2026-11-08.json`); (c) greedy MTP on/off divergences all near-tie (top-2 gap < 0.5 nats, same file); (d) env snapshot + warm-up every run; the 128K headline's flagged window is the declared D1/S4(d) deviation, labelled, clean figures beside it; (e) both smoke tasks PASS (WP7, `data/harness/`) |
| S5 Release | met (T-015/T-016) | repo PUBLIC and release v0.1.0 "v0.1.0: Step 0 baseline" published 2026-11-16T19:32:44Z, not draft (`gh repo view` / `gh release view`, T-016 S1; Zack ran the two publish commands at the gate); checklist rows 1 and 5 done; scrub and release checks pass (T-013) |

## 8. Upstream re-check (read-only, 2026-11-15)

Method: GitHub REST API (unauthenticated) for releases/tags/issues, git ls-remote for b-tags,
npm registry for harness versions; discussion pages read as HTML (the issues API 404s them).

**llama.cpp** — pinned `b12208` (commit `57d04820`, built 2026-11-08). Newest release: **v1.0.0**,
published 2026-11-13 (tag `v1.0.0-b12359-b1b770d`, i.e. build b12359 — 151 builds past the pin
<!-- derived: 12359 - 12208, tag names above -->). Newest b-tag: **b12415**, commit `4e5116f47619`,
2026-11-15 — 207 builds past the pin <!-- derived: 12415 - 12208, git ls-remote -->. At pin time the
newest semver tag was v0.9.0; v1.0.0 is a new upstream milestone. No re-build or re-measure is
proposed for Step 0; the pin stands for the release.

| ref | kind | status (2026-11-15) | date |
|---|---|---|---|
| #28619 — /slots save/restore never persists draft context | issue | **closed, completed** — fixed by PR #30574 "server: save the draft state in the slot file" (merged) | closed 2026-10-15; PR merged 2026-10-15 |
| #30594 — hybrid MoE expert cache, profile prefilling, `--moe-cache-audit` | PR | **open** (last updated 2026-11-10) | Step 3b's trace format depends on it |
| #30664 — sharing prompt prefixes across sessions | discussion | open discussion (no close state) | started 2026-10-16 |
| #23262 — "UBBoost": larger ubatch for prompt processing | discussion | open discussion (no close state) | started 2026-05-18 |
| #26448 — MoE experts from host RAM via PCIe DMA | issue | **closed, not_planned** (stale) | closed 2026-10-11 |
| #20697 — disk-based context checkpoints (`--cache-disk`) | issue | **closed, not_planned** (stale) | closed 2026-11-07 |
| #22384 — checkpoint restore for hybrid/recurrent models | issue | **closed, completed** | closed 2026-04-26 |

**Harnesses** — OpenCode `opencode-ai`: pinned 1.19.5 (published 2026-10-28); npm `latest` is
still **1.19.5 — unchanged**. dsh `@deepseek-ai/dsh`: pinned 0.2.1-rc.5 (published 2026-10-29);
npm `latest` is **0.2.2-rc.1** (published 2026-11-04 — already `latest` at install time, rejected
then by the 7-day rule); newest by publish time is 0.2.2-rc.3 (2026-11-13, `next` tag); `alpha` is
0.2.2-alpha.3. The Step 0 pin stands; re-pin under the 7-day rule at the next step boundary.

---

*Reviewed by the planning chat (E-015) on 2026-11-15; the edits it listed are applied as recorded
in docs/decisions.md.*