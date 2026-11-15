# Methodology

<!-- sources: docs/plans/step-0-baseline.md, docs/decisions.md -->

This document explains, in prose, how the Step 0 baseline was measured. It follows §5 of the
step plan (`docs/plans/step-0-baseline.md`, v1.9), which remains the authoritative statement
of every rule; where this text and the plan differ, the plan wins. The results themselves are
in `reports/baseline-report.md`, and the human decisions taken along the way are in
`docs/decisions.md`.

## What counts as a measurement

The authoritative speed numbers come from llama-server's own response `timings`, not from
client wall-clock time (which is recorded alongside them). Every number in the report was
produced by a real server answering real prompts: llama-bench builds its prompts from random
token IDs, which distorts MoE routing — whole groups of experts go unused — and therefore
distorts expert-cache hit rates and draft acceptance. llama-bench appears once, as a clearly
labelled cross-check (Stage 2e), and never feeds a decision.

Every server start gets a warm-up, every run records an environment snapshot and continuous
telemetry (2 Hz), and every long session is bracketed by canary measurements at its start and
end so that drift and heat soak cannot hide inside a session. The canary is a fixed
configuration named in the sweep spec, measured with 3 repetitions; its requests use
repetition indices from 100 upward with fresh nonces, so the end canary cannot be served from
a cache warmed by the session itself.

Nothing is left implicit: every llama-server argument that matters is either set explicitly or
deliberately left at its default, and the effective values are captured from `/props` and the
startup log. An explicit port is always set (the server's default port is 9931, which is never
relied on).

## The workload

Prompts are built from two permissively licensed public repositories at pinned commits — one
Python, one Rust or TypeScript. A prompt variant is a system prompt, then real source files
packed to an exact token length (counted with the server's `/tokenize` endpoint), then an
instruction that asks for code, all following the model's chat template. There are 5 variants
per length; repetition r uses variant r mod 5. K = 1,024 tokens throughout, so the 96K depth
is 98,304 tokens.

Every fresh request starts with its own unique nonce at the very beginning of the system
message. A per-repetition nonce would not be enough: prompts for different depths of the same
variant share their opening files, so a longer prompt could otherwise reuse a shorter one's
cached prefix, and the host-RAM prompt cache could match across requests. The nonce makes
every fresh prefill genuinely fresh.

The standardised turn is a 3,000-token append of tool-output-like text (a test log or file
listing from the same repos) plus an instruction, on top of an existing conversation prefix.
Request B must begin with Request A's exact token sequence, so token arrays are sent to
`/completion` rather than strings. BOS and special-token handling is explicit: llama-server
adds BOS only to string prompts, so the runner reads the model's `add_bos_token` metadata,
tokenizes with matching settings, and checks that a token-array request matches the equivalent
string request. Repository text containing any of the model's special-token strings is
excluded, because such text would silently become control tokens. Only the recipes (repo,
commit, file list, instruction, token count, SHA-256 of the rendered text) are committed; the
prompts themselves regenerate deterministically.

## The per-cell protocol

One server configuration is one *cell*. Before a cell runs, the runner checks that the GPU
lock is free, no other GPU compute processes are running, no display clients are on the dGPU
(warning only), `MemAvailable` is at least 24 GiB (warn) and 20 GiB (abort), and the CPU is
idle — busy time below 10% averaged over 10 seconds, from `/proc/stat`. The 1-minute load
average is recorded but is not the gate, because it lags for minutes after a heavy run. A
failed idle check is re-checked every 10 seconds for up to 10 minutes; transient failures are
retried up to 3 more times with a 10-minute pause, and every attempt and wait is recorded.
Hard conditions (another job holds the lock, a foreign GPU process, a busy port, a missing
binary) abort at once, and the session stays resumable.

The server then starts (load time, startup log and effective settings recorded), an
environment snapshot is taken, telemetry starts, and 2 warm-up requests (8K-token prompt, 128
generated tokens) are sent and discarded. Each repetition runs a fresh 2K-token short point
(up to 400 generated tokens) and then, for each depth d of the context in shuffled order
(fixed seed):

- **Request A** — a fresh prompt of length d with `n_predict: 0`, evaluated into the cache.
  The runner asserts `prompt_n + cache_n` = d and `cache_n` ≤ 32 (only the template's fixed
  opening tokens may match); a larger `cache_n` raises the `warm_prefill` flag.
- **Request B** — the same tokens plus the 3,000-token append, with up to 400 generated
  tokens. The runner asserts `prompt_n + cache_n` = d + 3,000 and `cache_n` ≥ 0.95·d, raising
  the `cache_miss` flag otherwise.

The depths are {8K, 16K, 24K} at 32K context, {16K, 32K, 48K} at 64K, and {32K, 64K, 96K} at
128K. The cell ends with a clean SIGINT shutdown, and buffer sizes, placement decisions and
expert-cache statistics are parsed from the log. Sampling uses the model card's recommended
parameters with a fixed seed per request; thinking stays at the template default (recorded);
greedy decoding is used only in the equivalence and sanity checks.

## The metrics

Per depth, the report gives: **PP_fresh**, the prefill speed of Request A; **PP_inc**, the
prefill speed of Request B (about 3,000 new tokens on a cached prefix of d); **TG**, the
generated-token speed of Request B; **T_reread**, d / PP_fresh, the cost of a full cache miss
at that depth; and **TTFT**, the client-side time to the first streamed token of B.

The headline turn metric, **T_turn_400**, is an *estimate* of the standardised turn: an ideal
cache hit (the new tokens are a pure append) followed by exactly 400 generated tokens —
Request B's prefill time plus 400 times its per-generated-token time. Because `n_predict` is
only a maximum and the model may stop earlier, the actually measured time of Request B
(**T_B**) is always reported beside it, with the actual `predicted_n`. MTP cells also report
acceptance (`draft_n_accepted / draft_n`), and every cell reports VRAM after warm-up and at
peak, server RSS, and major page faults and swap activity per measured window.

## The sweep stages

Candidate cells share sweep defaults — 8-bit KV, flash attention on, one slot, an explicit
port — unless a stage says otherwise. **Stock cells keep exactly the §3.1 settings in every
stage** (FP16 KV, flash attention auto, default slot count, `-b 2048 -ub 512`, no speculative
decoding), so tuned configurations are always compared against genuine stock. Every cell runs
with `-lv 4`: logging only, with no measured speed cost, which yields the placement trace,
buffer sizes and expert-cache statistics (hit rates for decode-sized batches only).

- **Stage 1 — screening** (2 repetitions): nine placement families (plain `--fit`, a tighter
  fit target, three VRAM expert-cache sizes, two max-fit `-cmoe` caches found by binary
  search, and two `--n-cpu-moe` layer counts) at each context and batch setting, plus stock —
  57 cells, run as three sessions with shuffled cell order and their own canaries. Output: a
  shortlist of the top 2 eligible placements per context.
- **Stage 2 — features** (5 repetitions): the host prompt-cache size (`--cache-ram`) is
  chosen first, because Stage 1's paging tracked its growth; then MTP draft lengths 1–3, KV
  type, and (where applicable) load mode and threads; then the output sanity check and the
  labelled llama-bench cross-check. Every decision rule was declared before its data existed.
- **Stage 3 — final** (5 repetitions, paired): stock against tuned for each context, on a
  quiet machine (gate G3 in full: desktop apps closed), one session per context with canaries
  and one re-run pass for flagged windows. The headline rule, declared before measurement:
  the clean-units comparison if both cells have at least 5 clean paired units after the re-run
  pass; otherwise the all-units comparison, labelled "includes paging-flagged stock windows",
  with the clean-units figures beside it and a recorded deviation.
- **Stage 4 — reproducibility** (a different day): stock-64K and tuned-64K again, checked
  against Stage 3 with the S2 criteria on T_turn_400, fresh prefill and decode at 32K depth.
  Its rules R1–R4 were declared on 12 November 2026, before any Stage 4 data (plan §5.4);
  run 1 was later excluded because the GPU's PCIe link ran below its verified state, and
  run 2 is the S2 run (decisions D1–D9 and rules R5–R7 in `docs/decisions.md` and the plan).

## Statistics

Per cell and metric the report gives the mean, n, min and max, and a 95% interval: a
percentile-bootstrap CI over repetitions (10,000 resamples, fixed seed) and a t-interval, of
which the **wider** is reported — at n = 5 the bootstrap alone comes out too narrow. Paired
comparisons (tuned vs stock, MTP vs no MTP) compute per-repetition ratios on the same
variants, take the geometric mean, and report the wider of a percentile-bootstrap CI and a
t-interval on the log ratios, back-transformed.

The intervals' coverage was simulated before use (20,000 experiments per case): the reported
interval — always the t-interval — covered about 95% for symmetric data at n = 5 and n = 10,
91–92% for strongly skewed data (lognormal σ 0.5) and 88–90% for exponential data. Step-0
timings are close to symmetric in the canaries, but a repetition slowed by background activity
is exactly the heavy-tailed case, which is why the flag rules matter.

Every results table and paired comparison is also computed with the units excluded whose
window shows llama-server swap growth of more than 64 MiB (the swap sensitivity). If a
headline comparison changes sign or an interval changes materially, the report says so.
Screening results (2 repetitions) are used only for shortlisting and appear in a clearly
labelled appendix, never as results.

## Flags and the output sanity check

A measured window is flagged when: a GPU thermal or hardware slowdown reason is active in
more than 1% of samples, or CPU Tctl reaches 95 °C in more than 1% of samples (**thermal**);
llama-server has more than 1,000 major page faults in the window (**paging** — swap growth is
recorded separately as `swap_activity`, not flagged, because this machine's zram swap with
`vm.swappiness` 150 swaps cold pages even with about 20 GiB available, and canary windows
with hundreds of MiB of growth were not slower); the session's start and end canaries differ
by more than max(their 95% CI, 5%) (**drift**); Request B generates fewer than 100 tokens
(**short_gen**); a fresh request reports `cache_n` > 32 (**warm_prefill**); Request B is
served with `cache_n` < 0.95·d (**cache_miss**); the prompt accounting does not match
(**accounting**); or the server fails to start or fit (**did_not_fit**).

Flagged measurements are re-run once (except `short_gen`, which a seeded re-run would only
repeat). If still flagged, they are excluded from selection and headline numbers but stay in
the report as excluded diagnostic results, with the flag shown.

The output sanity check compares greedy 512-token outputs on 3 fixed prompts against a
reference (the plain `--fit` cell at the same context). The thresholds, declared before any
real measurement: a prompt fails if its length is below min(100, half the reference length);
if its distinct 4-gram ratio is below half the reference's; if its longest run of one repeated
token is 16 or more while the reference's is below 16; or if some 8-gram repeats 8 or more
times (non-overlapping) while the reference's maximum is below 8. A candidate passes if none
of its 3 prompts fails. This check exists because of one unconfirmed report of the expert
cache producing degenerate output; it is what excluded MTP draft length 2 from the tuned
configurations (see `docs/upstream/` for the evidence and the open question).

## Machine state during sweeps

Monitors are on the iGPU and machine tuning stays frozen; the browser, games and VMs are
closed and the PC stays on mains power; every sweep is wrapped in `systemd-inhibit` so the PC
cannot sleep mid-run; and only one GPU job runs at a time, enforced by a lock file. Stages 3
and 4 additionally required the quiet-machine check (`scripts/check-quiet.sh`) to pass before
every session.

## Where to read next

- Results: `reports/baseline-report.md` (headline), `reports/stage3/`, `reports/stage4-run2/`.
- Exact rules and their history: `docs/plans/step-0-baseline.md` §5 and §14.
- Human decisions and recorded deviations: `docs/decisions.md`.
- Machine inventory: `docs/environment.md` and `data/env/`.
- Reproduction commands: `docs/runbook-stage3.md` and `docs/recon/commands.env`.