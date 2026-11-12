# Step 0 Plan: Baseline Setup

*Version 1.8 · 12 November 2026*
*Part of "Local AI on a Small PC" (project plan dated 5 November 2026). This file is the reference for Step 0. Any change produces a new version, recorded in §14.*

---

## 1. Objective and scope

Step 0 turns the project plan's pre-measurement estimates into measured facts. It delivers:

- a working, documented llama.cpp setup for Ornith-1.5-35B-A3B on this PC;
- a defined **stock** and **tuned** server configuration for each of 32K, 64K and 128K context;
- the baseline numbers that every later step is compared against;
- both harnesses (dsh and OpenCode) installed, pinned and smoke-tested against the local server.

**In scope:**
- the llama.cpp build;
- model download and MTP-head verification;
- endpoint health checks;
- microbenchmarks (PCIe, RAM, NVMe);
- engine sweeps: expert placement, expert cache, batch size, context, MTP, KV type and load mode;
- harness setup;
- a tagged baseline release.

**Out of scope:**
- Strata and Qwen3.8-Flash-Next (shelved);
- quantization comparisons and task-success measurement (both Step 1);
- Claude Code as a control harness (possibly a small cross-check in Step 1).

---

## 2. Success metric (fixed before anything is built)

Step 0 is done when S1–S5 all hold. There are no hard speed targets.

| ID | Criterion | Verified by |
|---|---|---|
| **S1 Coverage** | Every cell of the declared sweep design (§5.4) is either measured or recorded as "did not fit" with its error. Screening may use 2 repetitions. Every configuration that appears in reported results, or is recommended, has at least 5 repetitions with 95% CIs. Raw per-request data is committed. | Coverage report from the analysis tooling; JSONL record counts |
| **S2 Reproducibility** | The headline numbers for stock-64K and tuned-64K (T_turn_400, fresh prefill at 32K, decode at 32K depth) are re-measured on a different day. Each falls inside its original 95% CI or within ±5%, whichever is wider. Every recommended config also launches from a clean shell using only the README commands. | Stage 4 run; README walkthrough log |
| **S3 Decisions** | There is a stock and a tuned llama-server config for each of 32K, 64K and 128K. The tuned one is chosen by the pre-declared rule (§3.3). Each launches with `scripts/launch-server.sh`. | Config files; selection table in the report |
| **S4 Health checks** | (a) The MTP head shows none of the known broken-head signatures in the tensor screen (WP4), and real draft acceptance is at least 50% at draft length 1 on the code workload (WP5). The acceptance test is what proves the head works; the tensor screen only rules out known failures before benchmarking. (b) Every endpoint and field in the project plan's Appendix B works on the pinned build, or the deviation is documented. (c) Greedy outputs with MTP on and off diverge only at near-tie tokens. (d) Every measured run has a complete environment snapshot and a warm-up. No selected or recommended configuration, and no headline number, rests on a measurement with an unresolved flag. Measurements that are still flagged after their retry stay in the report, marked as excluded diagnostic results. (e) OpenCode and dsh each complete the smoke task against the local server. | `data/health/*.json`; flags column in the report; smoke-test logs |
| **S5 Release** | The release checklist (§9) is complete and v0.1.0 is tagged. | Checklist with evidence in the completion report |

---

## 3. Definitions

### 3.1 Stock configuration (per context C)

"Stock" means what a typical user would run, as confirmed by the executive chat:

- the model card's recommended settings (sampling, template defaults);
- llama.cpp's automatic placement (`--fit`, on by default). If `--fit` misbehaves, use the simplest `--n-cpu-moe N` that fits;
- default batch sizes (`-b 2048 -ub 512`), FP16 KV, default flash attention (`auto`), default slot count, and no speculative decoding;
- only `-m`, `-c C`, `--host` and `--port` set explicitly, plus `--metrics` and logging, which don't change inference;
- OpenCode with its default settings as the stock harness.

### 3.2 Tuned configuration (per context C)

The tuned configuration is Step 0's best configuration for that context, chosen from the measured candidates by §3.3.

### 3.3 Selection rule (declared before any speed measurement)

A candidate is eligible for a context if:
- its final cell status is complete (it started without errors and finished);
- the minimum free VRAM across its measured windows, in the final attempt, is at least 512 MiB;
- it has no unresolved flagged unit, where a unit is one repetition and an attempt-2 unit replaces the attempt-1 unit it re-ran;
- it has enough clean units: 2 in screening, 5 in final selection;
- it has not failed the output sanity check (§5.6). In screening the check may be "not run". In final selection it must have passed.

Among eligible candidates, order them by the **mean T_turn_400** (the estimated standardised turn, §5.3): the mean over repetitions of each repetition's mean over the three depths of §5.3. A repetition counts only if all three depths are clean. Final selection then compares the best-mean candidate with the runner-up, using the paired per-repetition difference of T_turn_400 and its 95% CI (§5.5):
1. If the CI excludes zero, the best-mean candidate wins.
2. If the CI includes zero, compare the paired difference of **T_reread** in the same way. If that CI excludes zero, the candidate with the lower mean T_reread wins.
3. If both CIs include zero, the candidates are tied on speed: prefer fewer moving parts, which means no MTP over MTP, then no expert cache over a cache.
4. If still tied, prefer the lower peak VRAM use (total minus the minimum free VRAM over its windows).

Any other eligible candidate whose paired T_turn_400 difference from the winner has a CI that includes zero is reported as "statistically tied with the winner", for information only. Screening (2 repetitions) applies no tie-break: its shortlist is simply the two eligible candidates with the lowest mean T_turn_400 per context, and pairs whose means differ by less than the larger of their two ranges are marked "too close to call at n = 2". The stock cell is a reference row and is never shortlisted.

### 3.4 Standardised turn workload

The benchmark's standard turn is **3,000 new prompt tokens** appended to a cached context, followed by **400 generated tokens** (thinking included). It is fixed for Step 0 and used for configuration selection, so every configuration is compared on exactly the same turn.

It is a standardised workload, not a model of real agent use. Real turns vary widely in how many tokens they add and generate, and Step 1 records those per request on real tasks. WP7's smoke task only proves that the harnesses work; its request pattern is reported as smoke-task data, never as representative of agent use.

---

## 4. Fixed decisions

| Topic | Decision |
|---|---|
| Model | Ornith-1.5-35B-A3B, one Q4-class GGUF (Q4_K_M or UD-Q4_K_XL) from a reputable publisher. **Primary:** the official `ornith-ai/Ornith-1.5-35B-A3B-GGUF` Q4_K_M, at a revision from on or after 2026-08-23, when ornith-ai updated the MTP weights. **Fallback:** `bartowski/Ornith-1.5-35B-A3B-GGUF` Q4_K_M, only with Zack's approval. No quant sweep. |
| Engine | Mainline llama.cpp, the newest release tag at build time (b12017 or later), pinned by commit. Built with CUDA and `CMAKE_CUDA_ARCHITECTURES=120`. |
| Harnesses | Control: OpenCode, exact version pinned. Research: dsh, exact version pinned for both the CLI and its plugins. |
| Languages | Bash for the launch and long-job scripts; Python managed with uv for everything else; TOML for configs. |
| Repo | Umbrella repo `ZHarvett/local-ai-research`, private until release, located on the 256 GB SSD (exact path found in WP0). Claude Code may push to it; Zack makes it public and publishes releases. |
| Licenses | MIT for code; CC BY 4.0 for data, report and write-up. Copyright holder: ZHarvett. |
| Write-up | GitHub only: a short post, "What a 16 GB GPU actually does with a 35B MoE model". |
| Storage | Repo, models and data on the 256 GB NVMe SSD. About 90 GB is available; Step 0 needs about 30 GB. |
| Display | Both monitors on the motherboard outputs (iGPU), so the RTX 5060 Ti runs no display clients. |
| Machine tuning | Frozen for the whole project and recorded with every run. Any change triggers a short re-check (the canary set). |
| Long jobs | Claude Code may start them, always detached via `scripts/run-detached.sh`, logged, lock-protected and resumable. |
| sudo | Never run by Claude Code. Claude Code proposes the exact commands, and Zack runs them. |

---

## 5. Measurement design

### 5.1 Principles

1. **llama-server's response `timings` are the authoritative speed source.** Client wall-clock times are recorded alongside them.
2. **No random-token numbers for expert-cache or MTP results.** llama-bench builds its prompts from random token IDs, which distorts MoE routing (whole groups of experts go unused) and therefore cache hit rates and draft acceptance. All reported numbers come from llama-server with real, public coding prompts. llama-bench is used once, as a clearly labelled cross-check (Stage 2e).
3. **Every server start gets a warm-up**, and every run records an environment snapshot and continuous telemetry.
4. **Every long session is bracketed by a canary measurement**, run at the start and the end, to detect drift and heat soak. The canary is a fixed candidate configuration named in the sweep spec (by default `--fit` at 64K with 8-bit KV), measured with 3 repetitions of the short point and the 16K pair. Canary requests use repetition indices from 100 upward, so each one gets a fresh nonce and the end canary can't be served from the cache.
5. **Nothing is left implicit.** Every llama-server argument that matters is either set or deliberately left at its default, and the effective values are captured from `/props` and the startup log. The default port is 9931, so an explicit port is always set.

### 5.2 Workloads (built in WP8)

- **Sources:** two permissively licensed public repositories at pinned commits, one in Python and one in Rust or TypeScript.
- **Prompt variant:** a system prompt, then real source files packed to an exact token length (counted with `/tokenize`), then an instruction that asks for code. Prompts follow the model's chat template.
- **Append chunk:** about 3,000 tokens of tool-output-like text (for example a test log or file listing from the same repos), plus an instruction.
- **Variants:** 5 per length; repetition r uses variant r mod 5. K = 1,024 tokens throughout, so 96K is 98,304 tokens.
- **Per-request nonces:** every fresh request (each Request A, the short point, the warm-up and every canary request) starts with its own unique nonce at the very beginning of the system message. A per-repetition nonce would not be enough: the prompts for different depths of the same variant share their opening files, so a longer prompt could reuse a shorter one's cached prefix. The nonce also prevents matches against anything kept in the host-RAM prompt cache.
- **Exact prefixes:** Request B (§5.3) must begin with Request A's exact token sequence, so token arrays are sent to `/completion`.
- **BOS and special tokens:** llama-server adds BOS automatically only to string prompts, never to pure token-ID arrays. WP8 therefore reads the model's `add_bos_token` metadata, tokenizes with matching `/tokenize` settings (special tokens parsed), and checks that a token-array request matches the equivalent string request.
- **Special-token strings:** repository files and command outputs that contain any of the model's special-token strings are excluded, because prompts are tokenized with special tokens parsed and such text would silently become control tokens.
- **What is committed:** only the recipes (repo, commit, file list, instruction, token count, and SHA-256 of the rendered text). The prompts themselves are regenerated deterministically.

### 5.3 Per-cell protocol

One server configuration is one **cell**. For each cell:

1. **Preconditions.** The runner checks that:
   - the GPU lock is free;
   - no other GPU compute processes are running;
   - no display clients are on the dGPU (warning only);
   - `MemAvailable` is at least 24 GiB (warn below this) and at least 20 GiB (abort below this);
   - the CPU is idle: busy time below 10% averaged over 10 seconds (from `/proc/stat`). The 1-minute load average is recorded but is not the gate, because it lags for minutes after a heavy run. If the idle check fails, the runner re-checks every 10 seconds for up to 10 minutes, records the wait, and treats it as a transient failure if it still fails.
   - **Retries:** a transient failure (the idle check times out, or `MemAvailable` is below the abort line) is retried up to 3 more times with a 10-minute pause, and every attempt and wait is recorded. Hard conditions abort the session at once, and it stays resumable: the GPU lock held by another job, a foreign GPU compute process, a busy port, or a missing binary.
2. **Start the server.** Record load time, the startup log and the effective settings from `/props`.
3. **Snapshot and telemetry.** Take an environment snapshot and start 2 Hz telemetry.
4. **Warm-up.** Send 2 requests (8K-token prompt, 128 generated tokens) and discard them.
5. **Repetitions.** For each repetition, with the depth order shuffled using a fixed seed:
   - **Short point:** a fresh 2K-token prompt with up to 400 generated tokens.
   - For each depth d in D(C):
     - **Request A:** a fresh prompt of length d with `n_predict: 0`. The prompt is evaluated into the cache. On the pinned build the server still reports one generated token (`predicted_n` = 1), but Request B reuses exactly d tokens, so the cached state ends at A. The runner asserts `prompt_n + cache_n` = d and `cache_n` ≤ 32, since only the template's fixed opening tokens may match. A larger `cache_n` raises the `warm_prefill` flag, and that request is not used for PP_fresh or T_reread.
     - **Request B:** the same tokens plus the 3,000-token append, with up to 400 generated tokens. The runner asserts `prompt_n + cache_n` = d + 3,000 and checks that `cache_n` ≥ 0.95·d, raising the `cache_miss` flag otherwise.
   - D(32K) = {8K, 16K, 24K}; D(64K) = {16K, 32K, 48K}; D(128K) = {32K, 64K, 96K}.
6. **Clean shutdown** (SIGINT). Parse buffer sizes, placement decisions and expert-cache statistics from the log.

**Sampling:** the model card's recommended parameters, with a fixed seed per request. Thinking stays at the template default, which is recorded. Greedy decoding is used only in the equivalence checks.

**What T_turn_400 represents:** an *estimate* of the standardised turn: an ideal cache hit (the new tokens are a pure append) followed by exactly 400 generated tokens. `n_predict` is only a maximum, so the model may stop earlier. The actual `predicted_n` is therefore recorded for every request, and the measured time of each Request B (T_B) is reported alongside the estimate. WP8 chooses instructions so outputs normally reach 400 tokens. Real-world cache misses are measured in Step 2, and real agent turns in Step 1.

**Derived metrics, per depth:**

| Metric | Definition |
|---|---|
| PP_fresh(d) | Prefill tokens/s of Request A |
| PP_inc(d) | Prefill tokens/s of Request B; expects `prompt_n` ≈ 3,000 and `cache_n` ≈ d |
| TG(d) | Generated tokens/s of Request B |
| T_turn_400(d) | **Estimated** standardised turn: prefill time of B, plus 400 × (time per generated token in B) |
| T_B(d) | **Measured** time of Request B as it actually ran (prefill plus `predicted_n` generated tokens), always reported with `predicted_n` |
| T_reread(d) | d / PP_fresh(d), the cost of a full cache miss at that depth |
| Acceptance | `draft_n_accepted / draft_n` (MTP cells only) |
| TTFT | Client-side time to the first streamed token of B |
| Memory | VRAM after warm-up and at peak; server RSS; major page faults and swap-in per measured window |

### 5.4 Sweep stages

**Sweep defaults apply to candidate cells only:** 8-bit KV (`-ctk q8_0 -ctv q8_0`), `-fa on`, `-np 1` and an explicit port, unless a stage says otherwise.

**Stock cells keep exactly the §3.1 settings in every stage:** FP16 KV, flash attention `auto`, the default slot count, `-b 2048 -ub 512` and no speculative decoding. Tuned configurations are therefore always compared against genuine stock.

**Logging and hit rates:** every cell, stock included, runs with `-lv 4`. This is logging only, which §3.1 allows, and WP5 measured no speed cost. It provides the placement trace, the buffer sizes and the expert-cache statistics. The statistics give hit rates for decode-sized batches only; prefill-sized batches report only how many experts were copied from the cache.

**Stage 1: Screening** (2 repetitions; WP11; about 4 to 5 hours of GPU time, run as three sessions)

Run every placement below for each context C ∈ {32K, 64K, 128K} and each batch setting (b, ub) ∈ {(2048, 2048), (4096, 4096)}:

| Cell | Placement |
|---|---|
| P1 | `--fit` with its default 1024 MiB margin |
| P2 | `--fit --fit-target 256` |
| P3–P5 | `--fit` plus `--moe-cache-mib` of 1024, 2048 and 4096 |
| P6–P7 | `-cmoe` plus `--moe-cache-mib` at max-fit and at max-fit − 2048. Max-fit is found by binary search in 256 MiB steps: the largest cache for which the server starts with the explicit placement unchanged and at least 512 MiB stays free after the longest request. `--fit` stays at its default for these cells, so its 1,024 MiB margin applies and a probe step where `--fit` intervenes is rejected. On this card the fit margin is the binding limit (about 1.35 GiB free), which makes the cache 512 to 768 MiB smaller than a 512 MiB rule alone would allow, and keeps the setting safe on other cards. |
| P8–P9 | `--n-cpu-moe` at N_fit and at N_fit − 2. N_fit is the number of expert layers that P1's fit placed on the CPU, read from its log; if it can't be derived, it is the smallest N that fits, found by binary search. |

Add the stock configuration for each C, for 57 cells in total.

**Sessions.** Stage 1 runs as three sessions, one per context (`--only context=32K`, then 64K, then 128K), each with its own start and end canaries, so a drift flag covers 2 to 4 hours instead of one 9-hour block. Inside a session, the cell order is a seeded shuffle that respects the one dependency (P1 before P8 and P9 of the same group), so slow thermal or background drift cannot line up with a placement. Real sessions start only from a clean committed tree (no `--allow-dirty`), and a resumed session must match its spec, workload manifest and sampling hashes.

**Time.** The WP11 pre-flight measured one repetition of ten cells. Candidate cells run at 40 to 53% of the earlier estimate, because the larger batch settings (`-ub 2048` or `4096`) prefill 2.3 to 2.9 times faster than the default `-ub 512` (PP_fresh at 16K: about 2,300 and 2,900 tokens/s against about 1,000), while decode speed is unchanged. Expected per session: 32K about 0.85 h, 64K about 1.3 h, 128K about 2.2 h, 4.3 h in all (5.0 h upper bound), including probing and canaries. These come from one repetition per cell and are good to about 15%.

**Pre-flight (done in WP11 part 1).** A short real run covered what the WP9 mini-sweep could not: one cell of each placement family on the GPU (including `-b 4096`), the max-fit probe at 32K and 128K, N_fit from P1's log, and the re-run mode on real hardware. All ten cells completed with no flags and no swap activity, `--fit` left the explicit placements of P6 to P9 unchanged, and the re-run left the old record lines byte-identical. Pre-flight data is functional-test data and is not reported as results. The probe cache from the pre-flight is retired before the real sessions, so every probe is measured under the same conditions as the session that uses it.

Output: for each context, the shortlist of §3.3 (the top 2 eligible placements by T_turn_400, with the stock reference row), plus VRAM breakdowns and expert-cache hit rates.

**Stage 2: Features** (5 repetitions per cell; WP12; about 6 to 7 hours of GPU time, in several sessions)

Stage 2 starts from the Stage 1 shortlist: for each context, the two eligible placements with the lowest mean T_turn_400 (all six are `-b 4096`; at 32K and 64K one is P6 and one is P2, and at 128K the pair is P2 and P6 in the same way). "Top" means first in the Stage 1 order, even where the pair is too close to call at n = 2. Every Stage 2 cell is a candidate cell with the §5.4 defaults, `-lv 4` and `--metrics`, runs 5 repetitions, and each sub-stage is its own session with its own start and end canaries. The decision rules below are declared before any Stage 2 measurement.

- **2f Host prompt cache (`--cache-ram`). Runs first.** Reason: in Stage 1, 14 of 38 windows at 128K and one at 64K were paging-flagged, all in the second repetition of a long-running server, in cells with a large memory-mapped model. The 15 re-runs on fresh servers were all clean, and the server's anonymous memory grew in step with its host prompt cache (default 8,192 MiB), which every unique benchmark prompt fills. That points to host-memory pressure on a 32 GB machine, and the benchmark's requests never hit that cache, so it only costs memory here. Cells, with MTP off: the top placement at 128K with `--cache-ram` 8192 (the default), 4096, 2048 and 0; and at 64K with 8192 and 2048. Rule: the chosen value is the largest tested value with no paging-flagged window in any of its 5 repetitions, unless its mean T_turn_400 is more than 3% above the mean of the 8192 cell's clean units. If the 8192 cell is already clean, the default stays. If no tested value is clean, stop and report: the cause is then not the host cache. The chosen value is used in every later candidate cell and in the tuned configs. Stock keeps the default. The trade-off is documented: a small host cache means that switching between conversations re-reads the prompt instead of restoring it (this matters for Step 5).
- **2a MTP.** Per context, 6 cells: both shortlisted placements with MTP off (these are also the 5-repetition measurement of the shortlist), the top placement with draft lengths 1, 2 and 3, and the second placement with the best draft length of the top placement. The best draft length is chosen by the §3.3 rules among the three; if the CIs include zero, the smaller draft length wins. Cache sizes of P6 cells are re-probed with MTP on, because the head and its draft context cost VRAM. Record acceptance, and the effect on decode **and on prefill**. MTP joins a tuned config only if it wins by §3.3 on T_turn_400 and passes the output sanity check.
- **2b KV type.** FP16 vs 8-bit KV at 64K, on the 2a winner at 64K, with the cache re-probed for the FP16 cell.
- **2c Load mode.** `--load-mode` at 64K on the 2a winner, with paging metrics: `auto` against one alternative chosen from the build's own help text and source. Modes that need `sudo` or a raised memory-lock limit are excluded (the limit here is 8 MiB). The choice and its reasoning are recorded before the run.
- **2d Threads (optional).** `-t 8` against the default at 64K, only if the default differs (check the effective thread count in the log); otherwise skipped and recorded.
- **2e llama-bench cross-check.** llama-bench at the nearest configuration it supports at 64K, labelled as a cross-check and never used for a decision, to show how far random-token numbers differ from real-prompt numbers. Fields llama-bench cannot express (for example `--moe-cache-mib`) are listed.
- **Output sanity check (§5.6).** On the 2a winner and runner-up of each context and on the plain `--fit` reference of the same context, before Stage 3.

Order: 2f, 2a, 2b, 2c, 2d, then the sanity check and 2e. The 2a spec is generated from the Stage 1 shortlist and the 2f result by a tool, and the second placement's cell from the 2a main result.

**Stage 2 outcome (WP12, 10–11 November; desktop apps open, so these are selection data, not headline results).**

| Context | Tuned configuration | T_turn_400 (s), 95% CI | Stage 1 stock (n = 2) |
|---|---|---|---|
| 32K | P6 (`-cmoe`, expert cache 11,520 MiB), `-b 4096 -ub 4096`, 8-bit KV, no MTP | 5.92 [5.61, 6.22] | 8.45 |
| 64K | P6 (cache 9,472 MiB), `-b 4096 -ub 4096`, FP16 KV, MTP draft length 1 | 6.49 [6.13, 6.85] | 9.36 |
| 128K | P6 (cache 8,704 MiB), `-b 4096 -ub 4096`, FP16 KV, no MTP | 7.97 [7.67, 8.27] | 11.29 |

All three use `--cache-ram 2048`, pass the output sanity check and leave more than 1,000 MiB of VRAM free. How the rules played out, and where a human decided:
- **2f:** `--cache-ram 2048` by the rule. Flagged windows fell from 2 of 5 (8192) to 0 of 5 (2048 and 0) at 128K, and the server's memory growth followed the cache size. Only 0 was entirely free of faults and swap.
- **2a and 2a2:** MTP won at 32K (draft length 2) and 64K (draft length 1). At 128K every MTP cell of the top placement (P2) fell below the 512 MiB VRAM line, so the second placement was tested at the draft lengths that won elsewhere (a rule added before its data existed), and MTP off won there. P6 beat P2 in every context.
- **2b:** FP16 KV won at 64K and at 128K (about 8% faster per turn at 128K, despite a 1 GiB smaller expert cache). 2b was extended to 32K and 128K after the 64K result.
- **Output sanity check:** draft length 2 fails on one of three prompts, deterministically, on four configurations (two placements, both KV types, 32K and 64K): an 8-token phrase recurs 8 times, against 1 to 2 for the reference. Draft length 1 is bit-identical to MTP off, and draft length 3 passes. Draft length 2 is therefore excluded from every tuned configuration. Whether this is a real fault or a threshold artifact is unresolved. The 32K tuned configuration is the rule's winner among the 32K cells that pass (MTP off, 8-bit KV as measured).
- **Not run:** 2c (`--load-mode dio`), because `--cache-ram 2048` removed the paging it was meant to remedy (1 flagged window of 80 in the later sessions) and `dio` pins 18.9 GiB of unswappable memory on a 32 GB desktop; and 2d, because the default thread count is already 8.
- **Operational:** the step lead's stop rule for paging-flagged windows was relaxed from 20% to 40% after the 2a 64K session, where the flags came from file pages of the mapped model in MTP cells, not from swap. A bug in the re-run path that blanked two keys in cell summaries was fixed, and 21 summaries were repaired from their committed versions with an audit log.
- **Human decisions** (all in `docs/decisions.md` and `docs/stage2-summary.md`): the 2a 64K gate, the 128K draft-length rule, FP16 at 64K when the swap sensitivity lost its data, and the reading that a sensitivity check with fewer than 2 paired units is inconclusive.

**Stage 3: Final** (5 repetitions, paired; WP13; about 1.5 hours on a quiet machine, up to 2.5 hours with worst-case re-run passes)

Stock-C against tuned-C for each C. These are the headline results, so gate G3 applies in full: the desktop apps are closed. Rules, declared before any Stage 3 measurement:
- **Configurations.** The six cells are the released config files, `configs/server/{stock,tuned}-{32k,64k,128k}.toml`. The tuned files are the Stage 2 winners above. Stock is §3.1 unchanged, including its default host prompt cache. The measured argument lists are exactly what those files render, plus `--metrics -lv 4`.
- **Sessions.** One session per context, each with its own start and end canaries, from a clean committed tree. Stock and tuned of a context share a session, so their repetitions are paired.
- **Re-runs.** One `--rerun-flagged` pass per session, as before.
- **Stock paging.** Stock keeps `--cache-ram 8192`, so its later repetitions may be paging-flagged at 64K and 128K. That is how stock behaves on this machine, so it is reported, not hidden. Every stock-against-tuned comparison is computed twice: on clean units only, and on all units with the flags shown.
- **Headline rule.** The headline for a context is the clean-units comparison if both cells have at least 5 clean, paired units after the re-run pass. Otherwise the headline is the all-units comparison, labelled "includes paging-flagged stock windows", with the clean-units figures beside it, and S4(d) is recorded as a deviation for that context. If the two versions disagree in sign, or one interval excludes 1.0 and the other does not, the report says so in its first paragraph.
- **Tuned cells.** A tuned cell must be eligible in final mode (§3.3): 5 clean units, at least 512 MiB of VRAM free, and a sanity pass. The sanity check is run again on the three tuned config files. If a tuned cell is not eligible, the step lead decides; nothing is substituted automatically.
- **Gate and quiet machine.** Each session is checked with `python -m smallpc.stage3 gate`: the runner's criteria a to e as in Stage 2, and the paging and swap stop rules (40% of windows, 1,024 MiB of swap growth) over the tuned cells' and the canaries' windows only. Stock windows are reported and never fail the gate. `scripts/check-quiet.sh` must exit 0 before every session. It lists process names only and blocks the apps named in `configs/quiet-check.toml`. A session whose check fails during the run keeps its data, marked "quiet condition violated", and the step lead decides.
- **Reported figures.** Per context: T_turn_400, T_B with `predicted_n`, T_reread, PP_fresh and PP_inc per depth, TG per depth, TTFT, the VRAM breakdown, and the paired ratios tuned/stock with 95% CIs (§5.5), plus the swap sensitivity.

**Stage 4: Reproducibility** (a different day; WP13; about 30 minutes on a quiet machine)

Stock-64K and tuned-64K, 5 repetitions each, in one session with canaries. S2 is checked with `report repro` on T_turn_400, fresh prefill at 32K and decode at 32K depth. If stock-64K has too few clean units on either day, S2 is evaluated for it on all units, and the report says so.

### 5.5 Statistics

- **Unit:** one repetition, which is one prompt variant.
- **Per cell and metric:** report the mean, n, min and max, and a 95% percentile-bootstrap CI over repetitions (10,000 resamples, fixed seed). With n = 5, bootstrap intervals come out too narrow, so a t-interval is also computed and the wider of the two is reported.
- **Paired comparisons** (tuned vs stock, MTP vs no MTP): compute per-repetition ratios on the same variants, take the geometric mean, and report the wider of two 95% intervals: a percentile-bootstrap CI and a t-interval on the log ratios (back-transformed). The bootstrap alone covered only about 83% at n = 5 in the WP10 simulation.
- **Known limit of the intervals.** In the WP10 simulation (20,000 experiments per case), the reported interval, which is always the t-interval, covered about 95% for symmetric data at n = 5 and n = 10, 91–92% for strongly skewed data (lognormal σ 0.5) and 88–90% for exponential data. Step-0 timings are close to symmetric in the canaries, but a repetition slowed by background activity is exactly the heavy-tailed case, so the flag rules matter.
- **Swap sensitivity.** Every results table and paired comparison is also computed with the units excluded whose window shows llama-server swap growth of more than 64 MiB (`swap_activity`, §5.6). If a headline comparison changes sign or an interval changes materially, the report says so.
- **Screening results** (2 repetitions) are used only for shortlisting. They appear in a clearly labelled appendix and are never reported as results.

### 5.6 Flags and sanity checks

| Flag | Trigger |
|---|---|
| thermal | A GPU thermal or hardware slowdown reason is active in more than 1% of samples in the measured window, or CPU Tctl reaches 95 °C in more than 1% of samples. The GPU power cap is recorded, not flagged. |
| paging | llama-server has more than 1,000 major page faults during a measured window. Swap growth is recorded as `swap_activity` (MiB of `VmSwap` growth in the window, with start, end and maximum), not flagged. System-wide swap-in is recorded but not flagged. Reason (chosen after the WP9 mini-sweep, which showed it): this machine uses zram swap with `vm.swappiness` 150, and the kernel swaps cold pages of the server's own memory with about 20 GiB available. Three canary windows with 71–610 MiB of growth and 0–357 faults were not slower than unflagged windows. Pages that are swapped out and later read back show up as major faults in the later window. The one window with 4.1 GiB of growth also had 1,692 faults, so it is flagged. The swap sensitivity of §5.5 checks this choice in every report. |
| drift | A session's start and end canaries differ by more than max(their 95% CI, 5%). |
| short_gen | Request B generates fewer than 100 tokens. Its generation speed and T_turn_400 are excluded, because too few tokens give an unstable per-token time; its prefill numbers are kept. |
| warm_prefill | Request A (or another fresh request) reports `cache_n` > 32. |
| cache_miss | Request B is served with `cache_n` < 0.95·d. |
| accounting | `prompt_n + cache_n` differs from the expected total: d for Request A, d + 3,000 for Request B, and the prompt length for other fresh requests. |
| did_not_fit | Startup failure or out-of-memory. |

Flagged measurements are re-run once, except `short_gen`, which a seeded re-run would only repeat. If still flagged, they are excluded from selection and from headline numbers. They stay in the report as excluded diagnostic results, with the flag shown.

**Output sanity check:** greedy 512-token outputs on the 3 fixed sanity prompts of WP8, compared with a reference (the plain `--fit` cell at the same context). It runs in Stage 2 on each shortlisted candidate, and in Stage 3 on the tuned configs. This matters because there is one unconfirmed report of the expert cache producing degenerate output. Thresholds (declared before any real measurement): a prompt fails if its length is below min(100, half the reference length); if its distinct 4-gram ratio is below half the reference's; if its longest run of one repeated token is 16 or more while the reference's is below 16; or if some 8-gram repeats 8 or more times (non-overlapping) while the reference's maximum is below 8. A candidate passes if none of its 3 prompts fails. The index of the first divergence from the reference is reported for information only, because different placements and KV types can legitimately diverge.

### 5.7 Machine state during sweeps

- Monitors are on the iGPU, and machine tuning stays frozen.
- The browser, games and VMs are closed, and the PC stays on mains power.
- Every sweep is wrapped in `systemd-inhibit`, so the PC can't sleep mid-run.
- Only one GPU job runs at a time, enforced by a lock file.

---

## 6. Work packages

Each work package (WP) is sized for one Claude Code prompt in a fresh session. Before every prompt I state whether plan mode should be on and how long to expect it to run.

| WP | Title | Plan mode | Expected length | Depends on |
|---|---|---|---|---|
| WP0 | Repo bootstrap | off | short (~10 min) | G0 |
| WP1 | System inventory (read-only) | off | short (~10 min) | WP0 |
| WP2 | Python skeleton, config schema, launch script, CI | **on** | medium (~45 min) | WP0 (can run during G1) |
| — | **G1: Zack installs prerequisites, sets up the BIOS and moves the monitors** | — | — | WP1 |
| WP3 | Build llama.cpp | off | **long** (detached build, 15–40 min) | G1, WP2 |
| WP4 | Model download and verification | off | **long** (~22 GB download) | WP3 |
| WP5 | Server bring-up and endpoint health checks | **on** | medium (~45 min) | WP4 |
| WP6 | Telemetry, environment snapshot, microbenchmarks | off | medium (~45 min) | WP5 |
| WP7 | Harness setup and smoke tests | **on** | medium (~1 h) | WP5 |
| WP8 | Workloads | **on** | medium (~45 min) | WP5 |
| WP9 | Sweep runner | **on** | medium–long (~1–1.5 h, including a mini-sweep) | WP6, WP8 |
| WP10 | Analysis and report tooling | off | medium (~45 min) | WP9 |
| WP11 | Stage 1 screening sweep | off | **long** (overnight, 6–8 h) | WP10, G3 |
| WP12 | Stage 2 feature experiments | off | **long** (4–5 h) | WP11, G3 |
| WP13 | Stage 3 final run and Stage 4 reproducibility | off | **long** (~2 h, then ~30 min on another day) | WP12, G3 |
| WP14 | Release | off | medium (~1 h) | WP13, G2 |

### WP0: Repo bootstrap

**Goal:** create the umbrella repo with its conventions in place, so every later prompt can rely on them.

**Tasks:**
- Find the 256 GB SSD's mount point (read-only: `lsblk`, `findmnt`, `df`) and confirm it is not the 500 GB OS drive.
- Create `local-ai-research` there and run `git init -b main`. If the mount point isn't writable without `sudo`, stop and give Zack the exact command instead.
- Copy `project-plan.md` and the newest `step-0-baseline-v*.md` from `~/Downloads/local-ai-research/` to `docs/plans/project-plan.md` and `docs/plans/step-0-baseline.md`. The stable names keep references valid when the plan's version changes; the version is in the file header.
- Write:
  - `CLAUDE.md` (content in §12.3);
  - `docs/progress-log.md` and `docs/decisions.md`;
  - a stub `README.md`;
  - `LICENSE` (MIT) and `LICENSE-DATA.md` (a CC BY 4.0 notice covering `data/` and `reports/`);
  - `CHANGELOG.md` with an "Unreleased" section;
  - `.gitignore` covering `models/`, `third_party/`, `.venv/`, `data/cache/`, raw logs and harness state directories.
- Make the first commit.

**Acceptance:**
- `git log --oneline` shows the commit and `git status` is clean.
- The files match the list above.
- `CLAUDE.md` is at most 100 lines.
- `findmnt` output shows the repo is on the 256 GB SSD.
- Nothing was written outside the repo, apart from creating its directory.

### WP1: System inventory (read-only)

**Goal:** know exactly what is installed and what is missing, without changing anything.

**Tasks:** write `scripts/inventory.sh` (read-only, no `sudo`). It produces `data/env/inventory-<UTC date>.json` and `docs/environment.md`, covering:
- OS, kernel, CPU, RAM, swap/zram, transparent huge pages, memlock limit and `/dev/shm` size;
- disks: mount points and free space, confirming that the repo sits on the 256 GB SSD;
- GPU: driver, CUDA runtime, `nvcc` version and the gcc versions it supports as a host compiler, PCIe link, power limit, clocks, compute processes and any display clients on the dGPU;
- CPU frequency governor, energy-performance preference (EPP) and amd-pstate mode;
- tools: git, cmake, ninja, every installed gcc version, Python, uv, Node/npm, gh (with auth status) and curl;
- existing llama.cpp installs on PATH or as packages, recorded only and never touched;
- available hwmon sensors (k10temp for the CPU, nvme);
- a "missing prerequisites" table giving the exact commands Zack would run. These are written down, not executed.

**Acceptance:**
- The script contains no `sudo`.
- `git status` shows only the new files.
- The JSON parses.
- The report lists the gaps, or says "none".

### WP2: Python skeleton, config schema, launch script, CI

**Goal:** the code foundation that everything else plugs into.

**Tasks:**
- **Project files:** `pyproject.toml` (Python 3.12 or later; dependencies pydantic, httpx, numpy, gguf, matplotlib; dev dependencies pytest and ruff), `uv.lock`, and the package `src/smallpc/`.
- **Config schema** (pydantic) for:
  - `configs/machine.toml`: paths, port, GPU index, and manually recorded BIOS fields (EXPO, PBO/Eco mode);
  - `configs/model.toml`;
  - `configs/server/*.toml`: one file per server configuration, with a `profile` field marking it as stock, candidate or tuned;
  - sweep specs.
- **`smallpc.render`:** turns a server TOML into the llama-server argument list in a deterministic order. The stock profile emits only the agreed explicit flags.
- **`scripts/launch-server.sh <config>`:**
  - renders the arguments and runs llama-server by absolute path;
  - logs to `data/logs/<run-id>/` and writes a pidfile;
  - waits for `/health`, with a timeout;
  - refuses to start if the GPU lock is held or the port is busy;
  - `--dry-run` prints the argument list instead of starting.
- **`scripts/stop-server.sh`:** sends SIGINT, waits, falls back to SIGKILL after a timeout, and records the exit status.
- **`.github/workflows/ci.yml`:** `uv sync --frozen`, `ruff check`, `ruff format --check`, `pytest -m "not gpu"` and `shellcheck`.
- **Tests:**
  - golden argument lists for example configs (stock-64k, fit-64k-q8, cmoe-cache-64k, mtp-64k);
  - validation errors;
  - deterministic rendering.

**Acceptance:**
- Every CI command passes locally.
- `launch-server.sh --dry-run` prints the expected argument list for each example config.
- The stock example's argument list contains none of `-ctk`, `-ctv`, `-fa`, `-np`, `-b`, `-ub` or `--spec-type`.

### WP3: Build llama.cpp

**Goal:** a pinned, recorded CUDA build for compute capability 12.0.

**Tasks:**
- **`scripts/run-detached.sh`:** a generic long-job wrapper. It uses `setsid nohup`, writes a log file and a status file (start, end, exit code), and refuses to start a GPU job while the GPU lock is held.
- **`scripts/build-llama.sh`:**
  - clones into `third_party/llama.cpp` and checks out the newest release tag (b12017 or later);
  - configures with `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release`, plus an explicit `CMAKE_CUDA_COMPILER` and `CMAKE_CUDA_HOST_COMPILER` (a gcc version the installed CUDA supports, as found in WP1);
  - builds `llama-server`, `llama-bench` and `llama-cli` with at most 6 parallel jobs, because nvcc is memory-hungry;
  - writes `data/env/build-info.json`: tag, commit, flags, nvcc version, host compiler and build duration.
- Run the build detached and poll its status file.

**Acceptance:**
- `llama-server --version` matches the recorded commit.
- `--help` lists `--moe-cache-mib`, `--fit`, `--slot-save-path` and `--reasoning-budget`, with `draft-mtp` among the speculative types.
- `--list-devices` shows the RTX 5060 Ti.
- `build-info.json` is committed.

### WP4: Model download and verification

**Goal:** the right model file, provably.

**Tasks:**
- **Pick the revision.** Query the official repo's commit history. Choose the newest revision, dated on or after 2026-08-23, in which the Q4_K_M file changed, and record it.
- **Download.** Use a pinned `huggingface_hub` via `uvx` to download into `models/`. Record the size and SHA-256 in `configs/model.toml`, along with the repo, revision and license.
- **Model card and template.** Fetch the model card and the official chat template from the base repo at a pinned revision. Record the recommended sampling settings in `configs/model.toml`.
- **`smallpc.gguf_check`,** writing `data/health/model-check.json`:
  - **Metadata:** architecture, block count and `nextn_predict_layers`, and a chat template that is present and identical, after whitespace normalization, to the official one.
  - **MTP head layout:** in GGUF the head is the `blk.40.*` tensors. Record their names, shapes and count. This shows the head is present and complete. It cannot tell a trained head from a random one, because both have the same layout.
  - **Known broken-head signatures:** dequantize the head and screen it. Any one of these signatures is a FAIL:
    - non-finite values anywhere;
    - norm weights with a median outside [0.2, 5], or any value above 1e4 in magnitude. This catches both ~0.02 norms and the reported ~1e31/NaN garbage.
    - weight matrices that look freshly initialized: at least 90% of them with kurtosis within 3 ± 0.3 and a standard deviation within 0.015–0.025.
  - **Diagnostics, not thresholds:** kurtosis, standard deviation and max/σ for every matrix are reported next to `blk.39`, a trained trunk layer, for comparison. A PASS here means "no known failure signature". Only WP5's acceptance and equivalence tests prove the head actually works.
- **Load check.** Do a one-off load with `llama-server --check-tensors`.
- **Tests, with synthetic tensors:**
  - N(0, 0.02) → FAIL;
  - Student-t → PASS;
  - NaN or 1e31 norms → FAIL;
  - norms around 0.02 → FAIL;
  - mostly heavy-tailed matrices with a few near-Gaussian ones → PASS (no false rejection).

**Acceptance:**
- The verdict is PASS, with the stats table, template match and SHA-256 recorded.
- On FAIL, Claude Code stops and reports. The fallback download needs Zack's approval.
- Real draft acceptance is checked separately, in WP5.

### WP5: Server bring-up and endpoint health checks

**Goal:** prove that the pinned build does everything later steps rely on.

**Tasks:** write `smallpc.health` and `scripts/healthcheck.sh`. Run them against a 64K server started with `--fit`, 8-bit KV, `-fa on`, `-np 1`, `--metrics` and `--slot-save-path /dev/shm/<repo>-slots`. The checks are:
- **Basic endpoints:**
  - `/health`;
  - `/props`: n_ctx equals what was requested, the template hash matches WP4, and the model path is right.
- **Tokenizing and templates:**
  - `/tokenize` with `with_pieces`;
  - `/apply-template` with tools.
- **Completions and the prompt cache:**
  - `/completion` returns the timings fields (`prompt_n`, `cache_n`, `predicted_n` and their times);
  - a repeated prefix is reused (`cache_n` > 0);
  - `cache_prompt: false` gives `cache_n` = 0;
  - `n_probs` returns probabilities.
- **Thinking budget:** a per-request thinking budget is honoured while the global `--reasoning-budget` is unset.
- **Metrics:** `/metrics` responds.
- **Slots:** `/slots` save, then restore, then continue. The continuation must match a run that was never saved and restored (greedy decoding, near-tie rule).
- **MTP:**
  - draft lengths 1 and 2 with `-np 1` give `draft_n` > 0, and acceptance at length 1 is at least 50% on a code prompt;
  - with MTP and `-np 2`, record whether the server rejects it, since this matters for later steps;
  - greedy equivalence with MTP on and off, on 3 prompts × 256 tokens, with near-tie analysis (a divergence only counts as a near tie when the top-2 log-probability gap is below 0.5 nats).
- **MTP across save and restore** (llama.cpp #28619 concerns the draft context not being saved with slots):
  - With MTP on (`-np 1`, draft length 2), run a short two-turn conversation that stays below `--checkpoint-min-step`, so no context checkpoint can help. Record any checkpoints the log reports.
  - **Slot files:** save the slot, erase it, restore it, then send the third turn.
  - **Host-RAM prompt cache:** switch to another conversation and back, so the prompt cache does the restore. Step 5 chooses between these two mechanisms, so both are tested.
  - Compare each with an uninterrupted session:
    - `cache_n` on the third turn must show the restored prefix was used; otherwise the restore wasn't exercised and the test is repeated;
    - greedy tokens must match (near-tie rule);
    - draft acceptance on the third turn must be compared too. Matching output alone can't reveal a lost draft state, because the target model verifies every drafted token; a lost state shows up as lower acceptance.
  - A lost draft state is recorded as a finding for the executive chat, not as a Step 0 failure.
- **Expert-cache statistics:**
  - start with `-cmoe --moe-cache-mib 4096 -lv 4`, then shut down cleanly and confirm the statistics line is present and parses;
  - run a quick A/B (3 repetitions) to see whether `-lv 4` slows decoding. The result decides how hit rates are collected in the sweeps.
- **Fixtures and cleanup:** save scrubbed log excerpts as parser test fixtures, and remove everything from `/dev/shm` afterwards.

**Acceptance:**
- `data/health/endpoints-<date>.json` lists PASS or FAIL with evidence for each check, and every FAIL is explained.
- The MTP save/restore result is recorded for both mechanisms, with acceptance figures.
- The parsers pass on the fixtures.
- `/dev/shm` is clean.

### WP6: Telemetry, environment snapshot, microbenchmarks

**Goal:** every number traceable to the machine state that produced it, plus calibration data for Step 6.

**Tasks:**
- **`smallpc.envsnap`** records:
  - driver, CUDA and kernel versions;
  - CPU governor and EPP;
  - GPU power limit, clocks, PCIe link under load and temperatures;
  - other GPU processes and display clients;
  - `MemAvailable`, swap/zram use and transparent huge pages;
  - build info, model SHA-256, harness versions and the manually recorded BIOS fields.
- **`smallpc.telemetry`:** a 2 Hz sampler covering:
  - nvidia-smi, including clock event reasons;
  - hwmon CPU Tctl;
  - llama-server RSS and page faults from `/proc`.

  It also includes detectors for the §5.6 flags.
- **`smallpc.scrub`:** replaces the username, hostname and home paths before anything is published.
- **Microbenchmarks,** 5 repetitions each, with CIs:
  - PCIe host↔device transfers (`tools/pcie_bw.cu`, pinned and pageable memory, 1.8 MB, 16 MB and 256 MB transfers);
  - RAM bandwidth (STREAM, source pinned by hash, at 8 and 16 threads);
  - NVMe direct read of the model file (`dd iflag=direct`, which bypasses the page cache without sudo).
- **Expert size:** compute the exact per-expert size from the GGUF's expert tensors, replacing the project plan's ~1.8 MB estimate.
- **Tests:** parsers on fixtures, the flag detectors and scrubbing.

**Acceptance:**
- `data/microbench/*.json` is committed.
- The PCIe link shows Gen4 x8 under load.
- There is a 60-second sampler CSV from a live server.
- The tests pass.

### WP7: Harness setup and smoke tests

**Goal:** both harnesses pinned, isolated from Zack's own configs, and proven against the local server.

**Tasks:**
- **Install.** Check that Node is version 22 or later. Install exact versions into a local prefix, `third_party/node`:
  - `opencode-ai`, at the newest stable version at install time;
  - `@deepseek-ai/dsh`, at the version the `latest` dist-tag points to at install time;
  - dsh's required plugins, at that same exact version, because plugin dist-tags have been unreliable.

  Record all versions in `configs/harness.toml`.
- **Configs.** Render them from templates, reading the context window from `/props`:
  - **OpenCode,** via `OPENCODE_CONFIG`, with its state directory inside the repo (gitignored):
    - an `@ai-sdk/openai-compatible` provider with base URL and model id;
    - `limit.context` and `limit.output`;
    - `enabled_providers` set to the local provider only;
    - `autoupdate: false` and `share: "disabled"`;
    - everything else left at its default, since this is the stock harness.
  - **dsh,** via `DSH_HOME` inside the repo (gitignored): a custom provider with `api: openai-completions` and `contextWindow` from `/props`.
- **Toy task.** Create `tests/fixtures/toy-task` (MIT, written by us): a small Python module with one failing test.
- **OpenCode smoke test.** `scripts/smoke-opencode.sh` copies the toy task to a scratch directory under `/tmp`, runs `opencode run "<task>"`, and then runs pytest there. OpenCode's bash permission allows only pytest, ls and cat inside the scratch copy.
- **dsh smoke test.** Use a headless mode if one exists (check `dsh --help`). Otherwise, write a manual procedure for Zack to follow.
- **Request pattern.** From the server log, summarise the request pattern into `data/harness/request-pattern.json`: requests per turn, title or other auxiliary requests, and `prompt_n`, `cache_n` and `predicted_n`. Label it as smoke-task data: it shows how OpenCode behaves (for example, extra title requests), not what real agent turns look like (§3.4).

**Acceptance:**
- The OpenCode smoke test passes, with the tests green in the scratch copy.
- The dsh smoke test passes, or a manual procedure is documented and Zack runs it.
- All versions are pinned.
- `~/.config/opencode` and `~/.dsh` are untouched, shown by listings and modification times taken before and after.
- The request-pattern summary is committed.

### WP8: Workloads

**Goal:** the real, public prompt sets described in §5.2.

**Tasks:**
- Pick the two source repositories and record them, with their licenses.
- Write `smallpc.workloads`. It builds prompt variants for lengths {2K, 8K, 16K, 24K, 32K, 48K, 64K, 96K}, plus the append chunks, packed to exact token counts with `/tokenize`.
- Keep the manifest in `configs/workloads/`, and cache rendered prompts in a gitignored directory.
- Make Request B begin with Request A's exact token sequence.
- Give every fresh request its own nonce at the very start of the system message (§5.2).
- Handle BOS and special tokens explicitly. Read `add_bos_token` from the model metadata, and tokenize with matching `/tokenize` settings, with special tokens parsed.
- **Tests:** determinism (the same recipe gives the same hash), the manifest schema, and packing accuracy against a fake tokenizer.
- **Live checks:**
  - a token-array request and the equivalent string request give identical `prompt_n` and identical first 16 greedy tokens;
  - every Request B variant reaches 400 generated tokens with the model card's sampling; variants that stop early are replaced.

**Acceptance:**
- The manifest is committed.
- Regeneration reproduces every hash.
- Token counts are verified against `/tokenize`.
- Both live checks pass.

### WP9: Sweep runner

**Goal:** unattended, resumable, honest measurement.

**Tasks:**
- **`smallpc.sweep`** implements the §5.3 protocol for a sweep spec:
  - the measurement steps: preconditions, launch, health check, snapshot, telemetry, warm-up, the protocol itself, then a clean shutdown with log parsing (buffers, placement, cache statistics);
  - JSONL records, one per request, each carrying the config hash and an environment reference;
  - resuming by (config hash, workload, repetition);
  - recording "did not fit" cells;
  - the accounting and `cache_n` assertions for Requests A and B (§5.3);
  - max-fit probing and canary bracketing;
  - `systemd-inhibit` wrapping.
- **Scripts:** `scripts/run-sweep.sh` (which goes through `run-detached.sh`) and `scripts/sweep-status.sh`.
- **Mock server:** a mock llama-server for the CI tests.

**Acceptance:**
- The tests pass. They cover resume, failure paths, the record schema, and the `warm_prefill` and `cache_miss` flags; the mock server can return a non-zero `cache_n` to trigger them.
- A real mini-sweep (2 cells at 32K, 2 repetitions, about 15 minutes) completes.
- Killing and resuming the mini-sweep creates no duplicate records.

### WP10: Analysis and report tooling

**Goal:** numbers, CIs, plots and the selection rule, all reproducible from the raw data.

**Tasks:**
- **`smallpc.stats`:** the statistics in §5.5.
- **`smallpc.report`:** Markdown tables, a flags column, a coverage report, and SVG plots of:
  - prefill speed vs prompt length;
  - decode speed vs depth;
  - T_turn_400 (estimated) and T_B (measured, with `predicted_n`) per configuration;
  - VRAM breakdown per context;
  - hit rate vs cache size.
- **Selection:** implement the rule in §3.3 and a shortlist generator.
- **Tests:**
  - CI coverage on simulated data (about 95% ± 2%);
  - a golden report rendered from fixture JSONL.

**Acceptance:**
- The tests pass.
- The report renders from the mini-sweep data.

### WP11: Stage 1 screening

WP11 runs in several sessions: preparation and pre-flight, three sweep sessions (one per context, each started by Zack after G3), and an analysis session.

**Tasks:**
- Preparation: adopt the current plan version; write `configs/sweeps/stage1.toml` according to §5.4 (it must expand to exactly 57 cells); write a short pre-flight spec; write `docs/runbook-stage1.md` with the exact commands for the three sessions, the G3 checklist, how to monitor, and how to resume.
- Pre-flight on the GPU (short, not reported as results): one cell of each placement family, the max-fit probe at 32K and 128K, N_fit from P1's log, and the re-run mode on a copy of the mini-sweep data. Check in the first logs that `--fit` leaves explicit placements alone (P6–P9) and that P8 and P9 start at the intended placement.
- Sessions: for each context, Zack readies the machine (G3), and the session runs detached from a clean committed tree.
- Analysis, after each session or after all three: `report coverage` to confirm every cell is measured or recorded as did not fit; re-run flagged repetitions once with `--rerun-flagged`; produce the shortlist, the VRAM breakdowns, the hit rates and the swap sensitivity; update the progress log.

**Acceptance:**
- Coverage is complete (exit code 0) and all flags are resolved or listed as excluded diagnostics.
- The shortlist follows §3.3.
- Everything is committed.

### WP12: Stage 2 feature experiments

WP12 runs in several sessions: preparation and pre-flight (tools, specs, runbook, short GPU checks), the 2f session and its decision, the 2a to 2d sessions, and the sanity check, 2e and the analysis.

**Tasks:**
- Preparation: a tool that builds the Stage 2 specs from the Stage 1 shortlist, the 2f decision and the 2a result; a tool that applies the declared rules of §5.4 to session data; the runner for the output sanity check (§5.6, using `smallpc.sanity`); a wrapper for the llama-bench cross-check; the runbook; short GPU checks of every new code path.
- Sessions: each sub-stage as its own session from a clean committed tree. Anything that changes code or configs between sessions is committed first.
- Analysis: per sub-stage, with CIs, the swap sensitivity of §5.5 and the decision rules of §5.4.

**Acceptance:**
- Every Stage 2 cell is measured with 5 repetitions and CIs, or recorded as did not fit.
- The `--cache-ram` decision follows its declared rule and is recorded in `docs/decisions.md`.
- MTP's effect on decode and on prefill is quantified, and the MTP recommendation is recorded in `docs/decisions.md`.
- The sanity check has been run on the candidates that go forward.

### WP13: Final run and reproducibility

WP13 runs in several sessions: preparation (no quiet machine needed), the three Stage 3 sessions and their analysis (quiet machine), and Stage 4 on another day (quiet machine).

**Tasks:**
- Preparation: write `configs/server/{stock,tuned}-{32k,64k,128k}.toml` from the Stage 2 outcome; write the Stage 3 and Stage 4 specs from those files; fix the VRAM-breakdown parser, which counts an MTP cell's compute buffers twice; write the tool that produces the Stage 3 headline tables under the rules of §5.4; write the runbook; a short functional check of the new paths.
- Stage 3: three sessions, one re-run pass each, the sanity check on the tuned config files, then the analysis with the label "results".
- Stage 4 on another day, then the S2 check.
- Walk through the README launch steps from a clean shell.

**Acceptance:** S1–S4 are met, with evidence, or each deviation is recorded with its reason.

### WP14: Release

**Tasks:**
- Write the README (contents in §9) and the `CHANGELOG.md` entry for v0.1.0.
- Write the final report, `reports/baseline-report.md`, and the write-up draft, `reports/writeup.md`.
- Run the scrub check over `data/` and `reports/`.
- Push to the private GitHub repo and confirm CI is green (`gh run watch`).
- Tag v0.1.0 and push the tag. Zack then publishes the release.

**Acceptance:** the §9 checklist is complete, with evidence.

---

## 7. Things only Zack can do

| Gate | When | What Zack does |
|---|---|---|
| **G0** | Before WP0 | Save the project plan and this plan as `~/Downloads/local-ai-research/project-plan.md` and `~/Downloads/local-ai-research/step-0-baseline-v1.2.md`. Open a fresh terminal and start Claude Code from your home directory. If WP0 reports that the SSD needs `sudo` for the repo directory, run the command it gives you. |
| **G1** | After WP1 | Run the proposed sudo commands for any missing prerequisites. In the BIOS, enable the integrated graphics and note the EXPO and PBO/Eco-mode settings. Move both monitors to the motherboard outputs and reboot. Then tell me; WP1's script is re-run to confirm there are no display clients on the RTX 5060 Ti. |
| **G2** | Before WP14 | Run `gh auth login` if that isn't done yet, and confirm that Claude Code may create and push to the private repo. |
| **G3** | Before each long run | Close the browser, games and VMs, keep the PC on mains power, and OK the start. Stages 1 and 2 ran with desktop apps open and idle, as a recorded deviation. Stages 3 and 4 produce the headline results, so G3 applies in full there. |
| **G4** | After WP14 | Make the repo public and publish the release. File any upstream issue drafts. |
| — | Only if WP4 fails | Approve the fallback model download. |

**Money:** none expected. **Accounts:** GitHub only; Hugging Face isn't needed for public models.

---

## 8. Deliverables and repository layout

Deliverables: the config files and launch script required by the project plan, plus everything below.

```
<repo>/
├── README.md, LICENSE (MIT), LICENSE-DATA.md (CC BY 4.0), CHANGELOG.md, CLAUDE.md
├── pyproject.toml, uv.lock
├── .github/workflows/ci.yml
├── docs/
│   ├── plans/project-plan.md, plans/step-0-baseline.md
│   ├── progress-log.md, decisions.md
│   ├── environment.md          # hardware, BIOS, OS, drivers (scrubbed)
│   └── methodology.md          # §5 in prose, for readers of the release
├── configs/
│   ├── machine.toml            # paths, port, GPU, manual BIOS fields
│   ├── model.toml              # repo, revision, SHA-256, sampling defaults
│   ├── harness.toml            # pinned OpenCode/dsh versions
│   ├── server/                 # stock-*.toml, tuned-*.toml, examples
│   ├── sweeps/                 # stage1.toml, stage2*.toml, stage3.toml, stage4.toml
│   ├── workloads/              # recipes + manifest
│   └── harness/                # OpenCode / dsh config templates
├── scripts/                    # inventory, build-llama, launch-server, stop-server,
│                               # healthcheck, run-detached, run-sweep, sweep-status,
│                               # smoke-opencode (+ dsh procedure)
├── src/smallpc/                # config, render, gguf_check, health, envsnap, telemetry,
│                               # scrub, workloads, sweep, stats, report
├── tools/                      # pcie_bw.cu, STREAM (pinned)
├── tests/                      # unit tests, fixtures, mock server, toy-task
├── data/                       # committed: raw/*.jsonl, env/, health/, microbench/,
│                               # harness/, logs/ (compressed, scrubbed)
├── reports/                    # baseline-report.md, figures/, writeup.md
├── models/                     # gitignored
└── third_party/                # gitignored: llama.cpp build, node prefix, harness state
```

---

## 9. Release checklist (lighter standard agreed for Step 0)

- [ ] v0.1.0 is tagged in the umbrella repo, with a matching `CHANGELOG.md` entry.
- [ ] The README covers:
  - what this is and the hardware it was measured on;
  - quick start: prerequisites, build, download and verify, launch stock or tuned;
  - how to rerun the sweep on your own 12–16 GB machine (via `machine.toml`);
  - a results summary with CIs;
  - limitations and licenses.
- [ ] The stock and tuned configs for 32K, 64K and 128K are included, along with the launch script.
- [ ] The sweep and analysis scripts are documented and parameterised, without extra packaging.
- [ ] Unit tests pass locally, and CI (lint and unit tests, no GPU) is green on GitHub.
- [ ] Raw JSONL, environment snapshots, microbenchmarks, health results and the baseline report with 95% CIs are included, along with the exact commands.
- [ ] Provenance is recorded: llama.cpp tag, commit and build flags; model repo, revision and SHA-256; OpenCode and dsh versions.
- [ ] Data is scrubbed (no username, hostname or home paths). Prompts are published only as recipes that point to the public sources.
- [ ] The write-up draft is reviewed (GitHub only). It covers the problem, approach, results and what didn't work.
- [ ] `LICENSE` (MIT) and `LICENSE-DATA.md` (CC BY 4.0) are present.
- [ ] Any upstream bugs found are written up as issue drafts with evidence, for Zack to file.
- [ ] The progress log is complete, and the step completion report has been delivered to the executive chat.

---

## 10. Risks

| # | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| 1 | The official GGUF still carries a bad or stripped MTP head | low / high | WP4 tensor check and WP5 acceptance test; fallback file only with approval |
| 2 | CUDA and gcc version mismatch on Arch | medium / medium | Explicit host compiler; WP1 identifies a supported gcc; Zack installs it at G1 |
| 3 | A regression in llama.cpp at the chosen tag | medium / medium | Pinned tag; WP5 catches it; step back one release tag if needed, recorded in decisions |
| 4 | MTP limits: single slot, slower prefill, greedy mismatches | medium / medium | Measured in WP5 and Stage 2a; MTP joins the tuned configs only if it wins on T_turn_400 and passes the equivalence check |
| 5 | The expert cache produces degenerate output | low / high | Output sanity check; such configs are excluded; upstream issue draft |
| 6 | RAM pressure: 32 GB of RAM with a 22 GB memory-mapped model | medium / high | Idle preconditions, paging flag and the load-mode experiment; mlock only as a later, approved option |
| 7 | Heat soak or drift during long sessions | medium / medium | Telemetry, thermal flags, canaries and re-runs |
| 8 | Background noise from the desktop | medium / low | Idle checks, display on the iGPU, repetitions and CIs |
| 9 | Trace logging (`-lv 4`) slows runs down | medium / low | WP5 A/B test decides; hit rates are collected in separate short runs if needed |
| 10 | Claude Code's 10-minute limit on Bash calls | certain / low | All long jobs run detached, with status files |
| 11 | dsh breaks (developer preview) or has no headless mode | medium / medium | Exact version pins; manual procedure; project decision point 4 (fall back to OpenCode) |
| 12 | OpenCode's extra title request disturbs the prompt cache | likely / low | Recorded as stock behaviour; material for Step 2 |
| 13 | Personal information ends up in published data | medium / medium | Scrub module plus a release check |
| 14 | The executor model changes (Opus 5.5 → GLM 5.3) | possible / medium | Self-contained prompts; review based on evidence, not claims |
| 15 | Upstream changes mid-step | likely / low | Everything pinned; upstream re-checked at the end of the step and noted in the completion report |

---

## 11. Confirmed decisions (6 Nov 2026)

1. **Repo:** `ZHarvett/local-ai-research`, on the 256 GB SSD (exact path found in WP0), with `models/` inside it (gitignored).
2. **LICENSE copyright holder:** ZHarvett.
3. **Selection rule and turn workload:** §3.3 approved, with the 3,000 + 400 turn of §3.4 as a standardised benchmark workload, not a model of real agent use. `predicted_n` is recorded for every run, and the estimated 400-token turn (T_turn_400) is kept separate from measured times (T_B).

---

## 12. Working protocol with Claude Code

### 12.1 Prompt header

Every message from me that contains a prompt starts with one line, for example:
**Plan mode: ON · Expected: long (~6 h, runs detached overnight)**

The prompt follows in a single `~~~` block. If plan mode is ON, Zack sends me Claude Code's plan before approving it.

### 12.2 Prompt rules

- One WP per prompt, started in a fresh Claude Code session (`/clear`). WP0 runs from the home directory; every later session starts from inside the repo.
- Every prompt is self-contained. It names the WP, points to the relevant section of `docs/plans/step-0-baseline.md`, lists the acceptance criteria, and requires the standard report.
- Corrective prompts follow the same rules.

### 12.3 CLAUDE.md contents (written in WP0; kept short)

- **Project:** a one-paragraph summary, and where the plans live.
- **Hard rules:**
  - never use sudo or change system configuration; propose the commands instead;
  - never delete or modify anything outside the repo, except scratch directories in `/tmp` and `/dev/shm/<repo>-*`;
  - never modify existing installs, services, `~/.config/opencode` or `~/.dsh`;
  - no downloads over 1 GB beyond those in the step plan without approval;
  - only one GPU job at a time, enforced by the lock;
  - anything that may take longer than about 8 minutes runs via `scripts/run-detached.sh`.
- **Conventions:**
  - uv, ruff, pytest (`-m "not gpu"` in CI) and shellcheck;
  - TOML configs;
  - llama-server is started only through `scripts/launch-server.sh`, with absolute paths and an explicit port;
  - `data/raw/` is never edited by hand.
- **Measurement rules:**
  - no random-token numbers for cache or MTP results;
  - a snapshot, warm-up and telemetry for every measured run;
  - report raw evidence, not adjectives.
- **Privacy:** public data only, and scrub before publishing.
- **Workflow:**
  - start by reading the WP's section of the step plan and the latest progress-log entry;
  - at the end of each WP, commit and append a progress-log entry;
  - finish with the standard report.
- **Compaction:** when compacting, keep the WP id, the acceptance criteria, the modified files and the commands run.

### 12.4 Standard report (the end of every prompt)

1. A summary of what was done.
2. Each acceptance criterion marked PASS or FAIL, with evidence.
3. Files changed (`git diff --stat <start>..HEAD`).
4. The commands that were run, with verbatim excerpts of their key output (tests, benchmarks).
5. Anything that couldn't be done, was uncertain, or deviated from the plan.
6. Suggested next steps.
7. The commit hash, and confirmation that the progress-log entry was added.

### 12.5 Progress-log entry format

Each entry records the date, WP, status, commit, key results (with numbers) and open issues.

---

## 13. Notes for the executive chat

- **MTP and parallel slots.** WP5 found that MTP works with `-np 2` on the pinned build: both slots draft, and the context is split between them. The "second server slot" designs in Steps 4 and 5 are therefore not blocked by MTP.
- **Control harness.** OpenCode was chosen; the project plan text still says "OpenCode or Claude Code".
- **Sweep tooling.** Expert-cache and MTP results come from llama-server with real prompts, not llama-bench, because random-token benchmarks distort MoE routing. llama-bench is kept as a cross-check.
- **Estimates to be replaced.** The plan's per-token KV size and per-expert size estimates will be replaced with measured values in WP6 and WP11. Any material difference will be reported.
- **Release.** Step 0's release follows the lighter standard agreed earlier: a tagged baseline release in the umbrella repo.
- **MTP state across save and restore.** On the pinned build, neither `/slots` save/restore nor the host-RAM prompt cache lost the MTP draft state (identical draft counts at 181 and 3,191 tokens of history, and the log shows the draft state saved and restored). There was no negative control and no history above 8,192 tokens. llama.cpp #28619 (a Step 3b starter PR that Step 5 depends on) may already be fixed, and Step 3b and Step 5 should confirm it.
- **Memory behaviour on this machine.** The system uses zram swap with `vm.swappiness` 150, and the kernel swaps cold pages of llama-server's memory even with about 20 GiB available. Step 1 benchmark runs on this PC will see the same behaviour. Step 0 flags only major page faults, and reports swap activity separately.
- **MTP draft length 2.** On the pinned build, draft length 2 gives a deterministic repeated phrase on one of three sanity prompts, on four configurations. Draft length 1 is bit-identical to MTP off, and draft length 3 passes. It is unresolved whether this is a fault in the speculative path or a threshold artifact. Step 3b and Step 7 should look at it before relying on draft lengths above 1.
- **What moved the numbers in Stage 2.** The larger batch (`-b 4096 -ub 4096`) more than doubles prefill speed over the default. Keeping all experts on the CPU side with a large VRAM expert cache (P6) beat `--fit` in every context. FP16 KV beat 8-bit KV at 64K and 128K. MTP helped by about 2 to 5% per turn (4.6% at 32K with draft length 2, an excluded configuration, and 2.4% at 64K with draft length 1) and not at all at 128K, because it costs 9 to 16% of prefill speed and 0.75 to 1.5 GiB of expert-cache VRAM.
- **Unexplained VRAM residual.** After the parser fix, the VRAM not accounted for by logged buffers is 512 to 532 MiB for MTP cells and 337 to 363 MiB without MTP, at every context size. The 170 MiB difference is not a compute buffer in the log and was not attributed.
- **Host prompt cache on a 32 GB machine.** With the default `--cache-ram` of 8,192 MiB, a long-running server's host prompt cache plus a 20 GiB memory-mapped model pushed the machine into paging at 128K and 64K in Stage 1. Stage 2f measures smaller values. Step 1 and Step 5 should expect the same effect, and Step 5's plan to park states in host RAM competes for the same memory.
- **Real agent turns.** Step 0's 3,000 + 400 turn is a standardised workload. Step 1 should report per-turn new tokens and generated tokens from real tasks, to show how far real use is from it.

---

## 14. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 6 Nov 2026 | Initial plan |
| 1.8 | 12 Nov 2026 | After WP13 part 1: three figures corrected against the data (1 flagged window of 80 not 100; MTP helped 2 to 5% not 3 to 5%; MTP costs 9 to 16% of prefill and 0.75 to 1.5 GiB of VRAM); the Stage 3 time estimate is 1.5 hours with up to 2.5 hours worst case; the Stage 3 gate command and the quiet-machine check are written into the Stage 3 rules (§5.4); the unexplained VRAM residual is noted for the executive chat (§13) |
| 1.7 | 11 Nov 2026 | After Stage 2: the Stage 2 outcome, its human decisions and its deviations are recorded, including 2c and 2d not run and draft length 2 excluded by the sanity check (§5.4); Stage 3 and Stage 4 are written out with their rules declared before measurement, including how stock's paging is reported and when the headline may use all units (§5.4); WP13 is split into preparation, sessions and Stage 4 (WP13); G3 applies in full to Stages 3 and 4 (§7); two notes for the executive chat (§13) |
| 1.6 | 10 Nov 2026 | After Stage 1: Stage 2 is written out with its decision rules declared before measurement (§5.4); a new first sub-stage, 2f, tests the host prompt cache size, because the paging seen in the 64K and 128K sessions tracked its growth; the Stage 2 estimate rises to 6 to 7 hours; WP12 is split into preparation, sessions and analysis (§5.4, WP12); a note on host-memory pressure for the executive chat (§13) |
| 1.5 | 9 Nov 2026 | After the WP11 pre-flight: the max-fit definition for P6 and P7 states that `--fit` keeps its default margin, which is the binding limit on this card (§5.4); the Stage 1 time estimate drops to about 4 to 5 hours, because the larger batch settings prefill 2.3 to 2.9 times faster than the default (§5.4); the pre-flight is recorded as done, and its probe cache retired (§5.4) |
| 1.4 | 9 Nov 2026 | Lessons from WP9–WP10: the paging flag counts only llama-server major faults, with swap growth recorded as `swap_activity` and a swap sensitivity added to every report (§5.5, §5.6); paired-ratio intervals become the wider of bootstrap and t on log ratios, and the measured coverage of the intervals is stated (§5.5); eligibility and the tie-break are written as WP10 implemented them, with the literal step 2 that could never apply removed, and screening applies no tie-break (§3.3); the output sanity check gets declared thresholds and a stage (§5.6, WP12); transient precondition failures are retried (§5.3); Stage 1 runs as three sessions with shuffled cell order, a recomputed time estimate of about 8 h, a clean-tree rule and a pre-flight (§5.4, WP11); a note on memory behaviour for the executive chat (§13) |
| 1.3 | 9 Nov 2026 | Lessons from WP5–WP8: the idle precondition uses CPU busy time instead of the lagging load average, with a recorded wait (§5.3); the paging flag counts only llama-server's own faults and swap, since system-wide zram swap-in never reaches zero (§5.6); a new `accounting` flag and `prompt_n + cache_n` assertions for Requests A and B, and Request A's one generated token documented (§5.3, §5.6, WP9); every cell runs with `-lv 4`, and hit rates are decode-batch only (§5.4); the canary is defined, with fresh nonces (§5.1, §5.2); K = 1,024, the variant policy r mod 5 and the special-token exclusion recorded (§5.2); the MTP notes updated with WP5's findings (§13) |
| 1.2 | 6 Nov 2026 | Zack's review: MTP draft state tested across slot save/restore and the host-RAM prompt cache (WP5, §13); the 3,000 + 400 turn is a standardised workload, and the smoke task's request pattern is no longer used to revise it (§3.4, WP7); T_turn renamed T_turn_400 and labelled an estimate, with measured T_B and `predicted_n` recorded, a `short_gen` flag, and a WP8 check that outputs reach 400 tokens (§5.3, §5.6, WP8, WP10); confirmed repo name, licence holder and WP0 setup (§4, §7, §11, WP0) |
| 1.1 | 6 Nov 2026 | After external review: stock cells keep their §3.1 settings in every stage (§5.4, WP2); every fresh request gets its own nonce, plus `cache_n` assertions and a new `warm_prefill` flag (§5.2, §5.3, §5.6, WP8, WP9); explicit BOS/special-token handling for token arrays (§5.2, WP8); the MTP tensor check now screens for known broken-head signatures, with proof left to WP5's functional tests (S4, WP4); S4 and §5.6 agree on how flagged results are reported |
