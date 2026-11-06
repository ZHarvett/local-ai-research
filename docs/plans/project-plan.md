# Local AI on a Small PC: Project Plan

*Last updated: 5 November 2026*

## 1. Goal

Make local agentic coding fast and capable on an ordinary gaming PC, and release the tools as open source. The work should be useful to other people with 12–16 GB GPUs, contribute to upstream projects (llama.cpp, DeepSeek Harness and others), and produce measured results suitable for a portfolio.

**Success means** a clear before/after result on our coding benchmark (Step 1). Compared with a stock local setup, the finished system should complete more coding tasks, in less wall-clock time, at whatever context size proves best on this hardware. Every claim in this project is backed by measurements, not impressions.

## 2. Releasing as we go

Every main deliverable is released publicly, on its own, as soon as it is finished and measured, rather than waiting for the whole project. Each release meets a high standard:

- **Standalone and usable:** its own repository (or an upstream pull request, for engine work), with a clear install path, a permissive open-source license, and a tagged, versioned release with a changelog.
- **Well documented:** a README explaining the problem it solves, how it works, how to install, configure and use it, and its known limitations.
- **Backed by evidence:** results from the Step 1 benchmark, with confidence intervals, plus the exact hardware, configuration, commands and raw data needed to reproduce them. Nothing is claimed that hasn't been measured.
- **Tested:** automated tests (and continuous integration where practical) that pass before every release.
- **Written up:** a public write-up (post and/or video) covering the problem, the approach, the results, and what didn't work.
- **Good upstream citizenship:** contributions to llama.cpp, dsh and other projects follow each project's contribution guidelines, start from an issue or discussion where appropriate, and include benchmark evidence.

Exceptions: the benchmark's locked test set and any personal-repo tasks stay private, and routing traces are published only from public tasks. A step isn't finished until its release is out.

## 3. Starting point

### Hardware

RTX 5060 Ti 16 GB (running at PCIe 4.0 x8; an identical card measured about 14.3 GB/s), Ryzen 7 9700X (Zen 5, AVX-512), 32 GB DDR5-6000 with EXPO enabled, NVMe SSD, CachyOS Linux.

### Base model: Ornith-1.5-35B-A3B

A fine-tune of the Qwen3.5/3.6 architecture. Its self-reported scores beat Qwen3.6-35B-A3B by a wide margin: SWE-bench Verified 79.0 vs 73.4, Terminal-Bench 2.1 67.8 vs 52.5. These are vendor numbers; Step 1 checks them on our own tasks.

| Property | Value |
|---|---|
| Layers | 40 (30 Gated DeltaNet + 10 full attention) |
| Experts | 256 per layer; 8 routed + 1 shared active per token |
| Active parameters | about 3B per token |
| License | MIT |
| Size at Q4 | about 21 GB (does not fit in VRAM alone; experts spill to RAM) |
| Expert size at Q4 | about 1.8 MB each (about 550 experts per GB of VRAM) |
| KV cache | about 20 KB per token at FP16, about 10 KB at 8-bit |

Use the **officially retrained MTP head**. The head originally shipped with the model was effectively random, and older GGUF files may still contain it.

### Engines

- **llama.cpp**, build b11560 or newer. This includes the merged MoE expert cache (`--moe-cache-mib`) and `/slots` save/restore that now works on hybrid models.
- **Strata** (the engine built for Qwen3.8-Flash-Next) is **shelved for now**. With 32 GB of RAM only Flash-Next's pruned Coder variant runs, in a slow low-RAM mode, and a RAM upgrade isn't planned. See decision point 2.

### Harness

- **DeepSeek Harness (dsh)** as the research testbed, pinned to a specific version, because everything in it is a plugin.
- **OpenCode or Claude Code** as the control setup for comparisons.

### Context window: a measured variable, not a fixed number

64K is the starting assumption, not a commitment. The best window depends on three trade-offs we can only settle by measuring:

1. **Larger windows cost VRAM.** At 8-bit KV, every 64K tokens of context costs about 0.65 GB, roughly 360 fewer cached experts.
2. **Longer prompts are slower to read** whenever they aren't cached, and model quality tends to drop as the context fills.
3. **Smaller windows force more compaction and handoffs.**

Qwen's guidance for this model family recommends at least 128K of context. We treat that as one candidate to test, not a requirement: a bigger window gives the model more room, but doesn't by itself make it reason better.

| Context | KV cache at 8-bit | Expert slots given up |
|---|---|---|
| 32K | about 0.33 GB | about 180 |
| 64K | about 0.65 GB | about 360 |
| 128K | about 1.3 GB | about 720 |
| 262K (model maximum) | about 2.7 GB | about 1,450 |

Step 0 and Step 1 test 32K, 64K and 128K, and the default is set from the results. Every tool reads the actual window from the server (llama-server's `/props` endpoint) instead of hard-coding a number.

### Facts that shape this plan

1. **Prompt processing (prefill) is the bottleneck, not generation.** Before measurement, estimates are roughly 1,500–3,000 tokens/s for prefill with large batches, versus roughly 40–55 tokens/s for generation. Agents send large prompts, so time-to-first-token dominates long sessions.
2. **Hybrid models are fragile with prompt caching.** The DeltaNet layers' state cannot be rewound. Any change early in the prompt forces a re-read from the last saved checkpoint, or from scratch.
3. **The harness matters most when context is tight.** In one study, better management of old tool output raised fully solved tasks from 43 to 72 (out of 169) at a 20,480-token window, while wide-window results barely differed. Local hardware pushes us toward that tight regime.
4. **Upstream moves fast.** Before starting each step, re-check llama.cpp, ik_llama.cpp and dsh for new work, so we build on it rather than duplicate it.

## 4. Working principles

1. **Measure everything, with honest statistics.** Every change is scored on the benchmark (Step 1) on task success rate and wall-clock time. Agent benchmarks are noisy (one study found run-to-run variation about as large as a model upgrade), so:
   - **During development,** 1–3 runs on a small dev set are enough to see which direction a change moves things.
   - **For reported results,** setups are compared as *paired* runs on the same tasks, at least 5 runs each, with 95% confidence intervals (bootstrapped over tasks), not just averages.
   - **A locked test set** is never used while building or tuning tools, so the tools can't end up tuned to the very benchmark that is supposed to prove they work.
   - **Fixed seeds** are used where the engine supports them, but GPU arithmetic isn't perfectly deterministic, so repeated runs are still needed.
2. **Keep harness tools engine-agnostic.** The proxy, debloater, orchestrator and skill plugin only use standard OpenAI/Anthropic-compatible APIs. Token counting uses the engine's `/tokenize` endpoint as the authoritative source. Where an engine doesn't offer one, a local copy of the model's tokenizer is used only after it has been checked against `/tokenize` on a representative test set; any disagreement is reported, never silently ignored.
3. **Build on upstream instead of forking.** Engine improvements go to llama.cpp as pull requests.
4. **Be cache-safe by default.** Never rewrite conversation history. Compress tool output only when it first enters the context. Inject instructions at fixed positions. Keep the orchestrator's history append-only.
5. **Use public data only for traces.** MoE routing traces can reconstruct most of the original text, so published traces must come from public repos and prompts.
6. **Ship small.** Each step should be useful on its own and released to the standard in section 2 before moving on.
7. **Define each step's success metric before building it.** Every step, especially the experimental engine work, must have an independently measurable result, so we know whether it worked before moving on.

## 5. The plan, in order

### Step 0: Baseline setup

**What.** Get a working, documented starting configuration and its numbers.

**How.**

1. **Build the engine.** Compile llama.cpp b11560 or newer from source with CUDA for this card (compute capability 12.0).
2. **Get the model.** Download Ornith-35B-A3B at Q4 with the retrained MTP head. Check the file date or model card so the old random head isn't used.
3. **Free up resources.** Move the monitors to the motherboard's display output (frees VRAM) and confirm EXPO is active (CPU-side expert speed depends on RAM speed).
4. **Run `llama-bench` / `llama-server` sweeps** over:
   - plain `--n-cpu-moe N` offload versus `--moe-cache-mib` cache sizes;
   - 8-bit KV (`-ctk q8_0 -ctv q8_0 -fa on`);
   - prefill batch sizes (`-b`/`-ub` 2048 and 4096);
   - contexts of 32K, 64K and 128K;
   - MTP off versus `--spec-type draft-mtp` with draft lengths 1–3.
5. **Record:** prefill speed at several prompt lengths, generation speed, VRAM and RAM use, and acceptance rates for speculative drafts.
6. **Install the rest:** a pinned dsh version configured as a custom provider pointing at llama-server, and the control harness.

**Output.** A configuration file, a launch script, and a baseline numbers table in the project repo.

### Step 1: The benchmark

**Problem.** Models and settings are usually chosen by gut feel or public benchmarks that don't match real work, so there's no reliable way to tell whether a change helps.

**Design: three tiers of tasks.**

| Tier | Source | What it gives us | Limitations |
|---|---|---|---|
| **A. Public, fresh** | A fixed subset of **SWE-rebench**, using only monthly task splits created after Ornith's release (19 Aug 2026), so the model cannot have trained on them | Results comparable with a public leaderboard; pre-built Docker images per task; credible for write-ups | Python only; real tasks take minutes each locally, so we use a subset, not all 860 |
| **B. Targeted synthetic** | Tasks generated with a frontier model (Claude Opus 5.5 in Claude Code) inside **real open-source repos with real test suites**, using SWE-smith-style methods: introduce a realistic bug, or remove a feature that the repo's own tests check, then write the issue text | Tasks aimed at what our tools change; covers Rust/TypeScript as well as Python | Generator bias and test quality must be controlled (see validation below) |
| **C. Personal (optional)** | A small set from the user's own repos, where tests exist | A sanity check that improvements carry over to real personal work | Small and uneven, so never the main signal |

**Tier B task categories,** each aimed at one of our tools:

| Category | What it tests | Which step it measures |
|---|---|---|
| Oversized | Deliberately larger than the context window | Step 5 (orchestrator) |
| Noisy tools | Huge build/test logs where only a few lines matter | Step 4 (debloater) |
| Long sessions | Many turns, many tool calls | Step 2 (cache doctor) |
| Edit-heavy | Rewriting large existing files | Step 7a (suffix decoding) |

**Validation for every synthetic task.** A task is only admitted if:
1. its tests fail on the starting code;
2. they pass with the reference solution;
3. they give the same result over 3 reruns (no flaky tests);
4. the reference solution does not appear in the task text.

About 10% of tasks are checked by hand. Using the repo's existing tests wherever possible avoids trusting the generator's own tests.

**The runner.**
1. **Isolation:** each task runs in its own container.
2. **Execution:** the runner drives the harness under test (dsh or the control) against the engine.
3. **Metrics:** it records success (the tests pass), wall-clock time, prefill versus generation time, tokens in and out, and prompt-cache reuse. Cache reuse comes from the server's `timings` fields: `prompt_n`, `cache_n`, `predicted_n`.
4. **Storage:** results go to JSONL with the full configuration.
5. **Reporting:** paired comparisons with 95% confidence intervals, as described in the working principles.

It can sweep model × quantization × engine flags × context size × harness × our tools. Tasks are split into three sets:
- **Dev set:** small, used constantly while building tools.
- **Milestone set:** larger, used for reported progress results.
- **Locked set:** drawn from Tiers A and B, never looked at during development, and run only for final comparisons.

Milestone and locked runs take hours (minutes per task, times several runs), so they run overnight. We first check whether the Harbor framework (which can already run SWE-rebench) can drive dsh. If it can't, writing a dsh adapter for Harbor is itself a useful contribution.

**Goal.** This is the scoreboard for the whole project. It decides the best configuration and context size for this PC, and whether new models (e.g. Qwen4-27B) are better.

### Step 2: Prefix-cache doctor + correctness check

**Problem.** When anything changes early in an agent's prompt, a hybrid model has to re-read the whole conversation. Common causes:
- chat template differences;
- timestamps or attribution headers;
- reasoning stripped from earlier turns;
- reordered tool definitions.

The waste is enormous: one llama.cpp issue reports about 8 minutes per turn on a 15K-token chat. Cache-miss diagnosers exist for cloud APIs, but nothing works at the token level for llama-server. There is also a correctness risk: one engine build's hybrid checkpoint restore leaked part of another conversation into a reply.

**What we build:** a proxy on localhost. The harness points at the proxy, and the proxy forwards requests (including streaming) to the engine.

**How.**

1. **Render the exact prompt.** For each request, turn the messages, including tool definitions and any template options, into the exact prompt string the engine will see, using llama-server's `/apply-template` endpoint.
2. **Tokenize it** with `/tokenize` (with `with_pieces` on, so each token maps back to its text). Keep the token array for each conversation.
3. **Check the rendering is faithful.** After the engine responds, the rendered token count must equal what the engine actually processed (`timings.prompt_n` + `timings.cache_n`). A mismatch means the rendering is missing something, such as tool definitions or a template option, and is flagged, because every later diagnosis depends on it.
4. **Find the first difference.** Compute the longest common prefix with the previous request in the same conversation, map the first differing token back to the message and field it came from, and classify the cause with clear rule IDs. Example rules: template changed, timestamp or UUID detected, reasoning removed, tool schema reordered (compared as normalized JSON), system prompt edited.
5. **Separate harness misses from engine misses.** Compare the expected reuse with what the engine reports (`timings.cache_n`):
   - if the engine reused about as much as the common prefix, the miss came from the harness;
   - if it reused much less, the engine had no usable checkpoint near the divergence point, and a **checkpoint advisor** recommends values for `--ctx-checkpoints`, `--checkpoint-min-step` and `--cache-ram` based on where divergences actually happen.
6. **Normalize (optional).** Order tools deterministically, move volatile lines to the end, and keep reasoning handling consistent. Every rewrite is logged.
7. **Run the correctness check.** After cache restores, and every N requests, generate the first K output tokens twice with identical settings (temperature 0, fixed seed): once using the cache, and once from a genuinely fresh context (`cache_prompt: false`). Compare the generated token IDs and their probabilities (`n_probs` reports probabilities for generated tokens, not prompt tokens). Small probability differences are expected, because cached and fresh runs split the computation differently. A different chosen token, or a probability gap beyond a set tolerance, raises an alert.
8. **Test for cross-conversation leaks.** A dedicated test runs two conversations, A and B, each containing unique "canary" facts. It saves and restores their states and interleaves their requests, then checks that neither conversation ever reveals, or is influenced by, the other's canaries. This targets exactly the bug class already seen in a hybrid checkpoint restore.
9. **Report:** a live log plus a session report (cache reuse %, wasted prefill seconds, top causes).

**Goal.** Every cache miss it catches turns a re-read of tens of thousands of tokens (tens of seconds to minutes here) into a few seconds. On agent workloads this is likely the single largest wall-clock improvement in the plan. Reproducible bug reports and a possible upstream improvement (checkpoints placed at message boundaries) are bonus outputs.

#### Step 2b: Thinking-budget mode (inside the same proxy)

**Problem.** Reasoning models think at length even on routine steps. At about 50 tokens/s, 5,000 thinking tokens is 100 seconds of waiting.

**How.**
1. **Estimate how much thinking each turn needs.** Turn type alone isn't enough: a tool result containing a complicated compiler error can need more thinking than a user asking to rename a variable. So the estimate starts from several simple signals:
   - whether the turn is a new request or a tool result;
   - whether the tool result contains errors or test failures;
   - how large and unusual the output is;
   - how much context is left.
2. **Set a per-request thinking budget** from that estimate. llama.cpp's server accepts a per-request budget when its global `--reasoning-budget` is unset. The budget is a request parameter, not prompt text, so the cached prefix is untouched.
3. **Escalate when a budget proves too small.** If the next turn shows the same failure again, or the model hits its budget partway through a hard problem, the budget is raised for the next attempt.
4. **Stop repetitive thinking.** Watch the streamed reasoning for repetition (repeated sentences or n-grams) and end thinking early with a budget-forcing message when it starts looping.
5. **Check quality.** Compare task success with and without budgets, since some tasks genuinely need long thinking.

**Goal.** Fewer wasted thinking tokens and minutes saved per task, with no loss in success rate.

### Step 3: Quick wins

#### 3a. A Ponytail-style skill for dsh and open-weight models

**Problem.** Models over-build: extra abstractions, unrequested features, padding. Locally, every output token costs real time.

**How.**
1. **Research exactly how Ponytail works:**
   - its rules and decision "ladder";
   - its intensity levels;
   - how its plugin injects the active mode before every turn (a skill left for the model to trigger on its own rarely activated in an independent test);
   - its review/audit skills;
   - how its benchmark is built.
2. **Rebuild it as a dsh plugin** based on that design. Inject the rules at a fixed position every turn so the prompt cache isn't broken, and tune the wording for open-weight models: shorter, more explicit, with examples.
3. **Measure it on the benchmark:** lines of code, wall-clock time, success rate, and whether validation and error handling survive.

**Prior art.** Ponytail supports Claude Code, Codex, OpenCode and several other hosts, but not dsh. Its headline numbers are from Claude models. An independent JetBrains test (80 tasks) found 15% less code and 10.3% lower cost, with no detectable quality loss.

**Goal.** Less unnecessary output per task, so tasks finish faster, without lower quality.

#### 3b. Starter upstream contributions

These are for learning the codebases and building a track record:
- **llama.cpp #28619:** slot save/restore doesn't keep the MTP draft context. Step 5 depends on this.
- **moe-expert-grading fork:** upstream its CPU repack fix for expert tensors.

### Step 4: Evidence-linked, cache-safe context debloater

**Problem.** Tool output stays in the context word for word, and models don't trim it. In a tight window, a few large logs force lossy compaction, and every extra token costs prefill time. Many compression tools exist (Compressor Reflex, sqz, context-mode, Headroom and others). None of them ties its summaries to checkable evidence, and some rewrite history, which breaks prompt caches.

**What we build:** an MCP server exposing `run_and_ask(command, question)`.

**How.**
1. **Run and save.** Run the command, save the full output with line numbers to a log file, and count its tokens with the tokenizer.
2. **Clean deterministically:**
   - strip colour codes and carriage-return progress bars;
   - collapse repeated lines ("[repeated 312×]");
   - pull out errors from known formats (pytest, cargo, tsc, npm).
3. **Return small outputs unchanged.** Below a token threshold, return the cleaned output as is.
4. **Ask a summarizer model about large outputs.** Send the question plus the numbered output (in chunks if needed). The model must reply in JSON as a list of short claims, **each with its own supporting line numbers and exact quoted lines**. A claim without evidence is dropped.
5. **Check every quote** by exact string match against the saved log, and drop claims whose quotes fail. If too little survives, fall back to the first and last lines plus a grep for error patterns.
6. **Optionally check that the evidence supports the claim.** A quote can be real while the explanation built on it is wrong, for example quoting a genuine error but misdiagnosing its cause. An optional second pass asks whether each claim actually follows from its quoted lines. Because it costs an extra model call, it is run as an experiment and kept only if it improves task success enough to pay for its time.
7. **Return** the claims with their quoted evidence, the log path, and stats. The agent always sees the evidence lines, not just the summary, and the full log stays available as the source of truth.
8. **Redact secrets** (keys, tokens, `KEY=value` pairs, high-entropy strings) before anything is sent to a cloud service.
9. **Compress only on the way in.** Output is compressed only when it first enters the context. Earlier messages are never edited.

**Summarizer model.** Local by default, so nothing leaves the PC. Two candidate setups: a small model on the CPU, or a second llama-server slot on the main model, though that competes with the main model for the GPU. For testing, we also plan to try a free or very inexpensive cloud model. Groq's free tier is one example (as of late October 2026, about 8K tokens per minute on its larger models), but the provider and model will be researched and decided when we reach this step.

**Goal.** Fewer tokens in context, less prefill time, and likely better answers in a tight window, with every summary claim linked to checkable evidence. The output is an *evidence-linked* summary, not a fully verified one. It will be measured on tokens saved, prefill seconds saved, quote-check pass rate, claim-support rate, and task success.

### Step 5: Orchestrator + subagents with tree memory

**Problem.** A limited context window can't hold a big task. A single agent either compacts repeatedly, losing information, or fails.

**What we build.** An "orchestrate" mode, implemented as a dsh plugin (dsh already supports subagents with per-subagent presets). It triggers automatically when a task's estimated size exceeds the context budget.

**How.**

1. **Measure exact token costs.** The orchestrator has a `measure(paths)` tool that returns the token count of each file from the engine's `/tokenize` endpoint, or from a local tokenizer that has passed the consistency check in the working principles. Counts are cached by file hash.
   - **Brief size:** each draft brief is rendered through `/apply-template` and tokenized, so its exact size is known.
   - **Window size:** read from `/props`.
2. **Budget each subtask** with explicit arithmetic: a subtask's files + brief + expected tool output + thinking allowance must fit within about 50–60% of the window, after subtracting the shared system prompt. Work is split along natural seams (module, function, test), with interfaces written first.
3. **Brief each subagent tightly.** A subagent starts with a fresh context containing the goal, the relevant files and interfaces, the constraints, and a "done" test. The system prompt and tool list are identical across all agents, so that cached prefix is reused.
4. **Hand off early.** The plugin tracks each subagent's context use from the server's `timings`. At about 80% full, it tells the subagent to write a handoff note (done, remaining, current state) and return. The orchestrator then splits the remainder.
5. **Verify, don't trust.** After each subtask the orchestrator runs the tests, reads `git diff --stat`, and runs linters, rather than believing reports.
6. **Park the orchestrator's state** while a subagent runs, then restore it. Two options are measured against each other:
   - **Slot files:** start llama-server with `--slot-save-path`, save via `POST /slots/{id}?action=save` and restore via `?action=restore`. This writes the state to files, so the path should point at a RAM-backed filesystem (tmpfs, e.g. `/dev/shm`) for RAM speed.
   - **Host-RAM prompt cache:** rely on llama-server's automatic `--cache-ram` cache to keep and restore the orchestrator's prompt.

   Either way, the orchestrator's history stays append-only so the restore is cheap, and Step 2's correctness and leak tests guard against a bad restore.

   **MTP caveat:** slot save/restore doesn't yet keep the MTP draft context (llama.cpp #28619, which Step 3b aims to fix). We don't assume a fix will be merged in time. Instead we measure how much draft acceptance drops after a restore, and if it hurts, orchestrator turns run without MTP until a fix lands.
7. **Keep durable memory.**
   - **Files:** the plan, decisions and progress are kept in files, so the orchestrator itself can be restarted.
   - **Conversation:** an OptChat summary tree (Victor Taelin's design: recent turns verbatim, older turns as progressively coarser one-line summaries, with "zoom" to expand any line back to the original). We adapt an existing local llama.cpp implementation, abdou-rgd/optchat, which already does cache-aware lazy compaction, runs its summarizer in a second server slot, and uses grammar-constrained summaries.
   - **Fitting it in:** the view is shrunk to fit our window, and compaction runs in batches so the prompt stays stable between compactions.

**Goal.** Complete tasks larger than the context window. Each handoff costs roughly 30–60 seconds, mostly the orchestrator writing the next brief (Step 2b's budgets reduce this). On large tasks we expect similar or better total time than a single agent with compaction, and a higher success rate. It will be measured on the oversized tasks from Step 1: orchestrated versus single agent.

### Step 6: Routing-trace logger + cache simulator + public dataset

**Problem.** llama.cpp now has an expert cache, but nobody knows which caching policy works best for agentic coding at a given VRAM budget. Caching also nearly breaks down for multi-token batches: one tester measured about 85–95% hit rates when processing up to 8 tokens at a time, but only about 18% on larger batches, which is exactly what speculative decoding produces.

**How.**

1. **Capture traces.** For every layer, log which experts were chosen for each token, plus the batch size and whether it was prefill or generation. Use the `--moe-cache-audit` JSONL format from llama.cpp PR #30594 if it has merged. Otherwise, hook the router's top-k selection using llama.cpp's graph evaluation callback (the mechanism `llama-eval-callback` and imatrix use).
2. **Record sessions.** Run Tier A and public Tier B benchmark tasks through dsh with Ornith.
3. **Build the simulator.** Replay each layer's expert requests through caching policies at cache sizes expressed in expert slots (about 1.8 MB per expert at Q4). Cache sizes are based on the VRAM actually left over after the non-expert weights, KV cache and compute buffers at each tested context size (roughly 4–10 GB on this 16 GB card), not on the card's total. Policies to compare:
   - SLRU, the policy llama.cpp's cache actually ships with (a probationary and a protected segment);
   - plain LRU;
   - profile pre-filling;
   - LFU;
   - a static coding profile plus an adaptive region;
   - verification-aware admission.
4. **Report and predict.** For each batch-size category (single tokens, small speculative batches, prefill), report the hit rate, the fraction of layers where all 8 experts were cached, and the bytes moved over PCIe or computed on the CPU. A cost model calibrated on Step 0's numbers turns these into predicted tokens/s.
5. **Validate against reality.** Hit rate alone doesn't determine speed: the cost of a miss depends on transfer size, PCIe contention, CPU work, batch size, and whether transfers overlap with computation. So for each policy and batch-size category, predicted speed is reported next to speed measured in real runs with `--moe-cache-mib`. A simulated improvement is never reported as a speed-up until real runs confirm it.
6. **Publish** the traces from public tasks with a privacy note, plus the simulator.

**Goal.** Data-driven cache settings for this PC, a public dataset, and the evidence base for the engine pull requests in Step 7. This is the original "expert caching" idea, redirected to where it adds new value now that a basic cache has been merged.

### Step 7: Engine contributions

#### 7a. Suffix decoding in mainline llama.cpp

**Problem.** Coding agents copy a lot of existing text (rewriting files, repeating code). Suffix decoding exploits this to draft many tokens cheaply, and its paper reports large speedups on agentic benchmarks. ik_llama.cpp has it; mainline llama.cpp does not.

**How.** Port ik_llama.cpp's suffix-tree drafter into mainline's speculative-decoding framework (`common/speculative`) as a new `--spec-type`. Benchmark it on edit-heavy tasks, alone and combined with MTP.

#### 7b. Expert cache that works during speculative decoding

**Problem.** MTP and suffix drafting verify several tokens at once, which touches more distinct experts than a single token. The current cache is bypassed or ineffective on these batches.

**How.** Use Step 6's simulator to design an admission rule for verification batches (for example, admitting experts used by the drafted tokens, or reserving slots), then implement it as a pull request against llama.cpp's MoE cache.

#### 7c. Faster prefill over narrow PCIe

**Problem.** During prompt processing, experts kept in RAM are streamed across the PCIe x8 link.

**How.** Use a larger batch and whole-layer expert placement during prefill only (the "UBBoost" idea, which claims up to 2x in its proposal), then switch back to the expert cache for generation.

**Goal.** Faster generation on edit-heavy turns (7a, 7b) and a shorter time-to-first-token (7c), contributed upstream so everyone benefits.

### Step 8: Stretch goals

- **Per-expert mixed precision.** Keep heavily used experts at higher precision and rarely used ones at lower precision. A fork (moe-expert-grading) already splits each layer into hot/warm/cold tiers stored with different quant types. We would evaluate it on real coding tasks rather than only perplexity, and compare tiers built from coding traces (Step 6) against generic calibration data, since a coding-specific profile may hurt other tasks. The prize is better quality per GB, or fitting a bigger model.
- **Model upgrades.** Evaluate Qwen4-27B when released, and any new model in this size class.

## 6. Decision points

1. **When Qwen4-27B weights are released:** run it through the benchmark within a day. It is a dense model, about 16–17 GB at Q4, so it will partly spill to RAM at long contexts. Switch base models only if it clearly wins on our tasks.
2. **Qwen3.8-Flash-Next and Strata (shelved):** revisit only if the PC gets 64 GB of RAM, a future model in that family runs well in 32 GB, or Strata turns out to run Ornith (it already supports the closely related Qwen3.6-35B-A3B) faster than llama.cpp.
3. **Context size and cache settings:** set from Step 0, Step 1 and Step 6 data, not guesses.
4. **If dsh's breaking changes block progress:** pin an older version or fall back to the control harness. The harness tools are engine- and harness-agnostic by design.

## 7. Summary

| Step | Work | Depends on | Main benefit |
|---|---|---|---|
| 0 | Baseline setup | — | Fixed, documented starting point |
| 1 | Three-tier benchmark | 0 | Measures everything |
| 2 | Prefix-cache doctor + correctness check | 1 | Removes unnecessary prompt re-reading (biggest time win) |
| 2b | Thinking-budget mode | 2 | Less waiting on routine turns |
| 3 | Ponytail-style dsh skill + starter PRs | 1 | Less unnecessary output; upstream track record |
| 4 | Evidence-linked debloater | 1, 2 | Leaner context, faster prefill, summaries tied to evidence |
| 5 | Orchestrator + tree memory | 1, 2, 3b, 4 | Tasks larger than the context window |
| 6 | Trace simulator + dataset | 1 | Best cache policy; public dataset |
| 7 | Engine PRs (suffix, cache, prefill) | 6 | Faster generation and time-to-first-token |
| 8 | Stretch goals | 6, 7 | Quality per GB; bigger models |

## 8. Ideas considered and dropped

These were researched and set aside. They are recorded here so they don't get re-investigated.

- **Qwen3.8-Flash-Next via Strata (shelved, not dropped).** With 32 GB of RAM only the pruned Coder variant runs, in a slow low-RAM mode, and a RAM upgrade isn't planned. Revisit under decision point 2.
- **Writing our own MoE expert cache.** llama.cpp merged one (`--moe-cache-mib`), and ik_llama.cpp and Strata have their own. We build on these instead (Steps 6–7).
- **Building our own engine to beat Strata on Qwen3.8-Flash-Next.** Strata already implements the same ideas, tuned for that model. Use it and contribute to it instead.
- **Running Flash-Next at true Q4 (needs about 96 GB of RAM).** IQ3_S matches the full model on Strata's published tests and is faster; not worth the extra RAM.
- **A static, coding-only expert profile on its own.** Evidence shows adaptive caching wins, so static profiles are only tested as one part of a hybrid policy in the simulator.
- **Adding an Engram-style n-gram lookup table to an existing model.** The table is learned during pretraining and can't be bolted on. Only a possible learning experiment with tiny models.
- **"GPU unlock" firmware mods.** They don't support RTX 50-series cards, and only speed up prefill.
- **TensorRT-LLM and NInfer.** Both need the whole model in VRAM, and NInfer officially targets the RTX 5090. Our models must offload experts to RAM.
- **"Thinking in numbers" (latent reasoning, "neuralese").** It requires specially trained models and isn't available in open models. The practical substitute is Step 2b's thinking budgets.
- **Using only the personal git history as the benchmark.** Too few well-tested tasks, so it is kept only as optional Tier C.
- **A standalone thinking-budget tool.** Folded into the Step 2 proxy.

---

## Appendix A: Research notes

Background that explains the choices above. All facts are as of early November 2026; re-check before relying on them.

**Models**
- **Ornith-1.5-35B-A3B** (DeepReinforce/ornith-ai) was released 19 Aug 2026 under the MIT license. Its scores are self-reported, averaged over five runs.
  - **Chat template:** Ornith adjusted the Qwen chat template to match how the model was trained, so use the template shipped with Ornith.
  - **Relation to Qwen3.6:** its language model differs from Qwen3.6-35B-A3B's by only about 0.2–1%, which is why Qwen3.6 tools and MTP heads transfer to it.
  - **MTP head history:** the shipped head was random. Community fixes appeared first (shisa-ai's head reached about 69% acceptance on code), then the official retrained head. Older GGUFs, including some popular re-uploads, carried the bad head.
- **Other Ornith releases:** Ornith-1.5-122B-A10B (20–21 Oct) has 3× the active parameters, so it is much slower with offload and only realistic with 64 GB+ of RAM. Tiel-Coder-35B-A3B is a re-quantization of Ornith, not a new model.
- **Qwen3.8-Flash-Next (shelved; notes kept for reference):** 125B total and 6B active parameters, plus a 51.2B-parameter n-gram embedding table (DeepSeek Engram-style). The table's addresses depend only on the input tokens, so it can live on the SSD and be prefetched. RAM needed with Strata:

  | RAM | What runs |
  |---|---|
  | 32 GB | Coder only (low-RAM mode) |
  | 48 GB | Q2_0, IQ2_XS |
  | 64 GB | All native sizes (IQ3_S is tight) |
  | about 88 GB+ | Unsloth Q4 fully in RAM |

  On Strata's numbers, IQ3_S agrees with the near-lossless 8-bit model's top token 87.7% of the time, against 93.1% for Q4. The "Swift 1.5" fine-tune thinks much shorter at similar quality.
- **Qwen4:** the lineup (Max, Flash, Plus, 27B) was shown on 29 Oct, but there were no weights as of early November. Qwen3.8-Flash-Next was described as a preview of the Qwen4 architecture.
- **Self-reported benchmarks:** treat them with caution. On fresh, decontaminated tasks (SWE-rebench), several models score noticeably lower than on older static benchmarks.

**Engines and upstream status**
- **Merged in llama.cpp:**
  - #29887, the MoE GPU expert cache (`--moe-cache-mib`). It uses an SLRU replacement policy and only handles batches of up to 32 tokens; the author measured 1.57–2.20× faster generation on Flash-Next.
  - #30112, multi-GPU support for that cache.
  - #26004, which keeps context checkpoints across `/slots` save/restore.
- **Open in llama.cpp:**
  - #30594: profile pre-filling, CPU computing cache misses, and the `--moe-cache-audit` trace output.
  - #30664: shared prompt prefixes across sessions.
  - #23262: "UBBoost" prefill.
  - #26448: zero-copy reads of experts from host RAM.
  - #20697: checkpoints saved to disk.
  - #28619: draft context not saved with slots.
  - #22384: checkpoint restore for hybrid models.
- **ik_llama.cpp:** has its own expert cache, a `suffix` speculative type, and chained drafters.
- **Strata techniques:**
  - CPU and GPU compute experts concurrently;
  - experts are pinned in RAM;
  - the next layer's experts are prefetched;
  - MTP and DFlash2 drafting;
  - the n-gram table lives on the SSD;
  - a calibrate mode tunes settings per PC;
  - an "effort at end" prompt layout keeps the cached prefix stable.

  Version 0.2.10 (2 Nov) made DFlash2 the default drafter. Since 0.1.45, Strata also runs Qwen3.6-35B-A3B with several concurrent requests.
- **Speculative decoding with offloading:** one study on an RTX 3090 found no llama.cpp speculative mode faster than baseline on Qwen3.6-35B-A3B. With all experts resident (on a Strix Halo machine), MTP plus n-gram drafting gave +73%.
- **Correctness hazard:** a hybrid checkpoint rollback bug leaked another conversation into a reply (ik_llama.cpp #2433, llama.cpp #27148). This is why Step 2 includes a correctness check.

**Harness research**
- **"Same Model, Different Harness"** (arXiv 2608.26218): shortening older tool results and reacting to stalled work raised fully solved tasks from 43 to 72 of 169 at a 20,480-token window. Wide-window Qwen3.6 results were close.
- **"Identical Runs, Different Results"** (arXiv 2609.33812): run-to-run noise in agent benchmarks is about as large as a model upgrade.
- **Harness swaps alone matter less for Ornith:** its scores with Terminus-2 and Claude Code differ by under a point. Context management is where harness gains come from.
- **OpenCode overhead:** a system prompt of about 9–15K tokens, 20–25K tokens per orchestrator turn, and the skill list sent twice.
- **dsh:** MIT, released 13 Aug 2026, everything is a plugin. v0.2.1-rc.2 added AGENTS.md, compaction in minimal mode, and per-subagent presets. v0.2.2-alpha added experimental delegation to other CLIs and a Claude Code compatibility layer. Still a developer preview.

**Context, memory and debloating**
- **Debloater competitors:** Compressor Reflex MCP, sqz-mcp, context-mode, Headroom, token-optimizer-mcp, Open330/context-compress. Paritok-4B is an extractive compressor; its "share of identifiers found in the input" metric (96.2% on SWE-bench Lite) is a good fidelity metric for Step 4.
- **Anthropic's context editing** invalidates the cached prompt prefix when it clears content, which is exactly the cost Step 4 avoids by compressing only on the way in.
- **OptChat implementations:** Hermes, Pi, OMP, Claude Code, and a local llama.cpp version (abdou-rgd/optchat).
  - The default view is 64–128 KB per turn, about 16–32K tokens, so it must shrink for us.
  - One audit found 4 invented causes in 42 summary lines; zoom is the safety net.
- **Groq free tier** (late October 2026): about 30 requests/min, 1,000 requests/day, 8K tokens/min and 200K tokens/day for its larger models. Cached tokens don't count toward the limits.

**Benchmarks**
- **SWE-rebench:** a continuously updated, decontaminated benchmark built from fresh GitHub tasks. Its leaderboard split has 860 curated Python tasks with pre-built Docker images and new monthly splits. It can be run through the Harbor framework, and V2 is language-agnostic.
- **SWE-smith:** generates tasks inside real repos by breaking existing tests. SWE-Gym, R2E and SWE-Bench++ are related task generators.

**MoE routing**
- **Privacy:** routing traces alone let a decoder recover about 91% of the original tokens (arXiv 2602.04105).
- **Not all models suit expert offloading** (arXiv 2505.16056): shared experts can reduce routing locality.
- **Static versus adaptive caching:** a static hot list learned on half of a workload covered only about 10% of the other half, and generic profiles covered about a third of a live session's hits. Adaptive caching wins.
- **Per-expert mixed precision:** the moe-expert-grading fork reached a perplexity of 1.5030 at 17.26 GiB on Qwen3.6-35B-A3B. The Colla-Q paper warns that expert usage frequency reflects the calibration data's domain.

## Appendix B: llama-server endpoints we rely on

Verify these against the current llama.cpp server documentation when building, since the API changes over time.

| Endpoint / field | Used for |
|---|---|
| `POST /tokenize` (`with_pieces`) | Authoritative token counts; mapping tokens back to text (Steps 2, 4, 5) |
| `POST /apply-template` | Rendering chat messages (with tools) into the prompt string; checked against `timings.prompt_n` + `cache_n` (Steps 2, 5) |
| `GET /props` | Reading the context size and chat template (all harness tools) |
| `POST /slots/{id}?action=save` / `restore` (needs `--slot-save-path`) | Parking and restoring the orchestrator's state as files; put the path on tmpfs for RAM speed (Step 5) |
| `--cache-ram`, `--ctx-checkpoints`, `--checkpoint-min-step` | Host-RAM prompt cache and hybrid-model checkpoints (Steps 2, 5) |
| Response `timings`: `prompt_n`, `cache_n`, `predicted_n` and their times | Measuring cache reuse and prefill vs generation time (Steps 1, 2, 5) |
| Request `cache_prompt: false`, `n_probs` (probabilities of generated tokens) | Correctness check: comparing generated tokens from cached vs fresh contexts (Step 2) |
| Per-request thinking budget | Thinking-budget mode (Step 2b) |
| `--metrics` (`/metrics`) | Prometheus metrics for long runs (Step 1) |

If an engine doesn't expose `/tokenize`, the tools fall back to a local copy of the model's tokenizer and chat template, but only after checking it against llama-server's `/tokenize` on a representative test set. Any disagreement is reported, never ignored.
