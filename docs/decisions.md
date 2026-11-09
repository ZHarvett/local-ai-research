# Decisions

Decisions are recorded with date and source. Source section numbers refer to
`docs/plans/step-0-baseline.md` (v1.2).

## Fixed decisions (§4)

| Topic | Decision |
|---|---|
| Model | Ornith-1.5-35B-A3B, one Q4-class GGUF (Q4_K_M or UD-Q4_K_XL). Primary: official `ornith-ai/Ornith-1.5-35B-A3B-GGUF` Q4_K_M at a revision on/after 2026-08-23 (MTP weights update). Fallback: `bartowski/Ornith-1.5-35B-A3B-GGUF` Q4_K_M, only with Zack's approval. No quant sweep. |
| Engine | Mainline llama.cpp, newest release tag at build time (b12017 or later), pinned by commit. CUDA, `CMAKE_CUDA_ARCHITECTURES=120`. |
| Harnesses | Control: OpenCode, exact version pinned. Research: dsh, exact version pinned (CLI and plugins). |
| Languages | Bash for launch/long-job scripts; Python via uv for everything else; TOML configs. |
| Repo | Umbrella repo `ZHarvett/local-ai-research`, private until release, on the 256 GB SSD. Claude Code may push; Zack makes it public and publishes releases. |
| Licenses | MIT for code; CC BY 4.0 for data, report and write-up. Copyright holder: ZHarvett. |
| Write-up | GitHub only: "What a 16 GB GPU actually does with a 35B MoE model". |
| Storage | Repo, models and data on the 256 GB NVMe SSD. ~90 GB available per plan; Step 0 needs ~30 GB. |
| Display | Both monitors on motherboard outputs (iGPU); the RTX 5060 Ti runs no display clients. |
| Machine tuning | Frozen for the whole project and recorded with every run; any change triggers a canary re-check. |
| Long jobs | Claude Code may start them, always detached via `scripts/run-detached.sh`, logged, lock-protected, resumable. |
| sudo | Never run by Claude Code. Claude Code proposes exact commands; Zack runs them. |

## Confirmed decisions, 6 Nov 2026 (§11)

1. **Repo:** `ZHarvett/local-ai-research` on the 256 GB SSD, with `models/` inside it (gitignored).
2. **LICENSE copyright holder:** ZHarvett.
3. **Selection rule and turn workload:** §3.3 approved; the 3,000 + 400 turn of §3.4 is a standardised
   benchmark workload, not a model of real agent use. `predicted_n` is recorded for every run; the
   estimated 400-token turn (T_turn_400) is kept separate from measured times (T_B).

## WP0 decisions (2026-11-07)

### Repository location: `/mnt/data/local-ai-research`
- **What:** the repo lives at `/mnt/data/local-ai-research`.
- **Why:** `/mnt/data` is the mount point of `/dev/nvme1n1p1` (SK hynix BC711 NVMe, 238.5 GiB ≈ 256 GB,
  btrfs), the only ~256 GB drive. The OS drive is `nvme0n1` (WD Green SN3000, 500 GB; `/` and `/home`).
  `/mnt/data` is owned by `<user>:<user>` (mode 755), so no sudo was needed.
- **Note:** the btrfs mount uses `compress=zstd:1`; incompressible model files are unaffected, but
  keep it in mind when interpreting disk-throughput microbenchmarks (WP6).

### Plan source files
- Plans were read from `~/Downloads/` (a symlink to `/mnt/data/downloads`) because
  `~/Downloads/local-ai-research/` did not exist: `local-ai-plan.md` -> `docs/plans/project-plan.md`,
  `step-0-baseline-v1.2.md` -> `docs/plans/step-0-baseline.md` (the only step-0 version present).

### Provisional `.gitignore` names
- Raw logs: `data/logs/*/` (per-run directories written by `launch-server.sh`) and `*.log`;
  compressed, scrubbed logs under `data/logs/` stay committable.
- Harness state: `.harness-state/`, plus `third_party/` (per §8). Revisit when WP7 fixes the
  OpenCode state dir and `DSH_HOME` locations.

## G1 decisions (2026-11-07)

### Ollama disabled for the duration of the project
- **What:** Zack ran `sudo systemctl disable --now ollama`. `ollama.service` is now inactive and
  disabled; the packages (`ollama`, `ollama-cuda`) remain installed and untouched.
- **Why:** to keep background GPU use out of the measurements.
- **Source:** done by Zack at gate G1; confirmed by `systemctl is-active` / `is-enabled` on 2026-11-07.

### Manual BIOS fields (recorded in `docs/environment.md`)
- EXPO enabled, 6000 MT/s configured speed confirmed by `dmidecode -t memory` (run by Zack).
- iGPU: set by Zack in the BIOS (Gigabyte): Settings > IO Ports > Integrated Graphics = Forced, Initial Display Output = IGD Video, UMA Mode = Auto; both monitors on the motherboard outputs (WP4 update, see "Desktop GPU steering").
- PBO/Eco mode: BIOS default, never changed by Zack; exact mode not recorded.

## WP3 decisions (2026-11-08)

### Desktop GPU steering (apps prefer the iGPU)
- **What:** after WP2 (2026-11-07) and before WP3 (2026-11-08) Zack moved both monitors to the
  motherboard (iGPU) outputs and changed the BIOS so the iGPU is the primary display adapter. WP3
  could not identify how; Zack explained it in WP4 (below). The exact date/time was not recorded.
- **Mechanism (WP4, from Zack):** a BIOS setting, not a software one. On the Gigabyte board:
  Settings > IO Ports > Integrated Graphics = Forced, Initial Display Output = IGD Video,
  UMA Mode = Auto. Zack rebooted to apply it ("I just rebooted my PC to change the setting to start
  working here"). This agrees with the WP3 read-only search, which found no GPU-selection variable
  or setting in the user session, systemd or `/etc` (`DRI_PRIME`, `__NV_PRIME_RENDER_OFFLOAD`,
  `__GLX_VENDOR_LIBRARY_NAME`, `VK_ICD_FILENAMES`, `VK_DRIVER_FILES`, `MESA_VK_DEVICE_SELECT`,
  `WLR_DRM_DEVICES`, `AQ_DRM_DEVICES`, EGL vendor; `~/.config/environment.d` absent; the only
  recently modified file, `~/.config/cosmic/com.system76.CosmicPortal/v1/screenshot`, is unrelated).
- **Observed effect:** cosmic-launcher and Xwayland hold the iGPU render node (renderD129, amdgpu);
  cosmic-comp holds the nodes of both GPUs. DRM card numbering moved (card0/card1 at G1, card1/card2
  now), so nothing may depend on `cardN` numbers.
- **VRAM still used (2026-11-08):** 2 MiB of 16311 MiB (`nvidia-smi --query-gpu`). No process holds a
  context on the card: `--query-compute-apps` is empty and the graphics-process section of
  `nvidia-smi -q` reads `Processes: None`. cosmic-comp, cosmic-workspaces and Mission Center have
  `/dev/nvidia*` open but no VRAM allocation. For comparison: G1 had 514 MiB used with 8 desktop
  processes holding contexts, and Zack saw about 371 MiB right after the change. This closes the G1
  open item (desktop contexts on the dGPU) for the current state; it drifts with desktop activity,
  so every measured run's environment snapshot records `memory.used` and the process list.
- **How to undo (description only, not run):** reboot into the BIOS and set Settings > IO Ports >
  Integrated Graphics back from Forced (to Auto), Initial Display Output from IGD Video back to the
  PCIe/discrete-card entry, and UMA Mode back to its previous value; then plug the monitors back
  into the RTX 5060 Ti. Zack did not record the previous values, so the originals are unknown and
  must be confirmed in the BIOS. The desktop then shows on the RTX 5060 Ti again (the pre-G1 state).
- **Games:** the RTX 5060 Ti is still present as a render device. Which GPU a given game defaults
  to was not tested; if one picks the iGPU, a per-application launch option (for example the PRIME
  offload variables) selects the RTX 5060 Ti.
- **Status:** this state is part of the frozen machine tuning (step plan section 4). Any change to it
  triggers the short re-check (the canary set).

### Flag table verified against build b12208
- All 22 flags in `FLAG_TABLE` exist in `llama-server --help`; none needed renaming, so the golden
  argv files are unchanged. Widened to what the build accepts: `spec_type` (11 values including
  `draft-mtp`), `load_mode` (`auto, none, mmap, mlock, mmap+mlock, dio`), `log_verbosity` 0-5.
- Build choices: newest b-tag built (b12208); upstream's newest semver tag
  (v0.9.0) is recorded in `build-info.json` only; CMake rewrote `CMAKE_CUDA_ARCHITECTURES=120` to `120a`.

## WP4 decisions (2026-11-08)

### Model revision
- Official repo `ornith-ai/Ornith-1.5-35B-A3B-GGUF`, file `Ornith-1.5-35B-Q4_K_M.gguf` (21,713,463,040
  bytes). Pinned to commit `f60452672689e0040be350560267a614cc172a18` ("Upload
  Ornith-1.5-35B-Q4_K_M.gguf", 2026-08-24 03:38:27 UTC): the newest commit that changed the file's
  content (LFS sha256 `ca6ea263...` before it, `42739874...` at it and in every later commit, checked
  at all 17 commits). Dated after the required 2026-08-23. The repo also has BF16, Q5_K_M, Q6_K, Q8_0
  and an mmproj file; none were downloaded. There are no separate MTP files: the head is `blk.40.*`.
- Downloaded with huggingface_hub 2.4.0 (`uvx --from huggingface_hub==2.4.0 hf download ...`,
  `--local-dir models/`), `HF_HOME` pointed into `models/.hf-home` so nothing went to
  `~/.cache/huggingface`. uvx's own tool environment is cached by uv under `~/.cache/uv` (uv's normal
  cache, as for the project environment).
- Base repo: the GGUF card has no `base_model` field. `ornith-ai/Ornith-1.5-35B-A3B` was taken from
  the card's `license_link` and chat-template link; pinned at its newest commit
  `10fbf86fed7ecee4a061f8b499a618f46001cac1` (2026-08-23). The base README differs from the GGUF
  README only by one blank line and the trailing newline.
- License: `mit` (card front matter). Its `license_link` points to a LICENSE file in the base repo
  that is not in that repo's file list.
- Sampling: the card gives two settings (general tasks: temperature 0.6, top_p 0.95, top_k 20;
  benchmark reproduction: temperature 1.0) and nothing for thinking vs non-thinking or coding. Both
  are recorded verbatim; the base `generation_config.json` (1.0 / 0.95 / 20) is recorded separately.

### Embedded chat template differs from the official one (decided in WP5, see below)
- `gguf_check` compared the GGUF's `tokenizer.chat_template` with the official base-repo template
  after whitespace normalisation: **not identical** (7828 vs 7536 bytes, 18 changes). The embedded
  one is a modified variant marked `Unsloth fixes - developer role, tool calling`: it accepts the
  `developer` role, merges the first two system/developer messages, renders tool-call arguments
  differently (`tojson | safe` for mappings and sequences) and no longer raises on an unexpected role
  or a system message that is not first.
- llama-server uses the embedded template unless `--chat-template-file` is given, and the plan fixes
  stock configs to the section 3.1 flags. Nothing was changed. To decide before WP5/WP7: measure with
  the embedded template (what a user gets), or point all configs at the official file
  (`configs/model/chat_template.jinja`) and say so in the report. This affects how the harnesses'
  system prompts and tool calls are rendered, so it must be the same in every stage.

### One-off load check (exception to "llama-server only through launch-server.sh")
- Run by absolute path through `scripts/run-detached.sh --gpu` (GPU lock), port 8191, `-ngl 0`,
  `-c 2048`, `--fit off`, `--no-warmup`, `--check-tensors`, stopped with SIGINT. Exception recorded as
  required by the WP4 prompt; no other server was started.
- Load 1 (the specified command): loads and listens, but every `blk.40.*` tensor is reported as
  "unused tensor ... -- ignoring" because MTP is not enabled, so the loader does not load or validate
  the head. Load 2 repeated it with `--spec-type draft-mtp` (a deviation, to cover the head): no
  unused-tensor warnings, an MTP draft context is created, no errors.
- What `--check-tensors` validates (source, `llama-model-loader.cpp` / `ggml-quants.c`): for each
  loaded tensor, `ggml_validate_row_data`; for the quantized types this checks the fp16 scales
  (NaN/Inf) and float tensors for NaN/Inf, not the quantized integers. A failure prints
  `ggml_validate_row_data: found nan/inf value ...` and aborts with "tensor ... has invalid data".
  Neither appeared. No negative control was run.
- nvidia-smi `memory.used`: before 2 MiB, load 1 up 422 MiB (process 412 MiB), load 2 up 698 MiB
  (process 688 MiB), after SIGINT 2 MiB. Excerpt: `data/health/load-check-excerpt.txt`.

## Open items (added in WP4)

- **WP14:** before the repository is made public, scan the whole git history (all commits, all
  files) for the hostname, home paths and username. An early commit contains the account name.
  Report any findings to Zack for a decision. Rewriting history changes the commit hashes recorded
  in the progress log, so Zack decides whether to rewrite or accept.
- **WP12:** the plan assumed `--load-mode auto (mmap)` vs `none`. The built llama-server accepts
  auto, none, mmap, mlock, mmap+mlock and dio. Before Stage 2c, read the exact meaning of each from
  `llama-server --help` and the source, and choose the comparison accordingly.

## WP5 decisions (2026-11-08)

### Chat template: the embedded template, everywhere
- **Decision:** all Step 0 work uses the chat template embedded in the GGUF, with no
  `--chat-template-file`, in every stage and every config (stock, candidate, tuned, health).
- **Reasons:** stock means what a typical user runs, and the official GGUF ships this template.
  It must be identical across all configs, so no config may point at `configs/model/chat_template.jinja`.
- **Exact differences from the official template** (whitespace-normalized comparison, 18 changes,
  7828 vs 7536 bytes; the full diff is `chat_template.diff` in `data/health/model-check.json`). The
  embedded one is the "Unsloth fixes - developer role, tool calling" variant:
  - it accepts the `developer` role;
  - it merges the first two system/developer messages into one;
  - it renders tool-call arguments differently (`tojson | safe` for mappings and sequences);
  - it does not raise on an unknown role or on a system message that is not first.
- **Check "template hash matches WP4":** the template that `/props` reports, whitespace-normalized
  (all whitespace runs collapsed to one space, stripped, UTF-8) and SHA-256 hashed, must equal the
  hash of the embedded template. `model-check.json` stores only `identical = false` and the diff, not
  the embedded hash, so `smallpc.health` computes it from the GGUF with the same normalization
  (`smallpc.gguf_check.normalize_template`) and reports it next to the official hash from
  `configs/model.toml` (`1575085b3cc2373cf3c2e0ec5cd075aa30581e9c3b9c36d33c17859fd2039b0c`).
- **Note for the executive chat:** Step 1 and Step 2 must decide which template to use for task
  success and for the prefix-cache doctor, because the template may affect tool-call behaviour
  (argument rendering, role handling). Step 0 numbers are for the embedded template only.

### Base repository
- `ornith-ai/Ornith-1.5-35B-A3B` is confirmed as the base repository. The GGUF card has no
  `base_model` field, and that is accepted.

### Manual BIOS fields updated
- The previous values in `docs/environment.md`, `configs/machine.toml` and `scripts/inventory.sh` were
  stale. Now: iGPU = Integrated Graphics "Forced", Initial Display Output "IGD Video", UMA Mode "Auto",
  set by Zack in the BIOS around 2026-11-08 (exact date unknown, previous values unknown). EXPO =
  enabled, and Zack re-checked it after the BIOS change: `dmidecode` shows 6000 MT/s configured speed.
  PBO/Eco mode is still "BIOS default, not recorded". `inventory.sh` was edited but not re-run.

## WP6 decisions (2026-11-08)

### Hit-rate collection: every sweep cell runs with `-lv 4`
- **Decision:** every sweep cell, stock included, runs with `-lv 4` (`log_verbosity = 4`).
- **Reasons (WP5):** the expert-cache statistics line is printed at clean shutdown only at `-lv 4`.
  It covers decode-sized batches (ubatch <= 8) with hits, misses and a hit rate; prefill-sized
  batches print no hit/miss line, only a count of experts copied from the cache. The fit trace and
  buffer sizes also appear only at `-lv 4`. The `-lv 4` vs default A/B gave +0.61% decode speed,
  which is not a measurable cost. Logging does not change inference, and plan section 3.1 allows it.
- **Limitation (WP9 and the report must state it):** hit rates in the sweeps are decode-batch hit
  rates plus the large-batch copy counts. There is no prefill hit rate.

### For the executive chat
- **Chat template** (recorded in WP5 above): the embedded template is used throughout Step 0; Steps 1
  and 2 must decide which template to use.
- **MTP with `-np 2`** is accepted on b12208 (2 slots of 32768 at `-c 65536`, both drafting), so the
  single-slot constraint behind the Step 4 and 5 designs does not apply, but the context is split
  between the slots.
- **MTP draft state across restore:** on b12208 neither slot-file restore nor prompt-cache restore
  lost the MTP draft state (equal `draft_n` and `draft_n_accepted` at 181 and 3191 tokens of history,
  and the log shows the draft state saved and restored). Caveats: no negative control, no history
  above 8192 tokens. llama.cpp #28619 may already be fixed; Step 3b and Step 5 should verify it.
- **Context checkpoints** are created at prompt ends at any length, not only above
  `--checkpoint-min-step`; the WP5 plan's premise was wrong. The turn-3 restore still used no checkpoint.
- **MTP acceptance source:** it was measured on llama.cpp's own source code, which the model may have
  seen in training, so rates on unseen code may be lower. Stage 2a re-measures on the WP8 workloads.

## WP7 decisions (2026-11-08)

### Smoke tests run against the stock server
- **Decision:** both smoke tests start `configs/server/examples/stock-64k.toml` through
  `scripts/launch-server.sh`. OpenCode with its defaults is the stock harness, and later steps compare
  against stock.
- **Recorded at run time from `/props`:** `total_slots`, the top-level `n_ctx`, the per-slot
  `default_generation_settings.n_ctx` and the kv-unified setting. The stock default is `-np` auto,
  so the slot count and the per-slot context are whatever the server reports, not assumed.
- **Harness context:** `limit.context` (OpenCode) and `contextWindow` (dsh) use the **per-slot**
  value, not the total `n_ctx`, wherever the two differ. `limit.output = min(16384, per_slot_ctx // 4)`.
  Reasons: `max_tokens` is only a ceiling, a small value could cut off a long thinking pass, and
  OpenCode subtracts it from the context when it decides to compact.

### The smoke request pattern is smoke-task data
- It shows how each harness behaves on a tiny task (for example extra title requests). It is not
  representative of real agent turns and does not revise the 3,000 + 400 turn (step plan 3.4).
  `data/harness/request-pattern.json` carries that label.

### Harness version pinning rule
- **Rule:** use the version the `latest` dist-tag points to at install time, unless it was published
  less than 7 days before. Then use the newest version that is at least 7 days old and say so
  (a newly published release can carry malicious code before anyone catches it).
  "Newest" is read as newest by publish time. dsh's plugins get exactly the dsh CLI version (plugin
  dist-tags are unreliable). A plugin without a release at that exact version stops the work.
- **Whole dependency tree:** the install runs with `npm install --ignore-scripts --before=<UTC
  timestamp exactly 7 days before the install>`. Every package in the lockfile is then checked against
  registry publish times, and any published less than 7 days before the install gets an `overrides`
  entry pinning an older version, repeated until none are left. The result is recorded in
  `configs/harness.toml` and appended below once the install is done. A package with no version at
  least 7 days old stops the work.
- **Package choice (Zack, 2026-11-08):** OpenCode is `opencode-ai` (legacy 1.x line), as the step plan
  says, not `@opencode/cli`, which the current README names. `npm view opencode-ai deprecated` was
  empty and `latest` points to `opencode-ai` itself.

### Isolation additions
- Every execution of a harness binary, `--help` and `--version` included, goes through
  `scripts/_sandbox.sh`: bubblewrap (`/home` and `/tmp` as tmpfs, only the scratch copy and
  `third_party/harness-state` writable) plus an isolation environment (`HOME`, `XDG_*`, `TMPDIR`,
  npm user and global config all repo-local). Informational commands also get `--unshare-net`. If
  bubblewrap fails, work stops; there is no environment-only fallback.
- Network behaviour is observed with a local logging proxy. A proxy cannot see traffic that ignores
  the proxy settings; if the control run shows no attempt, network behaviour is reported as
  "not verified".

### WP7 results recorded after the install and the smoke runs (2026-11-08)
- **Whole-tree 7-day rule (result):** installed with `--before=2026-11-01T18:25:11Z` (install
  2026-11-08T18:25:11Z). The final lockfile has 643 distinct name@version pairs; **none** was published
  after the cutoff (newest: `http2-wrapper@2.2.4`, 2026-11-01T11:29Z), so no `overrides` were needed.
  The checker was proven with a positive control (a later cutoff lists AWS SDK packages). Evidence:
  `data/harness/lockfile-ages.json`, `configs/harness.toml [age_check]`.
- **Pins:** `opencode-ai` 1.19.5 (the `latest` tag, 11 days old) and `@deepseek-ai/dsh` 0.2.1-rc.5
  (`latest` was `0.2.2-rc.1`, 4 days old; "newest" read as newest by publish time). 295 `@deepseek-ai/dsh-*`
  packages in the tree, all at 0.2.1-rc.5.
- **Install scripts:** npm 12 blocks dependency install scripts unless `allowScripts` in `package.json`
  approves them. Only `opencode-ai@1.19.5` (its postinstall hard-links the platform binary) is approved
  and was run, offline. `node-pty`, `koffi`, `@google/genai`, `protobufjs` and
  `@deepseek-ai/dsh-subprocess-local` stay blocked; dsh runs without them.
- **Smoke server config:** the first OpenCode run used `stock-64k.toml` exactly. At default log
  verbosity llama-server does not log the prompt length, so `cache_n` could not be derived. The
  committed request pattern comes from re-runs with `configs/server/smoke-stock-64k.toml` = stock-64k
  plus `log_verbosity = 4` (a logging flag, allowed by 3.1 and already used for every sweep cell by the
  WP6 decision; a test pins the difference to that one field). Both runs are kept.
- **Stock server in /props:** `total_slots = 4`, `kv_unified = true`, per-slot
  `default_generation_settings.n_ctx = 65536`, no top-level `n_ctx`. So the per-slot and total context
  do not differ here, and `limit.context = 65536`, `limit.output = 16384`.
- **Environment switches** (OpenCode): `OPENCODE_DISABLE_AUTOUPDATE`, `_MODELS_FETCH`, `_DEFAULT_PLUGINS`,
  `_LSP_DOWNLOAD` = 1. No switch exists for the unconditional background install of
  `@opencode-ai/plugin`; the deny-all proxy refuses it. (dsh): `DSH_TELEMETRY_MODE=DISABLED`,
  `DSH_PERMISSION_MODE=workspace-write`, a placeholder `DSH_LOCAL_API_KEY`, web tools disabled in the
  profile patch.
- **Sandbox goes beyond the amendment:** dsh's own permission settings do not restrict bash network
  access or `/tmp` (probed), so the smoke runs also use a private network namespace with only the
  server and the proxy bridged in (`_sandbox.sh --bridge`, `smallpc.netbridge`). OpenCode runs in the same.
- **A denied tool call does not fail a smoke run; a permission prompt does.** (The plan text said both.)
  Denials are counted and reported. In `opencode run` a prompt is auto-rejected ("permission requested;
  auto-rejecting", probed), never approved, and never hangs.

## WP8 decisions (2026-11-08)

### For the executive chat
- **Title request and slots.** In both harnesses (WP7 smoke runs) the title request ran on a different slot
  from the main loop, because stock uses 4 automatic slots. Candidate configs use `-np 1`, so the title
  request would share the main slot and could disturb cache reuse; Step 2 should test this.
- **OpenCode package.** The current OpenCode docs name `@opencode/cli`, not `opencode-ai`. Step 1 or 2 should
  decide whether to move, since the config schema differs.
- **OpenCode and npm.** OpenCode always tries to fetch a plugin package from npm at startup and has no switch
  to stop it; the private network namespace blocked it and OpenCode carried on.

### K = 1024 tokens
- In the workloads, K is 1024 tokens throughout: 2K = 2,048, 8K = 8,192, 16K = 16,384, 24K = 24,576,
  32K = 32,768, 48K = 49,152, 64K = 65,536, 96K = 98,304.

### Variant policy
- Repetition r uses variant `r mod 5`. The 2-repetition screening therefore uses variants 0 and 1, and a
  5-repetition run uses all five.

### WP8 workloads: sources, design and findings (2026-11-08)

**Source repositories** (`configs/workloads/recipe.toml`, `configs/workloads/manifest.json`). Both are
public, one per language, neither is llama.cpp nor this repository. The license is the text read from the
clone, not the GitHub label.

| | Python | Rust |
|---|---|---|
| Repository | `python-poetry/poetry` | `tokio-rs/axum` |
| Pin (release tag, full commit) | 2.5.1, `94b6e35b9091991887aa54feeb3771a86d3bd692` | `axum-v0.8.9`, `c59208c86fded335cd85e388030ad59347b0e5ae` |
| License (SPDX) | MIT (root `LICENSE`, SHA-256 `1786f071a510648a24695f295117f02bae0bbf0fb7c6730aafe9c93a3e4bf7ee`) | MIT |
| License file(s) | `LICENSE` | no root `LICENSE` at this tag; one per crate: `axum/LICENSE` SHA-256 `6a13bc24a100a6812f053879ec51b126b103af7cda6dbf48c4188722da44da9f` (primary); `axum-core`, `axum-extra`, `axum-macros` `LICENSE` all `2c417b11aaf663ec7cbc8c8127afd748bfbb4de78df864395866897daaca71fa` |
| Hand-written tokens (`/tokenize`) | 645,819 in 309 `.py` files | 346,356 in 256 `.rs` files |
| Excluded | 77 files in excluded directories (`fixtures`, `docs`, ...), 65 by size | 40 by size (under 200 bytes) |
| Shallow clone | depth 100, 17 MB | depth 100, 4.0 MB |

- The four axum license files are all MIT text but are **not byte-identical** (different copyright line and
  line wrapping), so the plan's "assert they are equal" was replaced by recording every hash and verifying
  each in `verify`. SPDX id `MIT` was read from the license text itself.
- Both repositories are popular public code the model may have seen in training; MTP acceptance and other
  content-dependent numbers measured on them need the same caveat as the WP5 llama.cpp-source figures.
- **Clone depth 100, not 1** (deviation to flag): depth 1 has no history, so `git log --stat` and
  `git diff HEAD~N HEAD` could not be used for the append chunks. Clones are in the gitignored
  `third_party/workload-sources/`. Nothing else was downloaded.
- Eligibility rules (recipe `[exclusions]`): extension, no vendor/fixtures/generated/build directories,
  200 to 200,000 bytes, UTF-8 without NUL or CR, no generated-file marker, no line over 1,000 characters.
  Pools: files sorted by size into six disjoint pools (variants 0 to 4 plus a reserve pool for warm-up,
  equivalence and sanity prompts), then shuffled with a fixed seed. Pool sizes: poetry about 107.6K tokens,
  axum about 57.7K tokens each (the 96K prompt needs about 49K per repository).

**Special-token strings (Zack's amendment).** A source file or command-output line that contains a literal
control-token string would turn into a control token when prompts are tokenized with special tokens parsed.
The strings are read from the model's vocabulary (GGUF `tokenizer.ggml.tokens` with `token_type` control or
user-defined: 33 candidates), then kept only if `/tokenize` turns the string into one token with special
parsing on and into something else with it off (27 strings; list and SHA-256 `f63d81b1cce154fe...` in the
manifest). Files and command-output lines containing one are excluded; a second guard rejects any file whose
token count differs between the two parsing modes. In the real sources no file was excluded for this reason
(a test with a fake file proves the exclusion works).

**Token accounting (Zack's amendment).** `prompt_n` counts tokens processed and `cache_n` tokens reused.
Invariants: Request A `prompt_n + cache_n == d` and `cache_n <= 32`; Request B
`prompt_n + cache_n == d + 3000` and `cache_n >= 0.95 d`; the equivalence check compares `prompt_n` of the
string and token-array requests. Any other result is a finding and no threshold is adjusted. The WP9
interface carries them as `expected.processed_plus_cached`.

**Committed data holds no text (Zack's amendment).** `data/workloads/live-check-<date>.json` and the manifest
contain counts, token ids, hashes, stop types and timings only; a test rejects any string over 200
characters. Instruction wording is kept in `recipe.toml` and referenced from the manifest by id and SHA-256.

**Design as built.**
- Prompt: `<|im_start|>system\n{nonce}\n{system prompt}<|im_end|>\n<|im_start|>user\n{files}\n\n{instruction}<|im_end|>\n`,
  plus the generation prompt `<|im_start|>assistant\n<think>\n` for single-turn kinds (short points, warm-up,
  sanity, equivalence). Request A has no generation prompt. Thinking stays at the template default (on).
  Files alternate by repository section (first half poetry, second half axum), so both appear at every length.
- Request B appends, for exactly 3,000 tokens including wrapper and generation prompt: an assistant stub,
  a `tool` message with tool-like output from git commands (`git log --stat`, `git diff`, `git grep -n`,
  `git ls-tree -r -l`), a final user instruction, then the generation prompt. The rendering was taken from the
  server's `/apply-template`; A's tokens are an exact prefix of B's (checked per pair against the real
  renderer and by tokenizing B whole).
- Nonce `[nonce <16 hex>]` is the first text in the system message, derived from `sha256(seed|kind|variant|length|repetition)`.
  Packing always runs on the complete text, so the nonce's token cost (it varies) cannot change the length.
  The manifest covers repetitions 0 to 4 (variant = repetition); larger repetitions are built on demand.
- BOS: the GGUF has `add_bos_token = false` (BOS id 248044), so token arrays and string prompts carry no BOS;
  the code prepends and counts it if a model sets it.
- Live-check server: `configs/server/workload-check-128k.toml` (candidate profile, 131072 context, `--fit on`,
  8-bit KV, `-fa on`, `-np 1`, `--metrics`, `-lv 4`), golden argv in `tests/golden/`.

**Rejected recipes.** None. All five variants reached 400 tokens with the first wording (W0) at every depth
and as short points; W1 and W2 in `recipe.toml` were never needed.

## WP9 decisions (2026-11-09)

### Plan v1.3 adopted
- `docs/plans/step-0-baseline.md` is v1.3 (commit `273e69f`). Its rules are in the code (commit `7385799`):
  the idle precondition (busy time below 10% over 10 s from `/proc/stat`, re-checked every 10 s for up to
  10 minutes, wait recorded, load average recorded not gated), the paging flag (llama-server major faults
  above 1,000 or `VmSwap` above zero; system `pswpin` recorded only; telemetry gained `server_vmswap_kib`)
  and the `accounting` flag.
- `flags.OOM_PATTERNS` no longer treats `CUDA error: an illegal memory access` as an out-of-memory error
  (the old pattern matched any "CUDA error ... memory"). A crash is `crash_mid_cell`; only "out of memory"
  and allocation failures are `oom_at_load` / `oom_runtime`.

### Sweep runner: how records are committed
- **The unit of commit is a repetition** (the short point plus every pair), the warm-up (two requests) or a
  cell record. A batch is appended with one `write`, and every line carries `batch_id`, `batch_index` and
  `batch_size`; the reader accepts a batch only if it is complete and skips unparsable lines. Reason: the
  thermal and paging flags belong to a repetition window and are only known when it ends, and a kill must
  never leave half a repetition that a resume then duplicates. Cost: the requests of an interrupted
  repetition are not in `records.jsonl`; they are kept in `events.jsonl` as `discarded_partial`.
- Resume is keyed by (config hash, role, repetition, attempt). A partly finished cell restarts with a new
  server, the warm-up again, and only the missing repetitions. It refuses if the spec, manifest or sampling
  hash or the `--only` filter differ from `session.json`; a different code commit only warns and the new
  records carry the new commit.
- `session.json` records the SHA-256 of the spec, of `configs/workloads/manifest.json` and of the `[sampling]`
  section of `configs/model.toml`, the git commit, whether `src/`, `configs/` or `scripts/` were dirty
  (`run-sweep.sh` refuses that for a new session unless `--allow-dirty`, which is recorded), the filter, the
  cell order and the `systemd-inhibit` status.

### Failure handling
- Every terminal failure of a cell is flagged `did_not_fit` with a `reason`: `oom_at_load`, `startup_failure`,
  `startup_timeout`, `context` (a depth does not fit the per-slot context from `/props`), `crash_mid_cell`,
  `oom_runtime`, `hung_server`, `request_timeout`. A server that dies mid-cell is restarted (new server,
  warm-up, missing repetitions only) up to `max_restarts` (default 2) times.
- Session-level problems are **not** `did_not_fit`: a held GPU lock, a foreign compute process, a running
  llama-server, a busy port or a missing binary abort at once (exit 3, resumable). Idle CPU and MemAvailable
  failures are retried 3 more times with a 10-minute pause, every attempt recorded in `events.jsonl` and the
  cell summary, then the session aborts (exit 3, resumable).
- Timeouts: 120 s + prompt tokens / 200 + `n_predict` / 10, using the whole prompt length, so a 96K Request A
  gets about ten minutes and a Request B that misses its cache cannot time out falsely. There is no separate
  gap timeout for streams (only the total limit). A hung server is stopped through `stop-server.sh`
  (SIGINT, then SIGKILL after 20 s).

### Session structure
- Stage 1 runs as three sessions (`--only context=32K` and so on), each with its own start and end canaries,
  so a drift flag covers 2 to 4 hours. Within a session the cell order is a seeded shuffle that respects
  `@n_fit` dependencies (P1 before P8 and P9 of the same group), not spec order; the order is in
  `session.json`. The depth order within a repetition is a shuffle seeded by (seed, cell name, repetition).
- The drift flag is decided on PP_fresh at 16K and TG of the 16K Request B (prefill and decode); the short
  point's TG is recorded but not decisive, to keep the false-flag rate down.
- A re-run (`--rerun-flagged`) repeats whole repetitions: any attempt-1 request flagged `warm_prefill`,
  `cache_miss`, `accounting`, `thermal` or `paging` makes its repetition a re-run. `short_gen`, `drift` and
  `did_not_fit` are never re-run, and there is never an attempt 3. A re-run has its own canaries (repetition
  indices 110 to 115).

### N_fit, `--fit` and explicit placement (for WP11)
- **How a partly offloaded layer counts.** N_fit is `expert_layers_on_cpu` from P1's log, which is `n_part` of
  the final `--fit` state: the number of layers whose expert tensors are at least partly in host memory. The
  one partly offloaded layer is counted as a whole layer. `--n-cpu-moe N` puts all the expert tensors of N
  layers on the CPU, so P8 (`N_fit`) keeps at most as much on the GPU as P1 did, and P9 (`N_fit - 2`) two
  layers more. This rests on how `common/fit.cpp` is documented in `smallpc.parsers`, not on a measurement:
  each P8 and P9 cell summary stores the P1 count (`p1_expert_layers_on_cpu`, the overflow type) and P1's
  realized peak VRAM and minimum free VRAM next to its own, so WP11 can check that P8 uses no more VRAM than P1.
- **`--fit` and an explicit placement.** The WP5 `-cmoe --moe-cache-mib 4096` log
  (`health-20261108T170427Z-E-cmoe-lv4`) shows fit leaving the placement alone when it fits:
  `projected to use 6650 MiB ... will leave 9153 >= 1024 MiB ... no changes needed`. If it did not fit, fit
  would ask to reduce device memory. Every cell summary has a `placement_check` (fit setting, attempted,
  succeeded, "no changes needed", whether fit asked for a reduction, expert layers on the CPU), a fit
  intervention on an explicit placement raises a `fit_changed_explicit_placement` warning event, and a
  probing step counts it as a failure, so max-fit is never found with fit moving things. The Stage 1 sketch
  leaves `--fit` at its default for P6 and P7 and sets `fit = "off"` for P8 and P9; **WP11 must read the first
  logs of P6 to P9 and confirm** that fit does not change the explicit placement before trusting the rest.

## WP10 decisions (2026-11-09)

Declared before any WP10 code is written, and before any real (non-functional-test) measurement exists.

### 1. Units and attempts
- The unit of measurement is **one repetition of one cell**: (session, cell, repetition).
- When attempt-2 records exist for a unit, they **replace** the attempt-1 records for that unit in every
  headline number. Attempt 1 stays in the diagnostics table ("excluded diagnostic result").
- Warm-up records (role `warmup`) and canary records (roles `canary_start`, `canary_end`) are never part
  of cell statistics. Canaries are summarised separately (session health).

### 2. Exclusion and eligibility
- After attempts are resolved, a unit is **clean** if no request in it carries any flag (any of
  `thermal`, `paging`, `warm_prefill`, `cache_miss`, `short_gen`, `accounting`) and its session is not
  flagged for drift. Drift is judged per attempt: attempt-1 units against the session's `drift.main`,
  attempt-2 units against `drift.rerun` (the re-run's own canaries); an attempt-2 unit is therefore not
  excluded by the drift of the main run it replaces. If a session has no drift record for an attempt
  (no canary was run), drift is "not assessed" and does not exclude, and the report says so.
- Headline statistics use clean units only and show `n_clean` and `n_total`. Flagged units are listed in a
  diagnostics table with their flags, labelled "excluded diagnostic result".
- A cell is **eligible** for selection (§3.3) if all of these hold:
  - its final cell status is `complete`;
  - the minimum over its final-attempt windows of `windows[*].min_free_vram_mib` is at least 512;
  - it has no flagged unit (after attempts are resolved);
  - `n_clean` meets the minimum for the mode: 2 in screening, 5 in final;
  - it has not failed the output sanity check (§5.6): sanity is `pass`, `fail` or `not run`; `not run`
    is allowed in screening, in final mode it must be `pass`.
- Every cell gets an eligibility line with the reasons it failed, so the table explains itself.
- One refinement that follows from the §5.6 text: a `short_gen` flag is not re-run, so a unit with it stays
  flagged. It excludes the unit from the headline numbers and from eligibility, as the rules say ("no
  unresolved flags"). Its prefill numbers are still shown in the diagnostics table.

### 3. Reading of the tie-break (§3.3)
Among eligible cells of one context, order by **mean T_turn_400** (the mean over repetitions of the
per-repetition mean over the three depths of §5.3). Compare the best-mean cell with the runner-up by the
paired per-repetition difference of T_turn_400 and its 95% CI (the wider of the bootstrap and t
intervals, §5.5).
- If the CI excludes zero, the best-mean cell wins.
- If it includes zero, **step 1** applies: the paired difference of T_reread (also the per-repetition
  mean over the three depths). If that CI excludes zero, the cell with the lower mean T_reread wins. If it
  also includes zero the cells are "still tied" and **step 2** applies: prefer the one without MTP, then
  the one without an expert cache (`moe_cache_mib` unset or 0).
- If still tied, **step 3**: prefer the lower peak VRAM use (total minus the minimum free VRAM over its
  windows).
- The winner and the loser of this comparison are the shortlist's top two. As information only, every
  further eligible cell whose paired T_turn_400 difference from the winner has a CI that includes zero is
  reported as "statistically tied with the winner".
- **Why a reading is needed:** the literal text of step 2 would never apply. Step 1 always yields an
  answer ("prefer the lower mean T_reread" exists for any two cells), so "if still tied" is unreachable.
  Here step 1 only counts when the T_reread difference is itself distinguishable from zero, which is the
  same standard step 0 uses for T_turn_400. Cells are paired on (session, repetition); cells that share no
  repetition cannot be compared and the comparison reports "not comparable" (the better mean stays ahead
  but the result is marked unpaired).

### 4. Screening shortlist (§5.4 Stage 1)
- Screening has 2 repetitions, so **no tie-break is applied**: the shortlist is the 2 eligible cells with
  the lowest mean T_turn_400 per context, where a cell is a placement plus batch setting. The stock cell
  is shown as a reference row and is never shortlisted.
- The output lists the shortlist's VRAM breakdowns and expert-cache hit rates, and flags any pair of cells
  in the top 4 whose means differ by less than the larger of the two ranges (max minus min over the two
  repetitions) as "too close to call at n = 2".

### 5. Output sanity check (§5.6), thresholds declared before any measurement
Inputs are the generated token ids of a candidate and of the reference (the plain `--fit` cell at the same
context) for the same prompt. Computed: the length; the distinct 4-gram ratio (distinct 4-grams divided by
all 4-grams); the longest run of one repeated token; the highest repeat count of any 8-gram; and the
index of the first divergence from the reference. A prompt **fails** if any of these holds:
- length is below `min(100, half the reference length)`;
- the distinct 4-gram ratio is below half the reference's;
- the longest repeated-token run is 16 or more while the reference's is below 16;
- some 8-gram repeats 8 or more times while the reference's maximum is below 8.
A candidate passes if none of its 3 prompts fails. The first divergence index is information only:
different placements and KV types can legitimately diverge.
- **Counting rule for the 8-gram repeat (made while implementing, before any real data):** occurrences
  are counted **non-overlapping**, greedy from the left. With overlapping counts a run of 15 identical
  tokens already contains one 8-gram 8 times and would fail the 8-gram rule, which contradicts the
  separate "run of 16" rule. A loop of an 8-token phrase repeated 8 times still counts 8.

### 6. Mini-sweep data caveats
`data/raw/mini-20261109` is functional-test data, never results. It was produced with `--allow-dirty`, so
its recorded commit is not exact. Its final `complete` cell records have a `server_instance` that is one
too high (fixed in the code afterwards, deliberately not patched in the data), so the analysis never
relies on a cell record's `server_instance`: it uses only request records, cell summaries and telemetry.

### Further choices made while implementing (recorded with the code that needs them)
- Cell identity across sessions is the cell name; units are keyed by (session, cell, repetition), so
  pooling several sessions never merges two repetitions that happen to share an index.
- Paired comparisons match on (session, repetition) keys.

### Interval coverage on simulated data (WP10, `python -m smallpc.stats coverage`)
How often each 95% interval of the mean covers the true mean. 20,000 simulated experiments per row, 1,000
bootstrap resamples per experiment (the production interval uses 10,000; the endpoint noise from 1,000 is
far below the coverage differences shown), seed 1. The reported interval is the wider of the bootstrap and
the t interval, as in §5.5.

| distribution | n | bootstrap | t | reported (wider) | bootstrap was wider |
|---|---|---|---|---|---|
| normal | 5 | 83.3% | 94.9% | 94.9% | 0.0% |
| normal | 10 | 89.9% | 94.9% | 94.9% | 0.0% |
| lognormal sigma 0.1 (mild right skew, skewness 0.30) | 5 | 83.2% | 94.8% | 94.8% | 0.0% |
| lognormal sigma 0.1 | 10 | 89.9% | 94.7% | 94.7% | 0.0% |
| lognormal sigma 0.5 (strong right skew, skewness 1.75) | 5 | 80.2% | 91.2% | 91.2% | 0.0% |
| lognormal sigma 0.5 | 10 | 87.2% | 91.9% | 91.9% | 0.0% |
| exponential (very strong right skew, skewness 2) | 5 | 78.5% | 88.5% | 88.5% | 0.0% |
| exponential | 10 | 86.4% | 90.1% | 90.1% | 0.0% |

What this shows, plainly:
- **The bootstrap interval alone under-covers badly** (80 to 90%), which is why §5.5 asks for the wider one.
- **The wider interval is always the t interval** (the bootstrap interval was wider in 0.0% of simulated
  samples), so the reported interval covers exactly as often as the t interval. It does **not** over-cover:
  the highest coverage is 94.9%, nowhere near 98%, so it is not conservative.
- **The asked-for floor of 93% holds for symmetric and mildly skewed data (94.7 to 94.9%) but not for strongly
  skewed data** (91.2% and 91.9% for lognormal sigma 0.5, 88.5% and 90.1% for exponential). The tests
  (`tests/test_stats_coverage.py`) assert at least 93% for normal and mild skew at n = 5 and n = 10, and only a
  regression floor of 85% for the two strong-skew stress cases, whose numbers are reported here rather than
  hidden. The step-0 timings vary by about 1 to 2% between repetitions (the mini-sweep's canaries: coefficient
  of variation about 0.4% for PP_fresh at 16K), where the data are indistinguishable from the symmetric case,
  so the floor should hold for the data this project will produce (a hope, not something these 10 windows
  prove). A heavy-tailed outcome (for example a few repetitions slowed by paging) is exactly the
  case where the interval under-covers, which is one more reason for the flag rules to keep such repetitions
  out of the headline numbers.
- Paired ratios use a bootstrap CI only (plan §5.5 / the WP10 spec): at n = 5 that interval is narrow
  (the 83% row above is the same effect), so a ratio CI at small n should be read as optimistic.

### Implementation notes (WP10)
- `analysis`: units are keyed `"<session>:<repetition>"`; a unit's drift status is looked up per attempt
  (`drift.main` for attempt 1, `drift.rerun` for attempt 2, "not assessed" when absent). The cell's final
  status is the worst over the sessions that have the cell; `partial` means requests without a final record.
- `select`: stock cells are reference rows in both modes. Cells with no resolved configuration
  (`not_applicable`) have no context and are listed in their own table in the report.
- `report`: the results tables of a `results` report show only cells with at least 5 clean repetitions; the rest
  go to the screening appendix. Every table carries the label banner; every cell with `n_clean` below 5 is
  marked "not reportable (n < 5)" under every label. Figures: stock is neutral ink, at most 8 candidates take
  the reference palette's categorical slots in order of mean T_turn_400, further cells are drawn gray as
  "N other cells"; text stays text in the SVG (`svg.fonttype none`) so the figures are diffable.
- `telemetry` gained `RssAnon`, `RssFile`, `RssShmem` and `pswpout` (not asked for; added because the paging
  analysis can use it). Older CSVs load unchanged.
