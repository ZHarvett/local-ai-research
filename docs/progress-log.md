# Progress log

Newest entry last. Each entry: date, WP, status, commit, key results, open issues
(format: `docs/plans/step-0-baseline.md` §12.5).

---

## 2026-11-07 — WP0: Repo bootstrap

- **Status:** done (see acceptance evidence in the WP0 completion report).
- **Commit:** `WP0: bootstrap repository` (first commit on `main`; hash from `git log`).
- **Key results:**
  - Repo at `/mnt/data/local-ai-research` on `/dev/nvme1n1p1` (SK hynix BC711, 238.5 GiB ≈ 256 GB, btrfs, mounted at `/mnt/data`, 164 GiB free at creation). The OS drive is the separate 500 GB WD Green (`nvme0n1`).
  - Plans copied: `docs/plans/project-plan.md` (from `local-ai-plan.md`), `docs/plans/step-0-baseline.md` (from `step-0-baseline-v1.2.md`, version 1.2).
  - Wrote CLAUDE.md, progress-log, decisions, README, LICENSE (MIT), LICENSE-DATA.md (CC BY 4.0), CHANGELOG.md, .gitignore.
  - No remote created; nothing pushed.
- **Open issues:**
  - Plans were found in `~/Downloads/` directly, not in `~/Downloads/local-ai-research/` (folder did not exist; G0 says it should). Copied from where they were.
  - The `.gitignore` entries for raw logs and harness state use provisional names (§8 does not fix them); revisit in WP2/WP7.

---

## 2026-11-07 — WP1: System inventory

- **Status:** done.
- **Commit:** `b2debca` (`WP1: system inventory`).
- **Key results:**
  - `scripts/inventory.sh` (read-only, no sudo) writes `data/env/inventory-<UTC date>.json` and `docs/environment.md`; re-runnable. shellcheck is not installed, so it was only checked with `bash -n`.
  - CUDA 13.4.3 (nvcc at `/opt/cuda/bin/nvcc`, not on PATH) lists compute_120, so sm_120 is supported. gcc 16.2.1 is the only gcc; the CUDA headers guard at `__GNUC__ > 16`, so it is usable as `CMAKE_CUDA_HOST_COMPILER`. The `#error` line in that guard is empty in this header.
  - Missing: uv, gh, shellcheck, ninja (optional). cmake 4.4.5, git, python 3.14, node 26 / npm 12 and curl are present.
  - Two connected displays (DP-1, HDMI-A-1) are on the NVIDIA card (`card1`), none on the iGPU.
  - GPU: driver 615.78.08 (CUDA 13.4), PCIe gen 2 x8 at idle (max gen 4 x8; WP6 measures under load), power limit 180 W (default = max = 180 W), persistence mode disabled.
  - Existing installs: ollama and ollama-cuda 0.40.13 (pacman), `ollama.service` and `libvirtd.service` running, `~/gate0/llama.cpp` and `/mnt/data/models/ollama` found; no llama-server or llama-cli on PATH.
- **Open issues:**
  - Zack to install the missing prerequisites and move the monitors to the iGPU (G1), then re-run the script.
  - RAM speed (EXPO) needs `sudo dmidecode -t memory`; PBO/Eco mode and iGPU status are still to be recorded at G1.

---

## 2026-11-07 — G1: post-change inventory

- **Status:** done, with one open item (desktop contexts still on the dGPU, below).
- **Commit:** `e043707` (`G1: post-change inventory`).
- **Key results:**
  - Displays: the two connected outputs (DP-5, HDMI-A-2) are on `card0` (amdgpu iGPU); all four `card1` (NVIDIA) connectors are disconnected.
  - uv 0.13.7, gh 2.102.1, shellcheck 0.11.0 and ninja 1.13.2 are installed. `ollama.service` is inactive and disabled.
  - RTX 5060 Ti memory.used: 514 MiB of 16311 MiB (P5, 10 W, 24 °C). **Not clean:** 8 desktop processes still hold graphics contexts on it (334 MiB listed per process; the rest is driver/context overhead): cosmic-comp 55 (G), Xwayland 3 (G), cosmic-app-library 36 (C+G), cosmic-launcher 34 (C+G), xdg-desktop-portal-cosmic 34 (C+G), Chrome GPU process 31 (G), ghostty 95 (G), missioncenter 46 (C+G).
  - `docs/environment.md` manual BIOS fields updated (EXPO 6000 MT/s per `dmidecode`, iGPU at BIOS default, PBO/Eco mode default/unrecorded); Ollama decision recorded in `docs/decisions.md`.
  - `scripts/inventory.sh`: shellcheck findings SC2009 and SC2155 fixed; the script now carries the BIOS fields.
- **Open issues:**
  - The desktop (COSMIC compositor and apps) still creates contexts on the NVIDIA GPU even with the monitors on the iGPU. §5.3 treats display clients as a warning, not an abort, but ~0.5 GiB of VRAM is not available to llama-server and it is background GPU activity. Options for Zack (not applied): set the compositor's render device to the iGPU (e.g. `WLR_DRM_DEVICES`/COSMIC equivalent), or run measurements from a TTY/with the desktop closed. Decide before WP5; record the chosen state in the environment snapshot.

---

## 2026-11-07 — WP2: Python skeleton, config schema, launch script, CI

- **Status:** done. All CI commands pass locally; CI itself has not run (no remote).
- **Commit:** `69acdd0` (`WP2: python skeleton, config schema, launch script, CI`).
- **Key results:**
  - `pyproject.toml` (Python >=3.12, system 3.14.9 only: `python-downloads = "never"`), `uv.lock` (35 packages), package `src/smallpc/` with `config.py` (machine, model, server, sweep-spec schemas; unknown fields forbidden) and `render.py` (single `FLAG_TABLE`; `python -m smallpc.render [--nul] <server.toml>`).
  - Stock configs may set only `model, context, host, port, metrics, log_verbosity`; anything else is a validation error. The §5.4 defaults (`-ctk/-ctv q8_0`, `-fa on`, `-np 1`) are filled in for candidate/tuned only.
  - Scripts: `launch-server.sh` (`--dry-run`, port and GPU-lock checks, `/health` wait, 300 s default), `stop-server.sh` (SIGINT, then SIGKILL; writes `stop-status.json`), `with-gpu-lock.sh`, internal `_supervise.sh` and `_common.sh`.
  - GPU lock: `<repo>/.locks/gpu.lock` (gitignored), `flock -n` on fd 9, `SMALLPC_GPU_LOCK_HELD=<pid>` set by the wrapper. fd 9 is inherited by the server, so the lock lasts as long as the server does. `launch-server.sh` without the wrapper takes the lock itself.
  - 80 tests pass (`-m "not gpu"`), including golden argv for the four examples, validation errors, determinism, dry-run vs golden and a launch/stop lifecycle against a fake server (SIGINT, SIGKILL fallback, busy port, lock refusal).
- **Open issues:**
  - Flag names are the upstream names given in the prompt and are unverified until WP3 (`--help`). `spec_type` is limited to `none`/`draft-mtp` and `load_mode` to `auto`/`none` until then.
  - `configs/model.toml` `file` is a placeholder name (`Ornith-1.5-35B-A3B-Q4_K_M.gguf`), to be replaced by WP4.
  - `SMALLPC_GPU_LOCK_HELD` is trusted when it names a live pid and the lock is held; the holder cannot be identified beyond that.
  - GitHub Actions pins (`actions/checkout@v7.0.1`, `astral-sh/setup-uv@v10.3.3`, uv 0.13.7) were looked up with `git ls-remote`; the workflow has never run.

---

## 2026-11-08 — WP3: Build llama.cpp

- **Status:** done. All acceptance checks pass; CI commands pass locally (121 tests, ruff, shellcheck).
- **Commits:** `48c823a` (`WP3: build llama.cpp`), `dfcd7d9` (`WP3: record desktop GPU steering`), then `WP3: progress log` (this entry).
- **Key results:**
  - llama.cpp **b12208**, commit `57d04820dfef7a3519aac276d018a6fd71251895` (newest b-tag; required >= b12017). Upstream's newest semver tag, `v0.9.0`, is recorded in `data/env/build-info.json` only. `llama-server --version`: `version: 0.9.0-dev (build 12208, commit 57d04820d)`, built with GNU 16.2.1.
  - Build: Ninja, CUDA 13.4.92 (`/opt/cuda`), host compiler `/usr/bin/g++` 16.2.1, `CMAKE_CUDA_ARCHITECTURES=120` (CMake rewrote it to `120a`), 6 jobs, no OOM retry. **Build duration 262 s** (configure + compile, excluding the clone); the detached job ran about 6 min wall-clock including the clone.
  - `scripts/run-detached.sh` / `job-status.sh` written and tested (`sleep 1; exit 3` records exit code 3). The build ran through them.
  - `--help` lists `--moe-cache-mib`, `--fit`, `--slot-save-path`, `--reasoning-budget`; `--spec-type` accepts `draft-mtp` (and 10 other values). `--list-devices`: `CUDA0: NVIDIA GeForce RTX 5060 Ti (15941 MiB, 15803 MiB free)`. `ldd`: libcudart/libcublas/libcublasLt resolve to `/opt/cuda/lib64`.
  - Flag table: all 22 flags exist, none renamed (golden files unchanged). Enums widened: `spec_type` (11 values), `load_mode` (`auto, none, mmap, mlock, mmap+mlock, dio`), `log_verbosity` 0-5. New tests check the table, the enums and `server-defaults.json` against `data/env/llama-server-help.txt`.
  - Server defaults (`data/env/server-defaults.json`): port 9931, fit on, fit-target 1024 MiB, ctx-size 0 (from model), batch 2048, ubatch 512, parallel -1 (auto), flash-attn auto, K/V f16, ctx-checkpoints 32, checkpoint-min-step 8192, cache-ram 8192 MiB, spec-type none, spec-draft-n-max 3, load-mode auto, reasoning-budget -1.
  - Desktop GPU steering (read-only): RTX 5060 Ti at 2 MiB of 16311 MiB, no process holds a context (G1 had 514 MiB and 8 processes). **Mechanism not identified**: no GPU-selection variable or setting in any searched location. Recorded in `docs/environment.md` and `docs/decisions.md`.
- **Open issues:**
  - Zack to name the mechanism (file and setting) behind the iGPU-first desktop so it can be recorded; the undo description depends on it.
  - The steering state is part of the frozen machine tuning; the VRAM figure drifts with desktop activity, so each run's snapshot must record it.
  - The actual slot count under `-np -1` and the fitted context are runtime values; read them in WP5.
  - A WP0 entry in `docs/decisions.md` contained the account name; scrubbed in the working tree, but it remains in git history (commit `b2debca` or earlier). Rewrite history before any public push.
  - The semver tags upstream (`v0.x.0`) are not obviously a "stable" channel; recorded only, as instructed.

---

## 2026-11-08 — WP4: Model download and verification

- **Status:** done. All acceptance criteria pass; CI commands pass locally (148 tests, ruff, shellcheck).
- **Commits:** `5182616` (`WP4: record desktop GPU steering mechanism`), `1660428` (`WP4: model download and verification`), then `WP4: progress log` (this entry).
- **Key results:**
  - Desktop GPU steering (asked of Zack): a Gigabyte BIOS setting, Settings > IO Ports > Integrated Graphics = Forced, Initial Display Output = IGD Video, UMA Mode = Auto, monitors on the motherboard outputs; recorded with an undo description in `docs/environment.md`, `docs/decisions.md`, `configs/machine.toml` and `scripts/inventory.sh`. The two open items (WP14 history scan, WP12 load-mode meanings) are in `docs/decisions.md`.
  - Model: `ornith-ai/Ornith-1.5-35B-A3B-GGUF`, `Ornith-1.5-35B-Q4_K_M.gguf`, 21,713,463,040 bytes, revision `f60452672689e0040be350560267a614cc172a18` (2026-08-24 03:38:27 UTC; newest commit that changed the file's content, checked at all 17 commits). SHA-256 `42739874cc2ccfdb8523b23fbe52e29b2a7555c8176737ca9ca0b5d59859d41f`: published by Hugging Face and computed locally, identical. License `mit`.
  - Download: huggingface_hub 2.4.0 via uvx, 15:53:22Z to 16:27:52Z = **34 min 30 s** (about 10.5 MB/s), detached, exit code 0. `git ls-files models` is empty.
  - Base repo `ornith-ai/Ornith-1.5-35B-A3B` at `10fbf86fed7ecee4a061f8b499a618f46001cac1` (identified from the card's links; the GGUF card has no `base_model`). Sampling recorded verbatim: general temperature 0.6 / top_p 0.95 / top_k 20; benchmarks temperature 1.0; no thinking/non-thinking/coding split.
  - `smallpc.gguf_check`: verdict **PASS** (`data/health/model-check.json`): `qwen35moe`, block_count 41, `nextn_predict_layers` = 1, 256 experts / 8 used; 20 `blk.40.*` tensors (16 trunk-shaped + 4 `nextn.*`), 0 of 12 matrices fresh-init-like, no non-finite values, all norm medians inside [0.2, 5]. The smallest norm median is `nextn.enorm` at 0.2734, close to the lower bound but inside it. PASS means only "no known failure signature". 26 synthetic-tensor tests (incl. no false rejection).
  - Load check (`--check-tensors`, `-ngl 0`, `-c 2048`, port 8191, GPU lock): no tensor errors. Without MTP, `blk.40.*` are skipped as "unused" and not validated, so a second load with `--spec-type draft-mtp` covered the head: no errors, MTP draft context created. VRAM: 2 MiB before, 422 MiB (load 1) / 698 MiB (load 2) while up, 2 MiB after. Excerpt: `data/health/load-check-excerpt.txt`.
- **Open issues:**
  - **Chat template (Zack to decide):** the template embedded in the GGUF is not identical to the official one (modified variant, "Unsloth fixes - developer role, tool calling"; 18 changes). llama-server uses the embedded one unless `--chat-template-file` is given. Nothing changed; decide before WP5/WP7 and keep it the same in every stage (`docs/decisions.md`).
  - The head is only screened, not proven: WP5's draft-acceptance (>= 50% at draft length 1) and equivalence tests are what prove it works.
  - `--check-tensors` validates only the fp16 scales and float values, not the quantized integers, and no negative control was run.
  - The base repo's `license_link` points to a LICENSE file that is not in its file list.
  - The BIOS change date is not recorded (WP3 already observed the steered state).
  - uvx cached its tool environment under `~/.cache/uv` (uv's normal cache); the Hugging Face cache and download metadata stayed under `models/`.
  - WP12: choose the load-mode comparison from the six accepted values. WP14: scan the full git history for the account name, hostname and home paths.

---

## 2026-11-08 — WP5: Server bring-up and endpoint health checks

- **Status:** done. 27 of 27 checks PASS (`data/health/endpoints-2026-11-08.json`); S4(a) PASS. CI commands pass locally (206 tests, ruff, shellcheck).
- **Commits:** `4938994` (`WP5: record decisions`), `7b12bc7` (`WP5: server bring-up and endpoint health checks`), then `WP5: progress log` (this entry).
- **Decisions recorded first:** the embedded GGUF chat template is used in every stage (no `--chat-template-file`); the "template hash matches WP4" check is the whitespace-normalized SHA-256 of the `/props` template against the embedded template's (`241770246d95...`, equal), reported next to the official one (`1575085b3cc2...`, not equal). `model-check.json` stores no embedded hash, so `smallpc.health` computes it from the GGUF. Base repo confirmed. Manual BIOS fields updated (docs, `machine.toml`, `inventory.sh` strings; inventory not re-run).
- **Placement and context (health-64k, `--fit on`, 8-bit KV, `-fa on`, `-np 1`):** effective `n_ctx` 65536, 1 slot (`n_ctx_slot` 65536, `kv_unified=false`). `--fit` projected 20892 MiB vs 15803 MiB free, kept `-c` unchanged and put the sparse experts of 15 of 41 layers on the CPU (14 layers fully, the first partial layer keeps attention+up+gate on the GPU: overflow type GATE). Buffers: CUDA0 model 13614 MiB, CPU_Mapped 6561 MiB, KV 680 MiB (K and V 340 MiB each, q8_0), recurrent state 62.8 MiB, compute 350 MiB (+80 MiB host). VRAM: 2 MiB before, 14874 MiB after load, 14972 MiB after the warm-up request. With MTP the placement moves to 16 (d=1) and 17 (d=2) expert layers on the CPU; VRAM 15056 / 14912 MiB after load, 15254 / 15110 MiB after warm-up. The fit trace and buffer sizes are only logged at `-lv 4`, so `health-64k.toml` sets `log_verbosity = 4`.
- **Timing fields:** `cache_n, prompt_n, prompt_ms, prompt_per_token_ms, prompt_per_second, predicted_n, predicted_ms, predicted_per_token_ms, predicted_per_second`, plus `draft_n` and `draft_n_accepted` only when something was drafted. Same names as Appendix B.
- **Thinking budget:** per-request field is `reasoning_budget_tokens` (alias `thinking_budget_tokens`) on `/v1/chat/completions`, with the global flag unset. Unbudgeted 3000 reasoning tokens (hit `max_tokens`, so a lower bound), budget 64 gave 63, then a 4386-character answer.
- **S4(a), MTP acceptance** (aggregate `sum(draft_n_accepted)/sum(draft_n)`, 3 prompts from real MIT sources in `third_party/llama.cpp`, about 4K prompt tokens, 512 tokens requested): length 1 greedy **88.6%** (619/699; per prompt 84.5 / 98.8 / 79.4%, the third stopped at 297 tokens); card sampling 91.1%; thinking on 90.2% (information only). Length 2 greedy 83.4% (957/1148), card sampling 80.7%, thinking on 81.1%.
- **Equivalence MTP off vs on (3 x 256 tokens):** d=1: identical, near tie at position 62 (gap 0.0465 nats), near tie at 149 (0.0429). d=2: near ties at 89 (0.0265) and 45 (0.2064), one identical. No real divergence.
- **MTP across save/restore (draft length 2, `-np 1`, 64K; one fresh server per arm; turn-3 `cache_n`/`draft_n`/`draft_n_accepted`):** short history (181 tokens): control 180/46/42, control repeat 180/46/42, slot files 180/46/42, prompt cache 180/46/42; long history (3191 tokens): 3190/46/43 for all four. Tokens identical to the control in every arm. Source of the restored prefix confirmed from the log: slot files = `slot_restore` (`restored the draft state (0.364 MiB / 6.311 MiB)`), prompt cache = `prompt_cache` (`prompt_save ... (draft: ...)` before, a prompt-cache load at turn 3). **Finding: on b12208 neither mechanism loses the draft state** (no negative control exists, see below).
- **Context checkpoints:** the premise that no checkpoint exists below `--checkpoint-min-step` (8192) is false on this build. Checkpoints are created at prompt ends at any length (positions 179/200 in the short, 3189/3210 in the long conversation; 6 and 7 per server), and slot files carry them (2 restored in the check-6 test). Turn 3 itself used no checkpoint restore (`restored_from_checkpoint` 0).
- **MTP with `-np 2`:** not rejected. The server starts with 2 slots (`n_ctx_seq` 32768 each at `-c 65536`), 17 expert layers on the CPU, and both slots draft when two requests run at once (draft_n 22 and 18). The step plan §13 assumption (MTP may need a single slot) does not hold on b12208.
- **Slots without MTP (check 6):** save 1267 tokens, erase, erase check `cache_n` 0 (no prompt-cache load, not confounded, so no `--cache-ram 0` repeat was needed), restore, continuation `cache_n` 1267, tokens identical to the never-saved run.
- **Expert cache (`-cmoe --moe-cache-mib 4096`):** the statistics lines are printed at clean SIGINT shutdown only with `-lv 4` (absent at the default level). Decode-sized batches (`ubatch <= 8`): hits 83621, misses 41364, hit rate 66.9%; prefill-sized batches show no hit/miss line, only `large batches: 115236 experts copied from the cache` (69521 MiB). `-lv 4` cost: 45.20 vs 44.93 tok/s, paired difference +0.61% (a preliminary run gave -0.04%); not measurable, so hit rates can be collected with `-lv 4` in the sweep runs themselves. Decode only; 3 repetitions, one arm order (lv4 first).
- **Cleanup:** `/dev/shm/local-ai-research-*` removed after the run, no llama-server running, GPU lock free, VRAM 2 MiB.
- **Open issues:**
  - The draft-state test has no negative control (the server cannot be made to drop the state); the evidence is the log lines plus identical statistics in all four arms at two history lengths. A history above 8192 tokens was not tested.
  - Phase C (check 8) was re-run once after adding `prompt_save` lines to the evidence; all other phases come from the single final run. Phase results are in the gitignored `data/logs/health-*`; the committed record is `endpoints-2026-11-08.json` and the fixtures (`tests/fixtures/logs/`, five scrubbed excerpts).
  - Check-8 turns use the empty-think (non-thinking) generation prompt to keep turns short and deterministic; the thinking-on case is covered only by the acceptance numbers.
  - Greedy MTP-off references come from a different `--fit` placement than the MTP servers, so near ties can come from numerics.
  - The expert-cache hit rate is from 3 prompts at 128 tokens (stats run) and 3x256 tokens (A/B), not a sweep result.
  - Step 1/2 must decide which chat template to use for task success and the prefix-cache doctor (note for the executive chat).

---

## 2026-11-08 — WP6: Telemetry, environment snapshot, microbenchmarks

- **Status:** done. All acceptance criteria pass; CI commands pass locally (309 tests, ruff check and format, shellcheck).
- **Commits:** `6c3d06a` (`WP6: record decisions`), `34276cf` (`WP6: telemetry, environment snapshot, microbenchmarks`), then `WP6: progress log` (this entry).
- **Decisions recorded first:** every sweep cell, stock included, runs with `-lv 4` (hit rates are decode-batch rates plus large-batch copy counts; WP9 and the report must say so); the "For the executive chat" notes (template, MTP with `-np 2`, MTP draft state across restore, checkpoints, MTP acceptance on llama.cpp's own source) are in `docs/decisions.md`.
- **New modules:** `stats` (summarize: bootstrap and t intervals, wider one reported), `scrub` (+ `--check`), `envsnap` (snapshot, `snapshot_id`, preconditions), `telemetry` (2 Hz sampler on one `nvidia-smi -lms 500` process), `flags` (thermal, paging, drift, warm_prefill, cache_miss, short_gen, did_not_fit), `sizes`, `microbench`, `livecheck`; `scripts/run-microbench.sh`, `tools/pcie_bw.cu`, `tools/stream/` (pinned).
- **PCIe** (`data/microbench/pcie.json`, 5 reps + discarded warm-up per configuration, CUDA events, decimal GB/s): link read **Gen4 x8 in 182 of 182 samples taken during transfers** (Gen1 x8 in the 2 idle samples before). Pinned host-to-device 14.29 (expert-sized, 1,904,640 B), 14.38 (16 MiB), 14.39 (256 MiB) GB/s; pinned device-to-host 14.51; pageable 14.0-14.5 except expert-sized pageable device-to-host, 11.45 [11.21, 11.69]. 200 back-to-back expert-sized copies: 133.7 us per copy and 7,480 copies/s pinned host-to-device (14.25 GB/s); pageable device-to-host 167.6 us. The reference 14.3 GB/s is matched within 1% for all pinned and for pageable host-to-device.
- **STREAM** (`stream.json`, unmodified stream.c 5.10 at `6703f75`, 100M elements, NTIMES 20, best rate in MB/s): 8 threads Copy 52,272 / Scale 42,434 / Add 46,681 / Triad 47,016; 16 threads 52,461 / 41,291 / 46,026 / 46,330. That is 43-55% of the 96 GB/s dual-channel DDR5-6000 peak; 16 threads are not faster than 8.
- **NVMe** (`nvme.json`): `dd iflag=direct bs=16M`, first 8 GiB, **1,881 MB/s** [1,874.5, 1,887.5]. Verdict **direct**: `Cached` in `/proc/meminfo` grew by at most 3.4 MB per repetition (8.6 GB read), so btrfs (`compress=zstd:1`) did not fall back to buffered reads. Sequential, queue depth 1, upper bound only.
- **Exact sizes** (`model-sizes.json`): bytes per expert 1,769,472 (Q4_K down, 20 layers) or 2,039,808 (Q6_K down, 20 layers); mean 1,904,640 = **+5.8% vs the plan's 1.8 MB**; 563.8 experts per GiB, 525.0 per GB (plan: about 550 per GB, -4.5%). KV bytes per token: **20,480 at f16** (plan ~20 KB, +2.4%), **10,880 at q8_0** (plan ~10 KB, +8.8%); 10 full-attention layers x 2 KV heads x (256 + 256). Recurrent state 65,863,680 B per sequence (30 layers; R 2.81 MiB + S 60 MiB). The metadata calculation matches the WP5 64K log exactly (680.00 MiB KV, 62.81 MiB recurrent), so there is no disagreement to resolve.
- **Live check** (`sampler-60s.csv`, 120 rows over 59.5 s, health-64k server, 7 requests of about 4,060 prompt tokens + 256 generated, temperature 0, `cache_prompt` false; 963-989 tok/s prefill, 87.5-87.7 tok/s decode): **thermal not flagged** (max Tctl 67.5 C, GPU 54 C, no slowdown reasons, no power-cap samples), **paging flagged by the "any swap-in" rule only**: llama-server had 0 major faults, but system-wide `pswpin` rose by 12 pages (zram swap in use, swappiness 150). Link Gen4 x8 in all 120 samples. Sampler cost **0.16% of one core** (0.06 s Python + 0.03 s nvidia-smi over 57 s, from `/proc/<pid>/stat`). Server stopped by SIGINT; no llama-server left, lock free, `/dev/shm/local-ai-research-*` clean, VRAM 2 MiB.
- **Snapshot:** `snapshot_id` `6b3015e09e8e9b87` is the same in the example, the suite's snapshot and the live-check snapshot (llama-server is excluded from the identity). Example: `data/env/snapshot-example-2026-11-08.json`.
- **scrub --check** over `data/ docs/ src/ tests/ scripts/ configs/ tools/` and the top-level files: 0 findings in 533 files; a planted leak is found (positive control).
- **Open issues:**
  - **Paging flag vs background swap-in:** `pswpin` is system-wide and moves by about 3-4 pages/s on this idle machine (390 pages in the 115 s PCIe run, 925 during STREAM), so the literal "any swap-in" rule would flag nearly every window. `flags.paging` takes `swap_in_tolerance_pages` (default 0 = the plan's rule); WP9 should decide whether to count only llama-server's own swapped-in pages (per-process `/proc/<pid>/status` VmSwap deltas or `majflt`) or keep the system-wide rule.
  - The load-average precondition (below 1.5) is raised by the microbenchmarks themselves: the first suite run aborted STREAM and NVMe because the PCIe copy loops left the 1-minute load at 1.78. The driver now waits for the load to settle (up to 300 s, recorded as `waited_for_load_s`; 172 s before NVMe). `pcie.json` comes from the first run, `stream.json` and `nvme.json` from the second (same snapshot id). WP9 will meet the same effect between cells.
  - CIs are within one session and very narrow for PCIe (deterministic copies); they say nothing about day-to-day variation.
  - The 8-vs-16-thread STREAM comparison uses `OMP_PROC_BIND=spread` with `OMP_PLACES=cores` (8) and `threads` (16); other bindings were not tried. Results are "STREAM-based" (the licence's labelling rule), not official STREAM results.
  - `configs/harness.toml` does not exist yet (WP7); the snapshot records the harnesses as "unavailable".
  - PCIe tool timings use the mean expert size; per-layer sizes differ by 15% (1.77 to 2.04 MB).

---

## 2026-11-08 — WP7: Harness setup and smoke tests

- **Status:** done. Both smoke tests pass; all CI commands pass locally (379 tests, ruff, shellcheck).
- **Commits:** `c700849` (`WP7: record decisions`), `2b8c5a4` (`WP7: harness setup and smoke tests`), then `WP7: progress log` (this entry).
- **Pinned:** `opencode-ai` **1.19.5** (2026-10-28, `latest`, Zack chose this line over `@opencode/cli`) and `@deepseek-ai/dsh` **0.2.1-rc.5** (2026-10-29; `latest` 0.2.2-rc.1 was 4 days old). 295 dsh plugin packages, all at 0.2.1-rc.5. Whole tree (643 name@version) installed with `--before=2026-11-01T18:25:11Z`: none newer than the cutoff, no overrides. `npm ci --ignore-scripts` reproduces it (`scripts/install-harnesses.sh`, lockfile sha256 `d21af6e8...`); only `opencode-ai`'s postinstall was run (offline); five other install scripts stay blocked by `allowScripts`.
- **Isolation:** every harness execution goes through `scripts/_sandbox.sh` (bubblewrap, empty `/home` and `/tmp`, read-only file system, `env -i`, repo-local HOME/XDG/TMPDIR/npm cache, private network namespace with only the server and a deny-all logging proxy bridged in). `data/harness/isolation-check.txt`: the six personal paths listed before and after are byte-identical (only `~/.npm` exists, 9,318 lines each).
- **OpenCode smoke:** PASS, 17 s, attempt 1 of 2 (`data/harness/smoke-opencode-20261108T184655Z`). Independent pytest green, test file byte-identical, 5 steps, 6 requests, 0 permission prompts, 0 rule denials. A first run against the unmodified stock-64k config also passed (20 s) but could not derive `cache_n` at default log verbosity, so the pattern comes from `configs/server/smoke-stock-64k.toml` (= stock + `-lv 4`).
- **dsh smoke:** PASS, 18 s, attempt 1 (`data/harness/smoke-dsh-20261108T184729Z`), headless profile, same checks, 5 steps, 6 requests. dsh has a headless mode, so no manual procedure was needed.
- **Stock server in /props:** 4 slots, kv-unified, per-slot n_ctx 65536 (no top-level n_ctx). `limit.context` 65536, `limit.output` `min(16384, ctx // 4)` = 16384.
- **Request pattern** (`data/harness/request-pattern.json`, labelled smoke-task data): OpenCode 1 title + 5 main requests, totals prompt_n 7,095 / cache_n 25,420 / predicted_n 486; dsh 1 title + 5 main, prompt_n 6,397 / cache_n 24,131 / predicted_n 713. The title request appeared in both harnesses; it ran on slot 0 while all main requests used slot 1, and each main request reused its own previous prefix (cache_n 6,032 / 6,079 / 6,605 / 6,704 for OpenCode, equal to OpenCode's own `cache.read`). With 4 slots the title request did not change main-loop cache reuse; a single-slot server was not tested.
- **Permission probes** (scripted fake model, no GPU): OpenCode 17 tool calls (4 allowed, 13 denied: curl, rm, `&&`, pipe, `$(...)`, `python -c`, absolute and parent paths, webfetch, write/read outside the project, task), 0 prompts; an `ask` is auto-rejected in `opencode run`. dsh: approvals fail closed; dsh's own sandbox does not stop bash network or `/tmp` writes, so the network namespace does.
- **Network/file writes:** `data/harness/network-observed.md`. Notable: OpenCode fetches `models.opencode.ai/api.json` unless `OPENCODE_DISABLE_MODELS_FETCH=1`, and always tries to install `@opencode-ai/plugin` from npm (no switch; refused by the proxy, harmless WARN); dsh telemetry defaults to a DeepSeek collector in `FEEDBACK_ONLY` mode (set `DISABLED`).
- **Open issues:**
  - `opencode-ai` has no repository or provenance metadata on npm; its identity rests on the shared maintainer with `@opencode/cli`, download counts and the lack of any deprecation. The official docs now name `@opencode/cli` (OpenCode v2 config schema); Step 1/2 may want to revisit.
  - The dsh pin is a pre-release, chosen by publish time; 0.2.2-rc.1 qualifies from 2026-11-11.
  - A proxy cannot see traffic that ignores proxy settings (`strace` is not installed); the network namespace is the real containment.
  - Smoke runs have a snapshot and telemetry but no warm-up (not measured runs); `/v1/models` reports the model path as its id, so the OpenCode model key is the full path.
  - For WP8/WP9: `smallpc.requests` parses per-request lines only at `-lv 4`; the harness env and sandbox helper are reusable for Step 1 harness runs; `limit.output`/`maxTokens` are derived from the per-slot context.

---

## 2026-11-08 — WP8: Workloads

- **Status:** done. All acceptance criteria pass; CI commands pass locally (407 tests, ruff check and format, shellcheck, `scrub --check` 0 findings in 885 files).
- **Commits:** `69c89db` (`WP8: record decisions`), `ba7ce1b` (`WP8: workloads`), then `WP8: progress log` (this entry).
- **Sources** (shallow clones, depth 100, gitignored in `third_party/workload-sources/`; 17 MB and 4.0 MB): `python-poetry/poetry` tag 2.5.1 `94b6e35b9091991887aa54feeb3771a86d3bd692`, MIT (`LICENSE` SHA-256 `1786f071...`), 645,819 hand-written tokens in 309 files; `tokio-rs/axum` tag `axum-v0.8.9` `c59208c86fded335cd85e388030ad59347b0e5ae`, MIT (no root license at the tag; four per-crate files, hashes in the manifest), 346,356 tokens in 256 files.
- **Manifest** (`configs/workloads/manifest.json`, 235 KB, recipes only; inputs in `recipe.toml`): 83 prompt entries (A 35, B 35, short 5, warm-up 2, sanity 3, equivalence 3) and 5 append chunks; every prompt is exactly its length (K = 1024) and every append exactly 3,000 tokens. 27 special-token strings (read from the vocabulary) are excluded from sources and command output.
- **Verify** (`python -m smallpc.workloads run verify`, `data/workloads/verify-2026-11-08.json`): 16 of 16 checks PASS: 48 prompts regenerated from the manifest with 1,550,336 tokens counted by `/tokenize` and every text and token hash reproduced, 5 appends, 35 prefix checks against the real `/apply-template` and whole-text `/tokenize`, context-fit table, nonce uniqueness (42 fresh requests of the 5-repetition plan).
- **Live checks** (`data/workloads/live-check-2026-11-08.json`, `workload-check-128k.toml`, one clean run after an earlier scratch run with the same result): equivalence at 2K, 8K and 32K PASS (`prompt_n` equal, first 16 tokens equal). All 35 pairs PASS: Request A `prompt_n` = d, `cache_n` 0; Request B `prompt_n` 3,000, `cache_n` = d, `predicted_n` 400, `stop_type` limit, at every depth (8K to 96K) and variant. The five short points each generated 400 tokens (limit). Findings: none. Rejected recipes: none (wording W0 was enough for all variants).
- **Server stopped** by SIGINT (exit 0); no llama-server left, GPU lock free, `/dev/shm/local-ai-research-*` clean, VRAM 2 MiB.
- **For WP9:** `from smallpc.workloads import get_workload` (documented in `smallpc/workloads/api.py`): `get_workload("pair", d, repetition=r)` returns `a_tokens`, `b_tokens`, nonce, seed and `expected` (including `processed_plus_cached`). Send token arrays to `/completion`. Request A with `n_predict` 0 reports `predicted_n` 1 and `stop_type` limit on this build, yet B then reuses exactly d tokens. Repetitions 5 and above are built on demand (the manifest covers 0 to 4). Cache misses need `base_url` of a running server for rebuilding.
- **Open issues:**
  - Clone depth is 100 (not 1) so the append chunks can use git history; recorded in `docs/decisions.md`.
  - The pairs, short points and equivalence checks ran on one server configuration (`-np 1`, 128K). Stock (`-np` auto, 4 slots) and other configs may behave differently; WP9 asserts the same invariants on every cell.
  - Instruction wording reached 400 tokens at every depth here with thinking on; other configs or seeds could still stop early (the `short_gen` flag covers that in the sweep).
  - The live-check file's timings are incidental (the check is not a benchmark and is not used for any speed claim).
  - No test needs the GPU, so none carries the `gpu` marker; the live behaviour is covered by the CLI checks.

---

## 2026-11-09 — WP9: Sweep runner

- **Status:** done. All acceptance criteria pass; CI commands pass locally (535 tests, ruff check and format, shellcheck, `scrub --check` 0 findings in 336 files). One finding needs a decision before WP11 (paging flag, below).
- **Commits:** `273e69f` (`Plan v1.3`), `7385799` (`WP9: apply plan v1.3 rules`), `08be96c` (`WP9: sweep runner`, with the mini-sweep data), then `WP9: progress log` (this entry).
- **Plan v1.3 rules** (`7385799`): idle precondition (busy below 10% over 10 s from `/proc/stat`, re-check every 10 s for up to 10 minutes, wait recorded, load average recorded not gated; tested with a fake `/proc/stat` and clock); paging flag (llama-server major faults above 1,000 or `VmSwap` above zero; system `pswpin` recorded only; telemetry has `server_vmswap_kib`); `accounting` flag from the workload's `expected`.
- **`smallpc.sweep`:** spec expansion (axes, product cells, `@max_fit` / `@n_fit(P1)` tokens, `expect_cells`, `--only context|batch`, seeded dependency-respecting cell order; the Stage 1 sketch expands to exactly 57 cells and `check` fails otherwise); append-only records committed per repetition with batch ids (schema: pydantic `RequestRecord` / `CellRecord`); the §5.3 protocol per server instance; failure handling (`did_not_fit` with reasons, restarts, hung-server stop, precondition retries 3 x 10 minutes); resume with spec, manifest and sampling hash checks and a code-commit warning; max-fit / N_fit probing with a cache; canaries (repetitions 100 and up) and drift; `--rerun-flagged` (attempt 2, never 3, `short_gen` excluded). Design decisions are in `docs/decisions.md` (WP9).
- **Scripts:** `scripts/run-sweep.sh` (spec check, dirty-tree refusal, `systemd-inhibit` pre-test, `run-detached.sh --gpu`), `scripts/sweep-status.sh`. Mock server `tests/fixtures/mock_llama_server.py` (real prefix cache by tokens, streaming, `id_slot`, misbehaviour switches) started by the real launch and stop scripts through a test machine config.
- **Real mini-sweep** (`configs/sweeps/mini.toml`, session `mini-20261109`): stock-32K and `--fit` 8-bit KV 32K, 2 repetitions, 3-repetition canaries at the start and end. SIGINT to the runner while `fit-q8-32K` was in repetition 1 (one cell finished, repetition 0 of the second committed); `--resume` finished it. 61 record lines, all validate, 0 duplicates, 0 torn lines; measured keys 28 of 28 unique; the interrupted cell has a non-final `interrupted` record, then a new server with a new warm-up ran only repetition 1. `systemd-inhibit sleep:idle` was active in both runs (recorded in `session.json`). Idle checks passed first time every time (busy 1.2 to 2.9%; the 1-minute load average was 0.9 to 4.3, which the old gate would have failed). Drift: PP_fresh 16K 1016.3 to 1014.3 tokens/s (0.2%), TG 80.0 to 79.6 (0.6%): no flag. No warm_prefill, cache_miss or accounting flags anywhere, stock included (4 slots, every fresh request on a different slot, every Request B on its own A's slot).
- **Paging flag fired** (4 of 10 repetition windows, 16 of 46 non-warm-up requests): llama-server's own `VmSwap` was above zero in the three canary-start windows (72 to 769 MiB) and in stock-32K repetition 1 (4.2 GiB, 1,692 major faults); the other six windows had none. The machine has zram swap with `vm.swappiness` 150 and about 3 GiB already swapped. The v1.3 rule is working as written, but it will flag many windows here. Needs a decision (options in the report).
- **Time estimate (Stage 1, 57 cells, 2 repetitions):** from the live check with the mini-sweep's measured overheads (14.7 s fixed per cell instead of the assumed 60 s; warm-up 20.1 s), **6.65 h with probing (6.25 h without)**; 7.8 h if the four CPU-expert placements run 1.5 times slower, 8.3 h with cold loads on top. As three sessions: 32K about 1.5 h, 64K 2.3 h, 128K 4.2 h. The plan's 6 to 8 hours holds.
- **Open issues:**
  - Paging flag threshold (above).
  - Only `--fit` and stock ran for real; the cmoe, n-cpu-moe and cache placements, probing against a real GPU and the re-run mode are tested against the mock only. WP11 must read the first logs of P6 to P9 (`placement_check`) and the realized VRAM in the P8 and P9 summaries.
  - The cell records of the mini data have `server_instance` one too high on the final `complete` record (fixed in the code after the run; request records are right).
  - The mini-sweep ran with `--allow-dirty` (recorded in `session.json`); its `git.commit` is `7385799` plus uncommitted code that became `08be96c`.
  - No gap timeout for streams, only the total timeout.

---

## 2026-11-09 — WP10: Analysis and report tooling

- **Status:** done. All acceptance criteria pass; CI commands pass locally (653 tests, ruff check and format, shellcheck, `scrub --check` 0 findings in 1,019 files). Nothing in this WP used the GPU or a server. One decision is waiting for Zack (paging rule, below).
- **Commits:** `9ebc6e1` (`WP10: record decisions`), `dbc7eb9` (`WP10: paging analysis and telemetry columns`), `2c009ff` (`WP10: analysis and report tooling`), then `WP10: progress log` (this entry).
- **Part A, paging (data only; `flags.paging` unchanged):** `data/analysis/paging-mini-20261109.{json,md}`, from `python -m smallpc.paging_analysis`. The telemetry CSV gains `server_rss_anon_kib`, `server_rss_file_kib`, `server_rss_shmem_kib` and (not asked for) `pswpout`; older CSVs load unchanged. Findings, 10 windows, one session, no causal claim: R0 (v1.3), R1 (VmSwap growth above 64 MiB) and R2 (absolute change above 64 MiB) flag **the same 4 windows** (canary-start r100 to r102 and stock-32K r1), and R0 reproduces the recorded flag on 10 of 10 windows. VmSwap was **0 at the first sample of all 5 server instances**, so every flagged window was swap-out *activity* during the window (0 to 71 MiB, 71 to 141, 141 to 751 in the canary-start windows, 0 to 4,146 MiB with 1,692 major faults in stock r1), not a pre-existing flat state; there is no flat-non-zero window, so these data cannot tell R0 from R1 or R2. In stock r1 the swap-out was concentrated in Request A 16K (+3,038 MiB) with the faults spread over the A 16K (604) and A 8K (843) requests; `MemAvailable` never fell below 19,807 MiB in any window (no real shortage; compatible with swappiness 150, not proof). System-wide `pswpin` moved by 1,064 to 59,071 pages per window including windows where the server's own VmSwap was 0, so it says nothing about llama-server. Speed, anecdotal: all 7 requests of stock r1 were slower than the same request in r0 (0.5 to 3.4%; PP_fresh 16K 921.9 vs 937.2, TG 16K 76.5 vs 79.2), but the three flagged canary windows were not slower than the unflagged windows of the same configuration (+0.4% PP, +0.4% TG). Not knowable here: what is in the swapped pages (RssAnon/RssFile/RssShmem were not recorded in this run).
- **Part B:** `stats` (paired_difference, paired_ratio, coverage simulation and `python -m smallpc.stats coverage`), `analysis` (units, attempts, drift, derived metrics), `select` (eligibility, screening shortlist, final tie-break; `python -m smallpc.select`), `sanity` (pure functions), `labels`, `report` (`render`, `coverage`, `repro`). Decisions 1 to 6 are in `docs/decisions.md` ("WP10 decisions") and were committed before any code. Two refinements made while implementing, recorded there: the 8-gram repeat count is non-overlapping (overlapping counts made a 15-token run fail the 8-gram rule), and cells with no resolved configuration (`not_applicable`) have no context and get their own table.
- **Coverage of the intervals** (20,000 simulated experiments per row; `docs/decisions.md`): reported (wider) interval 94.9% / 94.9% (normal, n = 5 / 10), 94.8% / 94.7% (lognormal sigma 0.1), **91.2% / 91.9% (lognormal sigma 0.5), 88.5% / 90.1% (exponential)**; the bootstrap alone 78.5 to 89.9%. The wider interval was the t interval in 100% of samples, so it never over-covers (maximum 94.9%, not conservative). **The asked-for floor of 93% holds for symmetric and mild skew but not for strong skew**; tests assert 93% for the first two and only an 85% regression floor for the strong-skew stress cases.
- **Mini-sweep report** (`reports/functional-test/report.md`, 5 SVGs, `select-screening.{md,json}`), labelled functional-test; byte-identical on re-render. Both stock-32K rep 1 (paging) and the clean `fit-q8-32K` appear, with `fit-q8-32K` alone on the shortlist. All 5 figures were rendered to PNG and inspected; fixes made: truncated title and banner (now wrapped), `predicted_n` label colliding with the error bar, VRAM total label floating above the axes, legend overlapping the x label, x ticks not at the depths.
- **Tests:** a deterministic fixture-session builder (`tests/fixture_session.py`) with the 12 scenarios of the brief; golden report `tests/golden/report-fixture.md` (`UPDATE_GOLDEN=1` regenerates); SVGs checked structurally.
- **Also fixed:** `test_transient_precondition_failures_are_retried_with_pauses` was flaky (it chose a cell summary by `started_utc`, which has 1 s resolution and tied); it now looks at the cell that took three attempts.
- **Open issues:**
  - **Paging rule decision** (Zack): the three rules agree on this data; see the paging paragraph and `data/analysis/paging-mini-20261109.md`. Collect RssAnon/RssFile/RssShmem in the first real session before deciding what swap means.
  - The strong-skew coverage shortfall above; paired-ratio CIs are bootstrap only (narrow at small n).
  - `sanity` and `repro` are tested on synthetic data only; the wiring that produces the sanity JSON (greedy 512-token outputs of the three prompts) is WP12/WP13 work.
  - Paired comparisons match on (session, repetition); cells from different sessions share no pair, and are reported as unpaired.
  - Cache hit rates cover everything a server served (warm-up, all repetitions, both attempts), not only clean repetitions.

---

## 2026-11-09 — WP11 (part 1): Plan v1.4, Stage 1 spec, runbook and pre-flight

- **Status:** done; the three Stage 1 sessions are NOT started (they are Zack's, after G3, one per context). All acceptance criteria pass; CI commands pass locally (680 tests, ruff check and format, shellcheck, `scrub --check` 0 findings in 455 files). One decision is waiting for Zack (P6/P7 max-fit, below).
- **Commits:** `8847d8e` (`Plan v1.4`), `1aacb88` (`WP11: record decisions`), `af24f46` (`WP11: apply plan v1.4 rules`), `c1d080a` (`WP11: stage 1 spec, pre-flight spec and runbook`), `c707742` (`WP11: pre-flight data`), then `WP11: progress log (part 1)` (this entry).
- **Plan v1.4 rules** (`af24f46`): `flags.paging` flags only more than 1,000 llama-server major faults; swap growth is `swap_activity_mib` (with `vmswap_start/end/max_mib` and the RssAnon/RssFile/RssShmem start and end) in `windows[]` and each request's `flag_detail`; new report section "Swap sensitivity" (units above 64 MiB removed, both versions side by side, an explicit verdict; older sessions derive the figure from the telemetry CSV, else "not available"); `stats.paired_ratio` returns the wider of the bootstrap and the t interval on log ratios. Coverage (20,000 experiments, n = 5, sigma 0.05 and 0.2): 94.9% reported against 83.3% bootstrap alone, test asserts at least 93%. `smallpc.select` re-checked against §3.3: no difference.
- **Stage 1 spec:** `configs/sweeps/stage1.toml` expands to 57 cells, 19 per context (`check --only context=...`, new option; the output now has per-axis counts and a per-selection estimate); expansion tests in `tests/test_stage1_spec.py`. `configs/sweeps/preflight.toml`: 10 cells, one repetition, no canary, every cell identical to its Stage 1 cell (test). `docs/runbook-stage1.md`: G3 checklist, the three commands (`stage1-32K|64K|128K`), `--resume` / `--rerun-flagged`, monitoring, recovery, durations, clean-tree rule.
- **Pre-flight** (`preflight-20261109`, 29 minutes, 90 requests): all 10 cells `complete`, no flags, no warnings, swap activity 0 MiB and 0 major faults in every window. `fit` left every explicit placement alone (P6, P7 "no changes needed"; P8, P9 fit off); P3's cache coexists with fit (17 expert layers on the CPU against P1's 15). N_fit from P1's log: 15 at 32K, 18 at 128K (P8 15 and 18, P9 13); P8 uses less VRAM than P1 (14,246 against 14,962 MiB), P9 more (15,176). Max-fit: 12,288 MiB at 32K, 10,752 MiB at 128K in 5 steps each (27 s and 103 s per step); P7 = 12,288 - 2,048 = 10,240. `-b 4096 -ub 4096` works: compute buffer 1,104 against 642 MiB at b2048, 1,349 MiB free.
- **Re-run mode on real hardware:** on a copy of the mini-sweep, `--rerun-flagged` re-ran exactly stock-32K repetition 1 as attempt 2 (plus its own canaries, by design); the first 61 lines of `records.jsonl` are byte-identical, and a second run planned nothing.
- **Findings that differ from the plan's assumptions:**
  1. **Max-fit for P6/P7 is bound by fit's 1,024 MiB margin, not the 512 MiB of §5.4** (probe steps with 589 to 1,101 MiB free were rejected as `fit_intervened`). By WP9's design; the cache sizes are about 512 to 768 MiB smaller than a 512 MiB rule would give. **Zack to decide** whether P6/P7 should use `--fit off` or a lower `--fit-target`; the plan was not changed.
  2. **Stage 1 will take about half the estimated time:** candidate cells run at 40 to 53% of the estimate because `-ub 2048` / `4096` prefill is about 2.3 to 2.8 times faster than the live check's `-ub 512` (decode unchanged). Expected: 32K 0.85 h, 64K 1.28 h, 128K 2.18 h (4.3 h in all; upper bound 5.0 h).
  3. The pre-flight ran with one Chrome tab, Mission Center and the IDE open (agreed with Zack); the idle gate passed every time.
- **Also fixed:** the VRAM breakdown showed the expert cache as "other"; it is now its own part. `data/probes/cache.jsonl` (the two max-fit probes) is committed and will be reused by the real sessions for 32K and 128K at b2048.
- **Open issues:**
  - P6/P7 decision (finding 1). P6/P7's `expert_layers_on_cpu` is not in the placement summary for explicit placements (shown as "-").
  - 64K and the other placements (P2, P4, P5) were not exercised; their times are extrapolated. A cell with `-b 4096` was exercised only for P1 at 32K.
  - The saved `/props` carries only context and slot fields; `n_batch` / `n_ubatch` are read from the startup log.
  - The mini-sweep's old data are unchanged; its flag table in `reports/functional-test` was re-rendered with the v1.4 report.

---

## 2026-11-10 — WP11 (part 2): Stage 1 screening sessions, re-runs and analysis

- **Status:** done. All three sessions ran, coverage is complete (57 of 57 cells `complete`, `report coverage` exit 0, no cell with unresolved flags), the shortlist and report are produced. One gate criterion failed and was accepted as a recorded deviation (128K paging, below); a re-run bug was found and fixed in between. CI commands pass (694 tests, ruff check and format, shellcheck, `scrub --check` 0 findings in 2,416 files).
- **Commits:** `3941bb0` (`Plan v1.5`), `6943239` (`WP11: retire pre-flight probe cache`), `77fbe02` (`WP11: stage 1 conditions log`), `18bd463` (32K data), `47dfc69` (64K data), `dd59e2b` (128K data), `7b800c0` (`WP11: fix re-run with --only and abort-path overwrite`), `60c3bfc` (64K re-runs), `5162e75` (128K re-runs), `061a5bb` (`WP11: Stage 1 analysis`), then `WP11: progress log (part 2)` (this entry). No rendering fix was needed.
- **Sessions** (`stage1-32K|64K|128K`, each from a clean committed tree, `systemd-inhibit` active, no idle waits or precondition retries, drift none, no thermal, accounting, warm_prefill or cache_miss flag anywhere): 32K 0.83 h (estimate 0.85), 64K 1.20 h (1.28), 128K 2.19 h (2.18); 57 of 57 cells complete, no `did_not_fit`. Lowest minimum free VRAM: 485 MiB (P2-32K-b2048, below the 512 MiB line, so ineligible), 547 MiB (P2-64K-b4096), 551 MiB (P2-128K-b4096).
- **Paging flags (attempt 1):** 32K 0 of 38 measured windows; 64K 1 of 38 (stock-64K repetition 1, 1,790 faults, 6.2 GiB swap growth); **128K 14 of 38 (36.8 %)**, all repetition 1, in P1-b2048, P2, P3, P4, P5, P6, P7 (both batches) and stock-128K; none in P1-b4096, P8, P9. Gate criterion f (at most 20 %, a stop rule set for this run, not a plan rule) failed; Zack and the step lead accepted it as a recorded deviation. Windows with swap growth above 64 MiB: 0, 6, 20.
- **Re-run pass** (one `--rerun-flagged` per session): 32K nothing to re-run (no flagged unit; the first attempt of the command was refused by the bug below and made no re-run); 64K 1 unit, 128K 14 units; **15 of 15 attempt-2 units clean** (attempt 2 ran as the first measured repetition of a fresh server). One attempt-2 window (stock-128K) still grew VmSwap by 2,366 MiB (327 faults, no flag).
- **Incident and fix:** the runbook's `--rerun-flagged stage1-32K` was refused (`--only filter differs`: the re-run ignored the session's stored `--only context=32K`) and the refusal overwrote `session.json` and `progress.json` of the 32K session with stubs (restored from `18bd463`; records, events and telemetry were untouched). Both bugs fixed in `src/smallpc/sweep/session.py` (`7b800c0`): the re-run takes the stored filter (a conflicting `--only` is refused), and nothing is written before the session is loaded (`update_session` and `progress` are read-modify-write, an unreadable file is never replaced); 14 new tests in `tests/test_sweep_refusals.py` fail on the old code. Cause of the test gap and the audit of all writers: `docs/decisions.md` "WP11 part 2: re-run mode fixes".
- **Shortlists** (screening, top two eligible by mean T_turn_400, n = 2; stock is a reference only): 32K `P6-32K-b4096` 6.14 s, `P2-32K-b4096` 6.26 s (stock 8.45 s); 64K `P6-64K-b4096` 7.00 s, `P2-64K-b4096` 7.16 s (stock 9.36 s); 128K `P2-128K-b4096` 9.06 s, `P6-128K-b4096` 9.09 s (stock 11.29 s). The top two are within "too close to call at n = 2" in 32K and 128K. Eligible cells: 32K 18 of 19 (P2-32K-b2048 excluded: 485 MiB free), 64K 19 of 19, 128K 19 of 19. Details: `reports/stage1/select-screening.md`, `reports/stage1/report.md`.
- **Probes** (fresh, the pre-flight cache was retired): max-fit cache P6 (P7 = max-fit minus 2,048): 32K 12,288 (b2048, 5 steps, 136 s) and 11,520 (b4096, 99 s); 64K 11,776 (4 steps, 206 s) and 11,008 (179 s); 128K 10,752 (5 steps, 528 s) and 9,728 (388 s). N_fit from P1's log (P8; P9 = N_fit - 2): 32K 15 / 16, 64K 16 / 17, 128K 18 / 20 (b2048 / b4096). P8 used less VRAM than P1 in all six groups (peak 14.2 to 14.7 GiB against 14.9 to 15.0), P9 more (15.2 to 15.6 GiB, minimum free 729 to 1,135 MiB).
- **Swap sensitivity** (report section): at 128K the order of the two fastest candidates flips (`P2-128K-b4096` and `P6-128K-b4096`, already 0.03 s apart) because P2-128K-b4096 loses a repetition with 331 MiB of swap growth, and **no 128K comparison with stock can be formed** (both stock-128K units have swap growth above 64 MiB). 32K shortlist and ranking unchanged; at 64K five cells lose a repetition and their intervals move, the shortlist is unchanged.
- **Diagnostics** (`reports/stage1/diagnostics.md`, `tools/stage1_diagnostics.py`, `data/analysis/paging-stage1-64K|128K`): the host prompt cache (server log `cache state: N prompts, X MiB`, limit 8,192 MiB) accumulates across repetitions (3.8 GiB at the start of repetition 1, 5.7 to 6.9 GiB at its end, against 2.4 to 3.1 GiB at the end of a fresh-server attempt 2); the anonymous footprint at the end of 32 of 32 repetition-1 and attempt-2 windows equals the cache plus 0.8 to 1.0 GiB. Flagged windows had the lowest MemAvailable (17.8 to 19.7 GiB) and lost 1.5 to 8.1 GiB of RssFile. Controls P8/P9 (RssFile 8 to 10 GiB) showed the same cache growth without the flag. Consistent with, not proof of, a host-memory-pressure explanation. The flagged windows are not visibly slower than ordinary repetition-to-repetition differences (T_turn_400 +1.3 % against +1.1 % baseline).
- **Interference** (`docs/stage1-conditions.md`): G3 not met, desktop apps open and idle (names: chrome, claude, antigravity-ide, cosmic-comp; kilo also present at the start). Highest CPU busy in 5 s polls: 19.1 % (32K), 27.2 % (64K), 38.8 % (128K), always antigravity-ide, chrome or this session's own tools; the runner's idle gate (10 s) passed at its first check every time (highest 1.46 %). MemAvailable between polls fell to 20.2 GiB (64K) and 18.1 GiB (128K), never below 24.7 GiB at a precondition check.
- **Open issues:**
  - Paging: the repetition-1 effect is systematic on this machine with the desktop open, not noise; Stage 2 and 3 (5 repetitions, one server per cell) will meet it in every cell with a 20 GiB mapping. Decision for the step lead (a rule change was not made): how repetitions, host prompt cache and desktop memory should be handled.
  - Screening CIs at n = 2 are wide for the expert-cache cells (P3 to P7: repetition-to-repetition TG differences of up to 10 to 15 %, in unflagged sessions too) and t-intervals can go below zero (`T_B` of P4-64K-b4096).
  - Output sanity check not run (allowed in screening); P2-128K-b4096 is shortlisted with 551 MiB minimum free VRAM, 39 MiB above the line.
  - `smallpc.paging_analysis` banner still says "Functional-test data (WP9 mini-sweep)" on the Stage 1 outputs (tool label, not changed); a completed re-run sets `finished_utc` in `session.json` to the end of the re-run.

---

## 2026-11-10 — WP12 (part 1): Plan v1.6, Stage 2 tooling and pre-flight

- **Status:** done; no real Stage 2 session was started. All acceptance criteria pass; CI commands pass locally (848 tests, ruff check and format, shellcheck, `scrub --check` 0 findings in 2,631 files).
- **Commits:** `2fc89c1` (`Plan v1.6`), `9aaf59a` (`WP12: record decisions`), `be53d79` (`WP12: label and finished_utc fixes`), `debe751` (`WP12: stage 2 tooling`), `b852e5b` (`WP12: stage 2 checks and runbook`), then `WP12: progress log (part 1)` (this entry).
- **Part A:** plan v1.6 adopted (line 3 `*Version 1.6 · 10 November 2026*`). `paging_analysis` takes `--label` (Stage 1 outputs regenerated with `screening`; only the banner and note lines changed); a completed re-run writes `rerun_finished_utc` and leaves `finished_utc` alone (tests fail on the old code).
- **Part B (`smallpc.stage2`, `smallpc.sanity run`, `docs/runbook-stage2.md`):** spec generator (2f 6 cells, 2a 15, 2a2 9 or 6, 2b 2, 2c 2, 2d 2 or "not needed", functional-test presets, `configs/sweeps/stage2-2f.toml` generated), decision tool (2f, 2a, 2a2, 2b, 2c, 2d; refuses `allow_dirty`, functional-test spec headers, `ft-` ids and incomplete sessions; provenance in every output), gate (`stage2 gate`), sanity runner, llama-bench wrapper, `stage2 smoke`; `hostcache` moved out of `tools/stage1_diagnostics.py` (output byte-identical).
- **Pre-flight findings** (all functional-test data):
  - `--cache-ram 0` is documented and logged as disabled (no prompt cache, no `cache state` line); 8192 prints the cache state (1,740 MiB after 5 prompts). "Decision models" in the help text are not MTP.
  - MTP at 32K (P6-32K-b4096): max-fit 10,752 MiB against 11,520 MiB without MTP; the MTP head and draft context cost 962 MiB (n = 1) and 1,088 MiB (n = 3) of VRAM; acceptance 80.2% (n = 1) and 52.2% (n = 3); PP_fresh about 9% lower than the Stage 1 cell (anecdotal); no errors in the logs.
  - Sanity runner: P6-32K-b4096 passes against P1-32K-b2048 (47 s).
  - Load mode: alternative to `auto` is `dio` (the model becomes 18.9 GiB of pinned `CUDA_Host` memory instead of 20.4 GiB of evictable file pages); `none` behaves the same but fills the page cache. `mlock` modes are out (8 MiB limit).
  - Threads: the default is 8 in all 82 Stage 1 logs, so 2d is not needed.
  - llama-bench default cell: P2-64K-b4096 (nothing inexpressible, one approximation); 1 repetition takes 175 s.
  - Estimates: Stage 2 about 6.1 h (2f 64 min, 2a 2.4 h, 2a2 1.5 h, 2b 22, 2c 25, sanity 7, 2e 14 min); upper bound 7.1 h.
- **Differences from plan v1.6's assumptions:** the 2a2 anchor and same-session comparators add cells (confirmed by Zack); 2a is about 2.4 h, not 4 h; the cross-check cell is a P2 cell, not P8/P9; P6 with MTP probes about 768 MiB lower; the pinned-memory behaviour of `dio` was not anticipated.
- **Open issues:** (1) 2f combined value across 128K and 64K is the tool's interpretation (smallest; human confirms when they differ). (2) 2c with `dio` pins 18.9 GiB: the machine may be short of memory for the desktop apps; the paging table will show it. (3) The probe step count for MTP at 64K is assumed (5). (4) `--rerun-flagged` must not run before the 2f decision.

---

## 2026-11-10 — WP12 (part 2a): Stage 2f session (host prompt cache)

- **Status:** 2f session run and decided; stopped at the checkpoint for the step lead (no 2a spec generated, the decision was not applied to anything).
- **Commits:** `7b7daf1` (`WP12: stage 2 conditions log`), `6f246cb` (`WP12: Stage 2f session data`), `de4e611` (`WP12: Stage 2f decision`), then `WP12: progress log (2f)` (this entry).
- **Session `s2f`** (13:22:09Z to 14:26:03Z, 63.9 min against the 64 min estimate): 6 of 6 cells complete, `systemd-inhibit` active, one attempt per unit, no idle waits or precondition retries, drift none (+1.2 % PP_fresh 16K), no thermal, accounting, warm_prefill or cache_miss flag. Gate PASS (a to e; f not applied to 2f). Paging-flagged windows (attempt 1): 128K cram 8192 2 of 5 (reps 1, 2), 4096 1 of 5 (rep 1, 1,202 faults), 2048 0, 0 0; 64K cram 8192 3 of 5 (reps 2, 3, 4; up to 159,451 faults), 2048 0.
- **Decision (tool output):** `status: decided`, chosen `--cache-ram` **2048**; no human decision needed.
  Both contexts choose 2048 (128K: mean T_turn_400 -0.62 % against the 8192 cell's clean units; 64K: -4.18 %, limit +3 %).
- **Conditions** (`docs/stage2-conditions.md`): G3 not met, desktop apps open and idle (antigravity-ide, chrome, claude, cosmic-comp, kilo, spotify); the runner's idle gate read 0.49 to 1.54 % before every cell; one 5 s poll sample of 32.1 % CPU at the start of a cell (cause not identified); lowest MemAvailable 15.7 GiB (telemetry, 8192 cell), 16.3 GiB at a poll.
- **Open issues:** the tool's 3 % comparison is unpaired and uses the 8192 cell's clean units (3 of 5 at 128K, 2 of 5 at 64K); the same-repetition paired differences are -0.75 % (128K) and -0.31 % (64K), so the decision does not depend on it. The chosen 2048 cells are "clean" by threshold, with repetition-1 fault counts of 889 (128K) and 828 (64K) against the limit of 1,000 and 450 to 548 MiB of swap growth. `--rerun-flagged` was not run.

---

## 2026-11-10 — WP12 (part 2b): stopped at the Stage 2a 64K gate (criterion f)

- **Status:** **stopped early** by the continuation's stop rule. Done: the 2f decision recorded, the 2a spec, sessions `s2a-32K` and `s2a-64K`. Not done: `s2a-128K`, any re-run, `decide --stage 2a`, 2a2, 2b, the sanity check, 2e, the wrap-up checks and the Stage 2 report. Nothing was decided and no tool or config was changed.
- **Commits:** `5c3eef8` (`WP12: record 2f decision`), `37040a8` (`WP12: stage 2a spec`), `60edde1` (32K conditions), `5a53bbe` (`WP12: Stage 2a 32K session data`), `f0ae746` (`WP12: stage 2a 64K conditions`), `455eb57` (`WP12: Stage 2a 64K session data (gate criterion f failed ...)`), then `WP12: progress log (2a stop)` (this entry).
- **Spec:** `python -m smallpc.stage2 spec --stage 2a --from-2f data/analysis/stage2/2f.json` (the continuation also named `--cache-ram 2048`; the tool refuses both together, `--from-2f` already yields 2048 and the spec sets `cache_ram = 2048` in `[defaults]`). 15 cells (32K and 64K: P6 at mtp0 to mtp3 and P2 at mtp0; 128K: P2 at mtp0 to mtp3 and P6 at mtp0).
- **Sessions:** `s2a-32K` 31.2 min (estimate 32), 5 of 5 cells complete, 4 of 25 windows paging-flagged (16.0 %), gate PASS. `s2a-64K` 46.5 min (estimate 47), 5 of 5 cells complete, **6 of 25 windows paging-flagged (24.0 %), gate criterion f FAIL**. No accounting, warm_prefill, cache_miss, thermal, drift or did_not_fit anywhere; inhibit active; no idle waits or retries.
- **Flagged windows:** 32K P6-mtp1 repetitions 2, 3, 4 (8,296, 1,243, 1,683 faults) and P6-mtp0 repetition 4 (1,697); 64K P6-mtp1 repetitions 2, 3, 4 (20,153, 16,162, 18,550) and P6-mtp2 repetitions 2, 3, 4 (51,759, 4,687, 13,247). None in P2 cells, in mtp3, or in repetitions 0 and 1 (mtp0 at 64K: none). Swap activity of the flagged windows was -295 to +58 MiB (the host cache stayed at 1.3 to 1.9 GiB); several lost 0.2 to 1.5 GiB of RssFile; MemAvailable stayed at 21.1 GiB or more. This differs from the 2f picture (swap growth and cache growth), and was not explained.
- **Open issues:** the step lead decides how to continue (the continuation says the 2f choice did not hold; the fallback `--cache-ram 0` is the step lead's decision, `--rerun-flagged` and `decide` were not run for either 2a session).
