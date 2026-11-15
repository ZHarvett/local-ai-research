# Local AI on a Small PC

<!-- sources: docs/plans/step-0-baseline.md, docs/environment.md, data/env/build-info.json, configs/model.toml, configs/machine.toml, configs/harness.toml, configs/server/stock-32k.toml, configs/server/stock-64k.toml, configs/server/stock-128k.toml, configs/server/tuned-32k.toml, configs/server/tuned-64k.toml, configs/server/tuned-128k.toml, scripts/build-llama.sh, scripts/launch-server.sh, scripts/stop-server.sh, scripts/run-detached.sh, scripts/run-sweep.sh, docs/runbook-stage3.md, docs/runbook-stage2.md, data/analysis/stage3/headline.md, docs/stage2-summary.md, docs/decisions.md, docs/progress-log.md, docs/recon/commands.env, pyproject.toml, LICENSE, LICENSE-DATA.md, data/analysis/stage4/s2-summary.md, data/analysis/stage4/repro-output.txt, reports/stage4-run2/caveats.md, docs/stage4-run2-conditions.md, docs/recon/pcie-link.md -->

Measured, reproducible baselines for running **Ornith-1.5-35B-A3B** (a 35B mixture-of-experts
coding model, Q4_K_M GGUF) with **mainline llama.cpp** on a **16 GB RTX 5060 Ti** desktop:
stock vs tuned `llama-server` configurations at 32K, 64K and 128K context, plus pinned
OpenCode and dsh harness setups.

**Status: work in progress.** Stages 1–4 are measured: Stage 3 is the final stock-vs-tuned
comparison, and Stage 4's next-day reproducibility check (S2) passes 6 of 6 rows on run 2
(run 1 is superseded — see [Reproducibility](#reproducibility-stage-4)). The v0.1.0 release
checks (clean-shell walkthrough, scrub, tag) are still pending.

## What this is

Step 0 of a longer project: it turns pre-measurement estimates into measured facts. The repo
contains:

- the six released server configs (`configs/server/{stock,tuned}-{32k,64k,128k}.toml`) and the
  launch script;
- parameterised sweep and analysis tooling (Python via `uv`, TOML specs in `configs/sweeps/`);
- raw per-request JSONL, environment snapshots, telemetry, health and sanity checks,
  microbenchmarks (`data/`, append-only);
- the baseline report with 95% CIs (`reports/`), the decisions log (`docs/decisions.md`) and
  runbooks with the exact commands (`docs/runbook-stage3.md`, `docs/recon/commands.env`).

**Stock** is what a typical user would run (plan §3.1): the model card's defaults, llama.cpp's
automatic placement (`--fit`), default batch sizes (`-b 2048 -ub 512`), FP16 KV, flash attention
`auto`, default slot count, the default host prompt cache (`--cache-ram 8192`) and no
speculative decoding. Only the model, context, host and port are set explicitly.

**Tuned** is the best measured configuration per context, chosen by a selection rule declared
before any speed measurement (plan §3.3, ordered by the standardised turn time `T_turn_400`).
All three tuned configs use CPU expert offload (`-cmoe`) with a probed max-fit expert cache in
VRAM, batch and ubatch 4096, flash attention `on`, one slot and `--cache-ram 2048`. Per context
(`configs/server/tuned-*.toml`, `docs/stage2-summary.md`):

| context | expert cache (MiB, probed max-fit) | KV type | MTP speculative decoding |
|---|---|---|---|
| 32K  | 11,520 | q8_0 (8-bit, the sweep default) | off |
| 64K  | 9,472  | f16 | on, draft length 1 |
| 128K | 8,704  | f16 | off |

### Hardware it was measured on

<!-- sources: docs/environment.md, configs/machine.toml -->

| Component | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 5060 Ti, 16,311 MiB (16 GB); driver 615.78.08; power limit 180.00 W |
| CPU | AMD Ryzen 7 9700X, 8 cores / 16 logical; amd-pstate-epp, performance governor |
| RAM | MemTotal 30.46 GiB; EXPO enabled (6000 MT/s configured speed) |
| Swap | zram, 30.5G; `vm.swappiness` 150 |
| OS | CachyOS, kernel 7.3.1-1-cachyos; CUDA 13.4 (nvcc); gcc/g++ 16.2.1 |
| Storage | repo and models on a 256 GB SK hynix NVMe (btrfs, `compress=zstd:1`) |
| Display | both monitors on the AMD iGPU; no display clients on the RTX 5060 Ti |

Machine tuning is frozen for the whole project and recorded with every run; any change triggers
a canary re-check. The full inventory is `docs/environment.md` (scrubbed) and
`data/env/inventory-2026-11-08.json`.

### Provenance

<!-- sources: data/env/build-info.json, configs/model.toml, configs/harness.toml, docs/progress-log.md -->

- **llama.cpp** `b12208`, commit `57d04820dfef7a3519aac276d018a6fd71251895`, built 2026-11-08
  with `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release`
  (Ninja; cmake 4.4.5, ninja 1.13.2, nvcc 13.4 V13.4.92, gcc/g++ 16.2.1). The full record
  including binary SHA-256s is `data/env/build-info.json`.
- **Model** (verified in WP4; `configs/model.toml`):

| Item | Value |
|---|---|
| Repository | `ornith-ai/Ornith-1.5-35B-A3B-GGUF` |
| Revision | `f60452672689e0040be350560267a614cc172a18` (2026-08-24) |
| File | `Ornith-1.5-35B-Q4_K_M.gguf`, 21,713,463,040 bytes |
| SHA-256 | `42739874cc2ccfdb8523b23fbe52e29b2a7555c8176737ca9ca0b5d59859d41f` |
| License | MIT (as stated on the repository) |

- **Harnesses** (`configs/harness.toml`): `opencode-ai` 1.19.5 and `@deepseek-ai/dsh`
  0.2.1-rc.5 (295 dsh plugin packages, all at the same version), node 26.13.0, npm 12.2.1.
  Installed offline from a pinned lockfile by `scripts/install-harnesses.sh`; both completed
  the smoke task against the local server.

## Quick start

### Prerequisites

- Linux x86-64 with an NVIDIA driver (measured: 615.78.08) and the CUDA toolkit with `nvcc`
  (measured: 13.4). The build script targets `sm_120` (RTX 5060 Ti) and expects `nvcc` at
  `/opt/cuda/bin` and the host compiler at `/usr/bin/g++` (CachyOS/Arch layout); for another
  GPU or distro, adjust `CMAKE_CUDA_ARCHITECTURES` and the compiler paths in
  `scripts/build-llama.sh`.
- gcc/g++, cmake, ninja, git, curl (measured versions: gcc 16.2.1, cmake 4.4.5, ninja 1.13.2).
- [uv](https://docs.astral.sh/uv/) (measured: 0.13.7); Python >= 3.12 is managed by uv
  (`pyproject.toml`).
- About 30 GB of free disk for Step 0 (plan §4); the model file alone is 21,713,463,040 bytes.
- A 16 GB VRAM GPU to run the released tuned configs as they are. On a 12–16 GB machine, see
  [Rerunning the sweep](#rerunning-the-sweep-on-your-own-1216-gb-machine) below.

### 1. Set up the Python environment

```bash
uv sync --frozen
```

### 2. Build llama.cpp

The build clones mainline llama.cpp into `third_party/llama.cpp`, checks out the newest `b`
release tag (at least b12017), builds `llama-server`, `llama-bench` and `llama-cli` with CUDA,
and writes `data/env/build-info.json`. It runs 15–40 minutes, so start it detached (it is not a
GPU job and takes no GPU lock):

```bash
bash scripts/run-detached.sh build-llama -- bash scripts/build-llama.sh
```

The job directory is printed; `job.log` and `status.json` land in
`data/logs/jobs/build-llama-<UTC timestamp>/`. The script builds the *newest* upstream tag; the
measured build is `b12208` / `57d04820dfef7a3519aac276d018a6fd71251895`. To reproduce it exactly,
check out that commit in `third_party/llama.cpp` and rebuild with the recorded cmake flags
(`data/env/build-info.json`).

### 3. Download and verify the model

The file lives in `models/` (gitignored). Download the pinned revision and verify its SHA-256
(the command recorded in `docs/decisions.md`, WP4):

```bash
HF_HOME="$PWD/models/.hf-home" uvx --from huggingface_hub==2.4.0 hf download \
  ornith-ai/Ornith-1.5-35B-A3B-GGUF Ornith-1.5-35B-Q4_K_M.gguf \
  --revision f60452672689e0040be350560267a614cc172a18 --local-dir "$PWD/models"
sha256sum models/Ornith-1.5-35B-Q4_K_M.gguf
# must print 42739874cc2ccfdb8523b23fbe52e29b2a7555c8176737ca9ca0b5d59859d41f
```

Optional MTP-head screen (writes `data/health/model-check.json`):

```bash
uv run python -m smallpc.gguf_check models/Ornith-1.5-35B-Q4_K_M.gguf
```

A PASS means only "no known broken-head signature"; the acceptance test during measurement is
what proves the head works.

### 4. Launch a server (stock or tuned)

`scripts/launch-server.sh` is the only sanctioned way to start `llama-server`. It renders the
argument list from the TOML configs, refuses to start if the binary is missing, the port is busy
or the GPU lock is held by another job, then starts the server detached and waits for `/health`
(default 300 s):

```bash
bash scripts/launch-server.sh configs/server/stock-64k.toml    # stock at 64K
bash scripts/launch-server.sh configs/server/tuned-64k.toml    # tuned at 64K
```

Swap in any of the six `{stock,tuned}-{32k,64k,128k}.toml` files. Useful options (from the
script's usage): `--dry-run` (print the rendered argv and exit), `--machine FILE`,
`--model-config FILE`, `--run-id ID`, `--health-timeout SEC`. The server listens on
`http://127.0.0.1:8080` (`configs/machine.toml`; the port is always explicit). Log, pidfile and
exit code are kept in `data/logs/<run-id>/`; the launch prints the run id. Only one GPU job runs
at a time: the launch holds the GPU lock (`.locks/gpu.lock`) for the server's lifetime.

Stop it with:

```bash
bash scripts/stop-server.sh <run-id>    # SIGINT, then SIGKILL after --timeout SEC (default 60)
```

## Rerunning the sweep on your own 12–16 GB machine

<!-- sources: configs/machine.toml, scripts/launch-server.sh, docs/runbook-stage3.md, docs/runbook-stage2.md, docs/progress-log.md, docs/decisions.md, docs/stage4-run2-conditions.md -->

1. **Edit `configs/machine.toml`.** Set the absolute paths (`llama_server`, `models_dir`,
   `slot_save_dir`), the `host`/`port` and the GPU `index` (exported as `CUDA_VISIBLE_DEVICES`).
   The slot-save path must stay under `/dev/shm/local-ai-research-*` — the launch script
   enforces that prefix.
2. **Expect to re-tune on a smaller card.** The tuned configs' expert caches (11,520 / 9,472 /
   8,704 MiB) are probed max-fit values for this 16 GB card; they do not fit a 12 GB card.
   Stock (`--fit` automatic placement) adapts to your GPU. To get tuned configs for your card,
   rerun the Stage 1 and Stage 2 sweeps (`configs/sweeps/stage1.toml`, `stage2-*.toml`;
   `docs/runbook-stage1.md`, `docs/runbook-stage2.md`): the runner probes the max-fit expert
   cache per cell, and the pre-declared selection rule picks the winners.
3. **Host RAM.** The sweep runner aborts below 20 GiB `MemAvailable`; the runbook expects
   24 GiB or more at session start (this machine: MemTotal 30.46 GiB).
4. **Quiet machine, clean tree.** Close browser, IDEs, music/chat apps, monitors, games and
   VMs; `bash scripts/check-quiet.sh` must exit 0. Measurement sessions start only from a clean
   committed tree — never `--allow-dirty`. The PC stays on mains power and is not used during
   a session; sweeps run under `systemd-inhibit` and the GPU lock.
5. **Run the sessions** (commands from `docs/runbook-stage3.md` §3; one session per context,
   each detached, with start and end canaries). For 32K:

```bash
uv run python -m smallpc.sweep check configs/sweeps/stage3.toml --only context=32K   # expect 2 cells
bash scripts/run-sweep.sh configs/sweeps/stage3.toml --only context=32K --session-id stage3-32K
bash scripts/sweep-status.sh stage3-32K        # watch from the terminal; nothing else is open
```

When it says `state=complete`, run the gate and the single re-run pass, then commit the data:

```bash
uv run python -m smallpc.stage3 gate --session data/raw/stage3-32K --spec configs/sweeps/stage3.toml  # exit 0 = pass
bash scripts/run-sweep.sh configs/sweeps/stage3.toml --rerun-flagged stage3-32K   # ONCE, only if a unit is flagged
```

Repeat for 64K and 128K. After the third session, run the sanity check on the three tuned
config files (runbook §3), then the headline and the report:

```bash
uv run python -m smallpc.stage3 headline --sessions data/raw/stage3-32K data/raw/stage3-64K data/raw/stage3-128K \
    --sanity data/sanity/stage3-tuned.json --out data/analysis/stage3/headline
uv run python -m smallpc.report render --sessions data/raw/stage3-32K data/raw/stage3-64K data/raw/stage3-128K \
    --out reports/stage3 --label results --sanity data/sanity/stage3-tuned.json
```

(The sanity file is named `data/sanity/stage3-tuned.json`; the runbook's `stage3-all.json` was
a recorded minor deviation — decision D7 in `docs/decisions.md`.)

**Time budget.** The three Stage 3 sessions took 18.4, 26.4 and 45.9 minutes; the re-run passes
8.2, 11.6 and 17.8 minutes — about 2.1 hours in all. <!-- derived: (18.4 + 26.4 + 45.9 + 8.2 + 11.6 + 17.8) min / 60 = 2.14 h, from docs/progress-log.md "WP13 (part 2, Stage 3)" -->
Stage 4 (one 64K session on a different day) took 26.1 minutes plus a 9.2-minute re-run pass
in run 2, the S2 run (`docs/stage4-run2-conditions.md`); the runbook estimate was 26–29 minutes,
upper bound 44 with a worst-case re-run pass (`docs/runbook-stage3.md` §7). Run 1 (superseded,
R5) took 38.3 + 13.6 minutes (`docs/progress-log.md`, T-007).

## Results

<!-- sources: data/analysis/stage3/headline.md, docs/decisions.md, docs/plans/step-0-baseline.md, docs/stage2-summary.md, docs/progress-log.md, data/analysis/stage4/s2-summary.md, data/analysis/stage4/repro-output.txt, reports/stage4-run2/caveats.md, docs/stage4-run2-conditions.md, docs/recon/pcie-link.md -->

Stage 3 measured the six released configs on a quiet machine: one session per context, stock
and tuned paired in the same session, 5 repetitions each, start and end canaries, one
`--rerun-flagged` pass per session. Ratios are tuned/stock geometric means over paired
repetitions with the wider of a percentile-bootstrap and a t 95% CI (plan §5.5). The
authoritative numbers are `data/analysis/stage3/headline.md`; the rendered report is
`reports/stage3`.

**Headline ratios (tuned / stock).** Lower is faster for `T_turn_400`, `T_reread` and TTFT;
higher is faster for prefill (PP_fresh) and decode (TG). The prefill/decode/TTFT columns are
the min–max across the three measured depths (8K/16K/24K at 32K; 16K/32K/48K at 64K;
32K/64K/96K at 128K); per-depth values with CIs are in `headline.md`.

| context | units | T_turn_400 [95% CI] | T_reread [95% CI] | PP_fresh | TG | TTFT |
|---|---|---|---|---|---|---|
| 32K | clean, n=5 | 0.705 [0.672, 0.739] | 0.378 [0.375, 0.381] | 2.621 to 2.686 | 1.089 to 1.173 | 0.431 to 0.455 | <!-- derived: min-max of the per-depth pp_fresh/tg/ttft ratios in data/analysis/stage3/headline.md (32K clean headline) -->
| 64K | clean, n=5 | 0.690 [0.649, 0.734] | 0.423 [0.419, 0.427] | 2.304 to 2.488 | 1.213 to 1.239 | 0.479 to 0.551 | <!-- derived: min-max of the per-depth pp_fresh/tg/ttft ratios in data/analysis/stage3/headline.md (64K clean headline) -->
| 128K | all units, n=5 — **includes paging-flagged stock windows** | 0.706 [0.679, 0.735] | 0.382 [0.381, 0.384] | 2.487 to 2.926 | 1.125 to 1.143 | 0.418 to 0.521 | <!-- derived: min-max of the per-depth pp_fresh/tg/ttft ratios in data/analysis/stage3/headline.md (128K all-units headline) -->
| 128K | clean units beside it, n=4 | 0.711 [0.673, 0.750] | 0.382 [0.380, 0.384] | 2.487 to 2.932 | 1.107 to 1.141 | 0.416 to 0.521 | <!-- derived: min-max of the per-depth pp_fresh/tg/ttft ratios in data/analysis/stage3/headline.md (128K clean-units figures) -->

**Absolute standardised-turn times** (`T_turn_400`, seconds, from the headline's per-cell
figures):

| context | stock [95% CI] | tuned [95% CI] |
|---|---|---|
| 32K | 8.339 [8.299, 8.379] | 5.882 [5.594, 6.170] |
| 64K | 9.288 [9.238, 9.338] | 6.413 [6.003, 6.824] |
| 128K | 11.191 [11.149, 11.234] (all units; clean: 11.192 [11.129, 11.255], n=4) | 7.910 [7.609, 8.210] |

Notes on the headline rules (decisions D1–D3 in `docs/decisions.md`):

- **The clean-units and all-units versions agree in every context** (sign, and whether each
  interval excludes 1.0).
- **128K (D1).** stock-128K has 4 clean units of 5 after the re-run pass: unit `stage3-128K:3`
  is still paging-flagged in attempt 2 (swap growth 4,200 MiB). Fewer than 5 clean paired units
  means the headline is the all-units comparison, labelled "includes paging-flagged stock
  windows", with the clean-units figures beside it (table above); S4(d) is recorded as a
  deviation for this context. `data/analysis/stage3/headline.md` is authoritative; the rendered
  report (`reports/stage3`) applies the same §5.4 headline rule (the rendering was fixed in T-009).
- **32K swap sensitivity (D3).** Excluding the units whose window shows more than 64 MiB of
  llama-server swap growth removes 3 of the 5 paired units. The point estimates barely move
  (`T_turn_400` 0.712 [0.629, 0.807]), but the wider intervals mean the **32K decode gain is
  small and not robust** to excluding swap-active units: TG becomes 1.157 [0.981, 1.365] at 8K,
  1.142 [0.999, 1.305] at 16K and 1.057 [0.859, 1.300] at 24K — intervals that include 1.0.
  The `T_turn_400` conclusions are unchanged.
- **MTP acceptance (64K tuned).** 0.771 pooled over Request B; per unit 0.771 [0.745, 0.798].
- **VRAM headroom.** Minimum free VRAM across the tuned cells' measured windows: 1,379 MiB
  (32K), 1,021 MiB (64K), 1,211 MiB (128K) — all above the 512 MiB eligibility floor. Peak VRAM
  of the tuned cells: 14,932 / 15,290 / 15,100 MiB.

**What tuning bought (Stage 2 context).** MTP helped about 2 to 5% per turn (4.6% at 32K with
draft length 2 — an excluded configuration; 2.4% at 64K with draft length 1), and costs 9 to 16%
of prefill speed and 768 to 1,536 MiB (0.75 to 1.5 GiB) of max-fit expert cache. <!-- derived: 768 MiB = 0.75 GiB and 1536 MiB = 1.5 GiB, from docs/decisions.md "Corrections to plan v1.7" item 3 -->
Only the 64K tuned config keeps MTP (draft length 1). In the later Stage 2 sessions, 1 window
of 80 was flagged (`docs/decisions.md`, "Corrections to plan v1.7"). The full Stage 2 outcome
table is `docs/stage2-summary.md`.

### Reproducibility (Stage 4)

Stage 4 re-measured stock-64K and tuned-64K on a different day (2026-11-14, session
`stage4-run2`, 5 repetitions per cell with canaries, quiet machine, clean committed tree).
The S2 check requires each re-measured mean (`T_turn_400`, fresh prefill at 32K, decode at
32K depth) to fall inside its original 95% CI or within 5%, whichever is wider.
**Result: PASS — 6 of 6 rows**, every row evaluated on clean units (both cells 5 clean of 5
on both days; the R1 all-units fallback was not triggered). Summary:
`data/analysis/stage4/s2-summary.md`; verbatim tool output: `data/analysis/stage4/repro-output.txt`.

| cell | metric | Stage 3 mean [95% CI] | allowed range (wider of CI, ±5%) | Stage 4 mean | result |
|---|---|---|---|---|---|
| stock-64K | T_turn_400 (s) | 9.288 [9.238, 9.338] | [8.824, 9.753] | 9.100 | PASS |
| stock-64K | fresh prefill 32K (tok/s) | 844.155 [840.328, 847.982] | [801.947, 886.363] | 853.861 | PASS |
| stock-64K | decode at 32K depth (tok/s) | 73.881 [73.792, 73.970] | [70.187, 77.575] | 75.936 | PASS |
| tuned-64K | T_turn_400 (s) | 6.413 [6.003, 6.824] | [6.003, 6.824] | 6.296 | PASS |
| tuned-64K | fresh prefill 32K (tok/s) | 2024.852 [2001.669, 2048.034] | [1923.609, 2126.094] | 2000.895 | PASS |
| tuned-64K | decode at 32K depth (tok/s) | 91.644 [85.476, 97.812] | [85.476, 97.812] | 93.459 | PASS |

Two rows pass inside the Stage 3 CI itself (tuned-64K `T_turn_400` and decode); the other
four pass inside the wider ±5% band. Caveats (`reports/stage4-run2/caveats.md`):

- **Run 1 is superseded (R5).** The first Stage 4 session (`stage4`) ran with the GPU's PCIe
  link at Gen3 x8 instead of Gen4 x8 for the whole session, so it is invalid for S2. It is
  kept as an excluded diagnostic, never deleted (`reports/stage4/`,
  `data/analysis/stage4-run1-superseded/`). The link was restored and verified at Gen4 x8
  under load before run 2 (`docs/recon/pcie-link.md`); every sample in run 2's measured cell
  windows read "4, 8" (R7, as clarified by decision E-009).
- **Changed kernel and driver (E-009).** Run 2 ran on kernel 7.3.4-1-cachyos, driver
  620.70.06; Stage 3 ran on 7.3.1-1-cachyos / 615.78.08. S2 passed on the changed kernel and
  driver; the comparison carries this confound. No re-measure — the data stands.
- The second half of S2 — every recommended config launches from a clean shell using only
  the README commands — is the T-012 walkthrough, still pending.

## Limitations

<!-- sources: docs/plans/step-0-baseline.md, docs/decisions.md, docs/stage2-summary.md, docs/progress-log.md, data/analysis/stage3/headline.md, reports/stage4-run2/caveats.md -->

- **The standardised turn is not real agent use.** Every configuration is compared on the same
  fixed turn: 3,000 new prompt tokens appended to a cached context, then 400 generated tokens
  (thinking included). Real turns vary widely in how many tokens they add and generate; the
  harness smoke tasks only prove the harnesses work and are never representative (plan §3.4).
  Task-success measurement is Step 1.
- **Stages 1–2 ran with desktop apps open** (and idle), as a recorded deviation; only Stages 3
  and 4 enforce the full quiet-machine gate. For context, every Stage 3 mean is within 1.3% of
  the Stage 1/2 selection data (`docs/progress-log.md`, WP13 part 2).
- **Stage 4 carries a kernel/driver confound and one superseded run.** The reproducibility
  pass ran on a changed kernel and driver, and run 1 (PCIe Gen3 x8) is excluded — see
  [Reproducibility (Stage 4)](#reproducibility-stage-4).
- **MTP draft length 2 produces degenerate repetition.** It fails the output sanity check
  deterministically at 32K and 64K on four different placement/KV/context configs (an 8-gram
  repeats 8 times on sanity prompt r0; the reference repeats it 2 times). MTP off and draft
  lengths 1 and 3 pass. Draft length 2 is excluded from all tuned configs
  (`docs/stage2-summary.md`, `data/sanity/`).
- **Host-memory paging is part of the picture.** Stock keeps `--cache-ram 8192`, so its later
  repetitions can be paging-flagged at 64K and 128K; that is how stock behaves on this machine
  and it is reported, not hidden. This machine uses zram swap with `vm.swappiness` 150, and the
  kernel swaps cold pages of the server's own memory. The tuned-64K MTP cell showed the known
  file-page faulting of Stage 2a in attempt 1 (all four flagged units re-ran clean on fresh
  servers; not investigated further — decision D2). One stock-128K unit stayed flagged after
  its re-run, which is why the 128K headline uses all units (see Results).
- **Intervals at n=5 have known coverage limits.** The reported interval is the wider of a
  bootstrap and a t-interval; in simulation it covered about 95% for symmetric data, 91–92% for
  strongly skewed and 88–90% for exponential data (plan §5.5). A repetition slowed by
  background activity is exactly the heavy-tailed case, so the flag rules matter.
- **The 32K tuned KV type is the default, not a measured win.** FP16 vs 8-bit KV at 32K was
  measured only on draft-length-2 cells, which the sanity check excluded; the 32K config keeps
  the measured q8_0 default (`docs/decisions.md`, "Known limitation").
- **One machine, one model, one quant, one build.** No quantization sweep and no cross-machine
  comparison; the numbers are specific to the hardware and the pinned llama.cpp build above.

## Licences

<!-- sources: LICENSE, LICENSE-DATA.md, configs/model.toml, docs/plans/step-0-baseline.md -->

- **Code:** MIT — `LICENSE`. Copyright (c) 2026 ZHarvett.
- **Data, reports and write-up** (`data/`, `reports/`): CC BY 4.0 — `LICENSE-DATA.md`.
  Credit ZHarvett, link to the licence, and indicate if changes were made.
- **Model:** MIT, as stated on the model repository (`configs/model.toml`).
- **llama.cpp:** MIT (upstream; the licence text is in `third_party/llama.cpp/LICENSE` after
  the build).
- The pinned harnesses (OpenCode, dsh) keep their own licences; versions are in
  `configs/harness.toml`.

## Repository layout

- `configs/` — `machine.toml` (paths, port, GPU), `model.toml` (identity, SHA-256, sampling),
  `harness.toml` (pins), `server/` (the six released configs), `sweeps/` (stage specs),
  `workloads/` (recipes pointing at public sources).
- `scripts/` — build, launch/stop, sweep runner, detached jobs, quiet check, harness install,
  smoke tests.
- `src/smallpc/` — config rendering, sweep runner, telemetry, statistics, analysis, report,
  scrub.
- `data/` — append-only raw JSONL, environment snapshots, health/sanity checks, probes,
  microbenchmarks, logs.
- `reports/` — rendered baseline reports and figures.
- `docs/` — the step plan, decisions, runbooks, environment inventory, progress log.
