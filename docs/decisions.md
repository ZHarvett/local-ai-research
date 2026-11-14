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

## WP11 decisions (2026-11-09)

Declared before the WP11 code is written. Plan v1.4 is adopted (commit `8847d8e`, line 3 reads
`*Version 1.4 · 9 November 2026*`).

### 1. Paging flag and swap activity (§5.6)
- `flags.paging` triggers only on more than 1,000 major page faults of llama-server in the measured window.
  The `VmSwap` trigger is removed; the rest of the function and its detail output (`server_vmswap_max_kib`,
  `server_vmswap_samples`, `system_swap_in_pages`, sample counts) is unchanged.
- **Swap activity** is a note, never a flag. For every measured window, `windows[]` of the cell summary and
  each request's `flag_detail` get `vmswap_start_mib`, `vmswap_end_mib`, `vmswap_max_mib` and
  `swap_activity_mib` (= end minus start, signed), taken from the first and last `server_vmswap_kib` sample of
  the window; and the RssAnon, RssFile and RssShmem figures at the window's start and end
  (`rss_anon_start_mib`, `rss_anon_end_mib`, and likewise `rss_file_*`, `rss_shmem_*`). A value is `null` when
  the column or the process was not sampled. The sweep runner's sampler is the same `telemetry.Sampler` that
  WP10 extended, so it already writes the three RSS columns; a test now proves it.
- The window's flags are unchanged otherwise: `thermal` and `paging` (faults).
- A recorded `paging` flag from an earlier session is never edited. The mini-sweep's only measured paging flag
  (stock-32K repetition 1, 1,692 faults) is also a flag under v1.4, which is what the re-run test relies on.

### 2. Swap sensitivity (§5.5)
- Threshold: a unit is "swap-heavy" if its window's `swap_activity_mib` is above 64. The report recomputes every
  results table (per context) and every paired comparison with the swap-heavy *clean* units removed, and prints
  both versions side by side with the removed units.
- Swap activity of a unit comes from the cell summary's window (same repetition and attempt). Sessions recorded
  before this change have no `swap_activity_mib`; for them it is derived from the telemetry CSV
  (`server_vmswap_kib` between the window's `t0_epoch` and `t1_epoch`), and if that is not possible the
  report prints "not available" for the unit. Units with "not available" are kept in both versions.
- Verdict: the section states plainly whether a headline comparison changed sign (the geometric-mean ratio
  or the paired difference moves across 1 or 0, or the shortlist order changes) and whether any interval changed
  materially (an interval endpoint moved by more than the original interval's half-width).

### 3. Paired-ratio intervals (§5.5)
- `stats.paired_ratio` returns the wider of the percentile-bootstrap CI of the geometric mean (10,000
  resamples, fixed seed) and a t-interval on the log ratios, back-transformed with exp; it reports both and
  which one was used (`ci_method`). Coverage on simulated data (n = 5, log-normal noise, sigma 0.05 and 0.2,
  known true geometric-mean ratio) is asserted at 93% or more in the tests and the measured numbers are recorded
  below, with the code commit.

### 4. Eligibility and selection against §3.3
`smallpc.select` was compared with the v1.4 text again (eligibility conditions, the ordering by mean
T_turn_400, the tie-break steps, "statistically tied with the winner", the screening shortlist without a
tie-break, stock as a reference row only, peak VRAM = total minus minimum free). Differences found are
recorded in the code commit; none is expected, because WP10 implemented that reading.

### 5. Stage 1 and pre-flight specs
- `configs/sweeps/stage1.toml` is the Stage 1 sketch fixture with `expect_cells = 57`; axes, defaults and
  canary are copied unchanged.
- `configs/sweeps/preflight.toml` copies the same axes and defaults, runs one repetition and has no canary
  (the schema allows it; drift is "not assessed"). **10 cells, all batch b2048 except one:** 32K: P1, P3, P6,
  P7, P8, P9; 128K: P1, P6, P8; plus **P1-32K-b4096**, added at Zack's request because half of Stage 1's cells run
  `-b 4096 -ub 4096` and that setting would otherwise meet the GPU for the first time in the real sweep. Its checks
  are: the server starts, `-b 4096 -ub 4096` in the effective settings, a compute buffer larger than in
  P1-32K-b2048 (both numbers reported), no accounting, warm_prefill or cache_miss flag, and its minimum free VRAM.
  A failure there stops the pre-flight for a decision; the plan is not changed in this session.
- Pre-flight data is functional-test data, never results.

### WP11 results recorded with the code (commit "WP11: apply plan v1.4 rules")

**Paired-ratio interval coverage** (`python -m smallpc.stats coverage --ratio`; 20,000 simulated experiments per row,
1,000 bootstrap resamples, seed 1; per-repetition log ratios ~ Normal(log 0.8, sigma), true geometric-mean ratio 0.8;
reported interval = wider of the bootstrap and the t interval on the log ratios):

| n | sigma (log ratio) | bootstrap | t | reported (wider) | bootstrap was wider |
|---|---|---|---|---|---|
| 5 | 0.05 | 83.3% | 94.9% | 94.9% | 0.0% |
| 5 | 0.2 | 83.3% | 94.9% | 94.9% | 0.0% |
| 10 | 0.05 | 89.9% | 94.9% | 94.9% | 0.0% |
| 10 | 0.2 | 89.9% | 94.9% | 94.9% | 0.0% |

- The reported interval covers 94.9% at n = 5 for both sigmas, above the 93% floor; the test
  (`tests/test_stats_coverage.py`, 3,000 experiments, 500 resamples, about 0.3 s) asserts at least 93%.
- sigma 0.05 and 0.2 give identical coverage because the noise is a scale family on the log scale and both runs use the
  same seed (the same standard-normal draws); the coverage of a t-interval does not depend on sigma. It is not a
  copy-paste error.
- The bootstrap alone covers 83% at n = 5 (the WP10 finding); the t interval was the wider one in every sample, as for
  plain means.
- The simulation is for log-normal ratios, where the t-interval on logs is exact. Real ratios of timings that include a
  slowed repetition are the heavy-tailed case; the flag rules and the swap sensitivity are the guard against that.

**Eligibility and selection against §3.3 (v1.4):** compared line by line, no difference found; no code change.
Eligibility (complete; minimum free VRAM of the final-attempt windows at least 512 MiB; no flagged final unit; n_clean 2 in
screening and 5 in final; sanity pass/fail/not run), the ordering by mean T_turn_400 (units are whole repetitions, so a
repetition counts only if all its depths are clean), the tie-break steps (CI excludes zero; T_reread; no MTP then no
expert cache; then lower peak VRAM = total minus minimum free), the "statistically tied" list, the screening shortlist
without a tie-break and the "too close to call at n = 2" marking, and stock as a reference row only.

**Implementation notes (WP11):**
- `analysis.unit_swap_activity` reads `swap_activity_mib` from the cell summary window, else derives it from the
  instance's telemetry CSV between the window's `t0_epoch` and `t1_epoch`, else "not available". For the mini-sweep it
  derives 4,143 MiB for stock-32K repetition 1 (the paging analysis of WP10 gave 4,146 MiB from the same data; the
  difference is the sample boundary), and 0 for the other three units.
- Only clean final units are removed in the sensitivity. A swap-heavy unit that is already excluded by a flag is
  listed as "already excluded" and does not count as removed (it is not in the headline numbers anyway).
- `windows[]` and each request's `flag_detail` carry `vmswap_start_mib`, `vmswap_end_mib`, `vmswap_max_mib`,
  `swap_activity_mib`, and the `rss_anon/file/shmem_start_mib` and `_end_mib` figures.
- `paging_analysis` keeps its three historical rules R0 to R2 (WP10); R0 is the v1.3 rule and is no longer equal to
  `flags.paging` (v1.4: faults only).

### WP11 pre-flight findings (session `preflight-20261109`, 9 Nov 2026, functional-test data)
Run with Zack's G3 with one Chrome tab, Mission Center and the IDE left open (the runner's idle-CPU gate passed at its first
check for every cell: 10 s waits, busy 1 to 3 %). 10 cells, 1 repetition, 29 minutes, 90 requests, all cells `complete`, no
flag of any kind in any window, no warning event, no `fit_changed_explicit_placement`.
- **Placement confirmations from the logs.** P6, P7: `-cmoe --moe-cache-mib N` with `--fit` at its default: "projected to use 14638
  MiB ... will leave 1165 >= 1024 MiB ... no changes needed" (P6 at 32K), "will leave 3214 ... no changes needed" (P7); fit left the
  explicit placement alone. P8, P9: `--fit off --n-cpu-moe N`, fit not attempted. P3 (`--fit --moe-cache-mib 1024`): fit sizes
  the placement around the cache, 17 expert layers on the CPU against P1's 15, 1,251 MiB free (the cache coexists with fit). P1
  (`--fit`): 15 layers on the CPU at 32K, 16 at 32K with `-b 4096`, 18 at 128K.
- **Max-fit is bound by fit's 1,024 MiB margin, not by the 512 MiB floor of §5.4.** Probe steps at 13,056, 12,800 and 12,544 MiB
  (32K) and 11,520, 11,264 and 11,008 MiB (128K) were rejected as `fit_intervened` although the free VRAM after the longest
  request would have been 589 to 1,101 MiB (at least 512): with `--fit` at its default fit shrinks the placement whenever its
  projection leaves less than 1,024 MiB. The WP9 rule (a fit intervention fails a probing step, so max-fit is never found with fit
  moving things) is working as decided; the consequence is that P6/P7 cache sizes are about 512 to 768 MiB smaller than a pure
  512 MiB rule would give (found 12,288 MiB at 32K, 10,752 MiB at 128K, leaving 1,355 and 1,361 MiB free). The plan is not changed;
  whether P6/P7 should instead set `--fit off` or a lower `--fit-target` is Zack's decision.
- **P7 = max_fit - 2048:** 12,288 - 2,048 = 10,240 MiB at 32K (reported 10,237 by the server). P6 at 32K reused the probe
  (cache hit, 0 steps).
- **N_fit from P1's log** (`expert_layers_on_cpu`, partial layer counted whole; overflow type GATE): 15 at 32K and 18 at 128K; P8
  `--n-cpu-moe` 15 and 18, P9 13. P8 uses less VRAM than P1, as §N_fit says it should: peak 14,246 against 14,962 MiB (32K) and
  14,420 against 15,006 MiB (128K); P9 uses more: 15,176 MiB peak, 1,135 MiB free.
- **`-b 4096 -ub 4096` (P1-32K-b4096):** the server starts and the log reads `n_batch = 4096, n_ubatch = 4096` (the runner's saved
  /props has only context and slot fields; the log and argv are the evidence). CUDA0 compute buffer 1,104.2 MiB against 642.1 MiB at
  b2048 (host 384.2 against 192.1), minimum free VRAM 1,349 MiB, one more expert layer on the CPU (16 against 15). No flags.
- **Prefill depends strongly on `-ub`:** PP_fresh at 16K 1,015 tok/s (mini-sweep, `-ub 512`), 2,316 (`-ub 2048`), 2,862 (`-ub 4096`);
  decode unchanged. The plan's Stage 1 time estimate (from the live check at `-ub 512`) is about twice too high; see the runbook.
- **Swap and RSS:** `swap_activity_mib` 0.0 and VmSwap 0 in all 10 windows; 0 major faults. RssAnon grows by 1.2 to 2.8 GiB during a
  window (1.2 to 4.0 GiB at 128K), RssFile 19,986 MiB for `-cmoe` and `--fit` cells and 7,829 (P8) / 6,851 (P9) / 9,258 (128K P8)
  MiB for explicit `--n-cpu-moe`, RssShmem 277 MiB (469 at b4096, 661 at 128K).
- **Report fix:** the VRAM breakdown showed the expert cache (10 to 12 GiB for P6/P7) as "other"; it is now its own part
  (`expert_cache_mib`, from the server's reported cache size) and "other" is about 300 MiB (CUDA context).
- **Re-run mode on real hardware** (copy `data/raw/rerun-test-20261109` of the mini-sweep): `--rerun-flagged` re-ran exactly
  stock-32K repetition 1 as attempt 2 (7 requests, warm-up, no flags) plus its own start and end canaries (indices 110 to 115,
  drift: no flag); the first 61 lines of `records.jsonl` are byte-identical before and after, and a second identical command
  planned nothing and left `records.jsonl` unchanged. On a copy the new records carry the copy's session id
  (`rerun-test-20261109`) while `session.json` and the old records still say `mini-20261109`; the runner and the analysis cope with that
  (the analysis uses the session id of `session.json`), so no change was needed.
- **Probe cache:** `data/probes/cache.jsonl` now holds the pre-flight's two max-fit probes (32K and 128K, b2048). A real session
  with the same configuration, llama.cpp commit, model and GPU reuses them (recorded as `probe_cache`, `cached_from`). Committed
  with the pre-flight data so that the tree is clean.

## WP11 part 2: re-run mode fixes (2026-11-10)

Plan v1.5 is adopted (commit `3941bb0`, line 3 reads `*Version 1.5 · 9 November 2026*`); the pre-flight probe cache was retired
(`git mv data/probes/cache.jsonl data/probes/preflight-cache.jsonl`, `6943239`), so every probe of the three real sessions was
measured fresh.

### Incident (10 Nov 2026)
After the three Stage 1 sessions (`stage1-32K`, `-64K`, `-128K`, each started with `--only context=...`), the runbook's
`scripts/run-sweep.sh configs/sweeps/stage1.toml --rerun-flagged stage1-32K` exited with code 2:
`cannot resume: --only filter differs: session {'context': '32K'} vs {}`. The refused command also **overwrote
`data/raw/stage1-32K/session.json`** (a 4-line stub: `state`, `last_error`, `exit_code`) and `progress.json` (an "aborted"
stub). `records.jsonl`, `events.jsonl`, the cell files and the telemetry were not touched. Both files were restored from the
committed versions (`git checkout -- ...`, commit `18bd463`; `git status` and `git diff HEAD --stat` empty afterwards). The 32K
session has no flagged repetition, so no re-run of it was needed or made. `--rerun-flagged` was not run for 64K or 128K before the fix.

### Bug 1: `--rerun-flagged` ignored the session's `--only` filter
`Session.rerun_flagged` opened the session with `filters` taken from its own command line, and the runbook's re-run command has
no `--only` (it "re-runs the session as it was started"). `provenance.resume_check` requires the filters to be equal, so every
session started with `--only` was refused.

### Bug 2: a refused start overwrote the session's files
`open()` raised `ProvenanceError` (a `SessionAbort`) before `self.session` was loaded. The abort handler of `run()` and
`rerun_flagged()` then called `update_session(state="aborted", ...)`, which wrote the (empty) in-memory dict plus those keys over
`session.json`, and `progress()` wrote over `progress.json` (and `run()` appended a `session_abort` event). The same path was taken by:
a resume with a changed spec, manifest or sampling hash; a changed filter; a new session on an existing id (`already exists; use
--resume`); and `InhibitError` or a dirty tree for a new session (which created a directory with a stub `session.json`). A
`KeyboardInterrupt` before the session was loaded did the same.

### Why the tests did not catch it
The pre-flight's re-run test (and `test_rerun_appends_attempt_2_...`) used a session created **without** a filter, so stored and
current filters were both `{}`; the refusal tests called `open()` directly and never looked at what the handler of `run()` wrote.
Neither checked that a refusal leaves the session's files unchanged.

### Fix (`src/smallpc/sweep/session.py` only; tests in `tests/test_sweep_refusals.py`)
- `rerun_flagged` first reads the stored filter from `session.json` (read-only, `_adopt_stored_filters`) and uses it. A `--only`
  given on the command line must equal it, otherwise the re-run is refused with a clear message. Cell and unit selection are unchanged.
- `Session._loaded` is set only after every provenance check has passed. Until then `update_session`, `progress` and the handlers
  write nothing; a refusal goes only to stderr (the job log) as `smallpc.sweep: refused, no session file touched: ...`, with the
  same exit code as before. `open()` no longer creates the session directory before the checks.
- `update_session` and `progress` are read-modify-write (`_merge_write`): the given keys are merged into the JSON object on disk and
  every other key is kept. An existing file that cannot be read as a JSON object is never replaced (`ProvenanceError`). A resumed
  `open()` merges only `runs`, `state` and `inhibit`.
- Audit of every writer of `session.json`, `progress.json` and `events.jsonl` in `src/` and `scripts/`: `open()`,
  `update_session()`, `progress()`, the `except KeyboardInterrupt` and `except SessionAbort` handlers of `run()` and of
  `rerun_flagged()` (all fixed above), `finish_drift` (calls `update_session`, now a merge) and the cell-summary and snapshot
  writers (already merge or write-once, only reached after loading). `status.py`, `runner.py`, `analysis.py` and
  `paging_analysis.py` only read.
- Tests (CI-safe, mock server): filtered session re-run runs only the flagged unit as attempt 2; a conflicting `--only` is refused
  (both stored `{context: 32K}` against `64K`, and stored `{}` against `32K`) with every file of the session byte-identical; a
  resume refused for a spec, manifest or filter change or a missing `--resume` leaves every file byte-identical; a refused new
  session leaves no directory; `update_session` and `progress` merge and keep unrelated keys; an unreadable `session.json` (three
  kinds of garbage) is never overwritten. All 14 fail on the old code and pass on the new.
- Known, left as is: a completed re-run sets `finished_utc` of `session.json` to the end of the re-run (the original main-run
  end is in `runs[0]` and in `events.jsonl`); the progress file keeps keys of an earlier run until they are overwritten.
- Not changed: flags, eligibility, selection, statistics, the request protocol, the workload code, the spec or anything that
  decides what is measured. Re-run records carry the new code commit and a `code_commit_changed` warning event, by design.


## WP12 decisions (2026-11-10)

WP12 part 1 prepares Stage 2 (tools, specs, runbook, short GPU checks). Plan v1.6 is adopted (commit `2fc89c1`, line 3 reads
`*Version 1.6 · 10 November 2026*`). These decisions are recorded before any code of this work package and before any Stage 2 data.

### Stage 1 shortlist (screening data, n = 2)
Label: **screening data, n = 2**. Never a result. Mean T_turn_400 in seconds with the 95% interval of `smallpc.stats`
(`data/analysis/select-screening.json`; the "too close" note is the §3.3 screening rule, larger of the two ranges). Order is the Stage 1 order.

| context | rank | cell | mean T_turn_400 (s) | 95% CI | n | note |
|---|---|---|---|---|---|---|
| 32K | 1 | `P6-32K-b4096` | 6.14 | [3.57, 8.70] | 2 | too close to call at n = 2 |
| 32K | 2 | `P2-32K-b4096` | 6.26 | [6.24, 6.29] | 2 | too close to call at n = 2 |
| 32K | ref | `stock-32K` (stock, not shortlisted) | 8.45 | [8.40, 8.50] | 2 | - |
| 64K | 1 | `P6-64K-b4096` | 7.00 | [6.28, 7.72] | 2 | - |
| 64K | 2 | `P2-64K-b4096` | 7.16 | [7.06, 7.26] | 2 | - |
| 64K | ref | `stock-64K` (stock, not shortlisted) | 9.36 | [9.09, 9.63] | 2 | - |
| 128K | 1 | `P2-128K-b4096` | 9.06 | [8.30, 9.81] | 2 | too close to call at n = 2 |
| 128K | 2 | `P6-128K-b4096` | 9.09 | [8.88, 9.30] | 2 | too close to call at n = 2 |
| 128K | ref | `stock-128K` (stock, not shortlisted) | 11.29 | [10.89, 11.69] | 2 | - |

Per the plan, "top" is the first cell above even where the pair is too close to call (32K and 128K).

### Stage 1 paging findings
Paging-flagged windows (more than 1,000 major faults) occurred only in repetition 1 of long-running servers at 128K (14 of 38 windows)
and 64K (1 of 38), and all 15 attempt-2 windows on fresh servers were clean. The server's anonymous memory tracked its host prompt cache
(`--cache-ram`, default 8,192 MiB), which every unique benchmark prompt fills: a hypothesis consistent with the data, not proof
(`reports/stage1/diagnostics.md`).

### Stage 2 rules (quoted from plan v1.6 section 5.4, not paraphrased)
Definition of "top":
> "Top" means first in the Stage 1 order, even where the pair is too close to call at n = 2.

2f, rule text:
> Rule: the chosen value is the largest tested value with no paging-flagged window in any of its 5 repetitions, unless its mean T_turn_400 is more than 3% above the mean of the 8192 cell's clean units. If the 8192 cell is already clean, the default stays. If no tested value is clean, stop and report: the cause is then not the host cache. The chosen value is used in every later candidate cell and in the tuned configs. Stock keeps the default.

2a, full bullet:
> - **2a MTP.** Per context, 6 cells: both shortlisted placements with MTP off (these are also the 5-repetition measurement of the shortlist), the top placement with draft lengths 1, 2 and 3, and the second placement with the best draft length of the top placement. The best draft length is chosen by the §3.3 rules among the three; if the CIs include zero, the smaller draft length wins. Cache sizes of P6 cells are re-probed with MTP on, because the head and its draft context cost VRAM. Record acceptance, and the effect on decode **and on prefill**. MTP joins a tuned config only if it wins by §3.3 on T_turn_400 and passes the output sanity check.

### Machine state
The desktop apps stay open for Stage 2 (gate G3 not met), as in Stage 1; they are idle and the runner's idle gate checks CPU before every
cell. Stage 3 and Stage 4 will need a quiet machine (browser and IDE closed).

### Tooling interpretations (declared before any Stage 2 data; confirmed by Zack on 10 Nov 2026)
Where the plan's text leaves a choice, `smallpc.stage2` implements the following, and the decision output always says which rule applied.
1. **Pairing.** Paired comparisons exist only between cells of one session (`smallpc.analysis` keys units by session and repetition).
   So every 2b, 2c and 2d spec holds both of its cells (2b re-runs the 8-bit cell under its own `s2b-` name even if it equals a 2a cell), and
   the 2a2 spec also holds the second placement with MTP off.
2. **2a2 anchor.** 2a2 also re-runs the top placement's 2a-best configuration (the "anchor") so the final top-versus-second comparison is
   inside one session. Without it the comparison would have no shared repetitions and `smallpc.select`'s tie-break would treat it as a tie
   and prefer fewer moving parts regardless of speed. Cost: 3 cells per context instead of 2 (`--no-anchor` turns it off).
3. **Draft length.** Among the top placement's MTP cells (draft length 1, 2, 3) the best-mean cell wins unless other cells are not
   distinguishable from it by §3.3 steps 1 and 2 (the paired T_turn_400 CI and the paired T_reread CI both include zero); then the smallest
   such draft length wins. The result does not depend on cell order.
4. **2f across contexts.** Each context is decided as written. The value used by later cells is the smallest of the per-context choices, and
   the output is marked "human confirmation needed" whenever they differ. If the 8192 cell has no clean unit the 3% condition cannot be
   evaluated and the tool reports "no automatic decision". The paging flag of 2f is read from attempt-1 windows, so `--rerun-flagged` must not
   run before the 2f decision.
5. **decide stages.** `decide` also has a `2a2` stage, which produces the per-context winner and runner-up that 2b to 2d and the sanity
   check start from.
6. **Probes.** P6 cells without MTP reuse the Stage 1 probe by cache key (the same VRAM picture); MTP cells (and the FP16-KV cell) probe fresh.
7. **Eligibility to drive a decision.** `decide` refuses a session whose `session.json` records `allow_dirty`, whose spec header says
   functional-test, or whose id starts with `ft-` (the functional-test prefix of the spec generator). Every decision output records the session
   ids, spec hashes, plan version, code commit, llama.cpp commit and the verbatim rule text.
8. **Session gates.** The Stage 1 gate applies to every Stage 2 session, except that criterion f (at most 20% of measured windows
   paging-flagged) does not apply to 2f (the gate reports flagged windows per cell and the next step is `decide`); from 2a onward it applies with
   the chosen `--cache-ram`, and more than 20% flagged stops the programme for a human (the 2f choice did not hold). `docs/runbook-stage2.md`
   lists every point that needs a human decision.

### Fixes in this work package (no change to flags, eligibility, selection, statistics, the request protocol or the workload code)
- `smallpc.paging_analysis` takes `--label` (default `screening` for sessions whose id starts with "stage", else `functional-test`); the
  Stage 1 outputs `data/analysis/paging-stage1-64K|128K.*` are regenerated with `--label screening` (only the banner and note change).
- A completed re-run writes `rerun_finished_utc` instead of overwriting `finished_utc` of `session.json`. The `session.json` files of
  `stage1-64K` and `stage1-128K` keep the overwritten value (Stage 1 data is not edited); the main-run end is in `runs[0]` and `events.jsonl`.

## WP12 part 1: findings of the short GPU checks and the 2c / 2d / 2e choices (2026-11-10)

All runs below are **functional-test data** (`ft-` sessions, `data/loadmode/`, `data/sanity/ft-*`, `data/microbench/ft-*`), produced with the desktop apps open. They test code
paths; none is a result.

### `--cache-ram 0` means "disabled" (confirmed before any 2f session)
Help text of the pinned build: "set the maximum cache size in MiB (default: 8192, 0 for decision models, -1 - no limit, 0 - disable)". Source
(`tools/server/server-context.cpp`): `cache_ram_mib == 0` creates no prompt cache ("prompt cache is disabled - use `--cache-ram N` to enable it") and also disables
`--cache-idle-slots`. "Decision models" are a separate typed-model concept (`<arch>.decision.type` in the model metadata), not MTP and not this model, so MTP cells keep the default cache.
Pre-flight (`ft-2f-cram`, P6-32K-b4096, one repetition): the rendered flag is `--cache-ram 0` / `--cache-ram 8192`; the `0` server logs "prompt cache is disabled" and
"--cache-idle-slots requires --cache-ram, disabling" and prints **no** `cache state` line; the 8192 server logs "prompt cache is enabled, size limit: 8192 MiB", 6 `cache state` lines,
1,740.5 MiB (5 prompts) at the end. Both cells complete, no flags. The 2f cells therefore test what the plan says.

### 2c: the alternative to `--load-mode auto` is `dio`
What the pinned build does (`include/llama.h`, `src/llama-model-loader.cpp`, `src/llama-model.cpp`, `src/llama-mmap.cpp`):
- `auto` and `mmap`: the model file is memory-mapped; the CPU-resident tensors are a `CPU_Mapped` buffer of file-backed pages (RssFile), which the kernel may drop and re-read from the SSD (these are the major faults of Stage 1). `auto` is `mmap` unless a device lacks mmap support.
- `none`: no mmap. Tensors are read with ordinary buffered `read()` into newly allocated host buffers; the page cache keeps a reclaimable copy of the file.
- `dio`: no mmap. The file is opened with `O_DIRECT` and read in aligned blocks into the same kind of host buffer, bypassing the page cache ("use DirectIO if available").
- `mlock` and `mmap+mlock`: lock the model in RAM. **Excluded**: the memory-lock limit is 8 MiB, and the plan excludes modes that need a raised limit or sudo.
Measured at 32K with P6-32K-b4096 (one short request, `data/loadmode/ft-smoke-*.json`): `auto` holds the experts as 20.4 GiB of RssFile (CPU_Mapped, evictable); `none` and `dio` both put them in an
**18.9 GiB `CUDA_Host` buffer (pinned memory)** with RssFile about 0.2 GiB and RssAnon under 1 GiB, so the kernel cannot drop or swap those pages. Load 10 s (auto, page cache warm), 21 s (none), 19 s (dio); the first
request ran at 1,110 to 1,132 tok/s prefill and 57 to 59 tok/s decode in all three (one request each: no speed claim).
**Choice: `dio`.** It is the remedy that matches what Stage 1 showed (the flagged windows lost 1.5 to 8.1 GiB of RssFile and faulted): the model stops being evictable file memory. Of the two modes with
that effect, `dio` leaves no second 20 GiB copy in the page cache (`none` fills it at every cold load, which pushes other processes' cache out on a 32 GB machine) and its load time does not depend on what the page cache holds.
It needs no sudo and no lock limit, loaded here without a fallback, and is a constant in `smallpc.stage2.specgen` (`LOAD_MODE_ALT`, pinned by a test).
Risks 2c will show, not hide: pinned memory cannot be reclaimed, so the pressure moves to the other processes (the desktop apps); the 2c paging table (faults, swap activity of llama-server, host cache, MemAvailable) is part of the decision output. `load_mode` is in the probe key, so both 2c cells probe fresh.

### 2d: not needed
The effective thread count is 8: all 82 Stage 1 server logs print `n_threads = 8 (n_threads_batch = 8) / 16` (16 is the hardware thread count of the Ryzen 7 9700X, 8 cores) and no resolved Stage 1 config sets `-t`. `-t 8` is the default, so 2d is skipped and recorded
(`python -m smallpc.stage2 decide --stage 2d --default-threads 8`).

### MTP pre-flight (`ft-2a-mtp`, P6-32K-b4096, one repetition, draft lengths 1 and 3)
Both cells complete, no flags, no error lines in either log; "creating MTP draft context" and "adding speculative implementation 'draft-mtp'" appear. Max-fit with MTP on is **10,752 MiB** for both draft lengths (4 steps, 21.4 s each) against 11,520 MiB without MTP in Stage 1 (b4096):
the draft context takes 768 MiB of cache room (3 steps of 256). Free VRAM at the first probe step (cache 4,096) was 7,841 MiB (n = 1) and 7,715 MiB (n = 3) against 8,803 MiB without MTP: **962 and 1,088 MiB** of VRAM for the MTP head and draft context. From the logs (CUDA0): model +23 MiB (head), recurrent state +63 MiB (n = 1) or +188 MiB (n = 3), draft KV 64 MiB, draft compute buffer 638 MiB.
Acceptance: 80.2% (709 / 884) at n = 1, 52.2% (973 / 1,863) at n = 3. PP_fresh with MTP, anecdotal (one repetition against two Stage 1 repetitions of the same placement): 2,275 / 2,221 / 2,151 tok/s (n = 1) and 2,243 / 2,251 / 2,186 (n = 3) at 8K / 16K / 24K against a Stage 1 mean of 2,468 / 2,482 / 2,384: **about 9% lower** with MTP; TG 104 / 104 / 94 (n = 1) against 93 / 87 / 81. The 10752 and 10752 probes were moved to `data/probes/functional-test-cache.jsonl`; the committed `data/probes/cache.jsonl` is unchanged, so real Stage 2 MTP probes are measured in their own sessions.

### Sanity runner (`data/sanity/ft-sanity-32K.json`)
P6-32K-b4096 against P1-32K-b2048, three prompts, 512 tokens each: **PASS** (first divergence at tokens 120, 41 and 222: information only; distinct 4-gram ratio 0.943 / 0.894 / 0.868 against 0.917 / 0.904 / 0.929; no repeated-token run longer than 1; 8-gram repeat 2 / 2 / 2 against 2 / 2 / 3). 47 s for both servers.
The pinned server returns the ids in `tokens` with `"return_tokens": true` (README of the server).

### 2e: the cross-check cell is P2-64K-b4096
`python -m smallpc.stage2 bench-crosscheck --list-expressibility` ranks the Stage 1 64K candidates by the number of inference fields llama-bench cannot express. P1 and P2 (fit placements) have none: `--fit-target` is `-fitt`, and only the context is approximated (`-fitc`, the minimum context of the fit).
P3 to P5 lose the expert cache, P6 and P7 lose the cache and the context, P8 and P9 lose the context. The default is P2-64K-b4096: nothing inexpressible, one approximation, and it is on the 64K shortlist. (The brief expected a P8 or P9; those cannot carry the context at all.)
Smoke (`data/microbench/ft-crosscheck-P2-64K-b4096.json`, 1 repetition, 175 s): parses, labelled "cross-check, random-token prompts, never used for a decision", nothing inexpressible; fresh prefill 2,682 / 2,493 / 2,324 tok/s at 16K / 32K / 48K, decode 70.5 / 64.5 / 59.4 tok/s at those depths.

## Stage 2f decision (2026-11-10)

**Chosen `--cache-ram`: 2048.** It comes from the plan v1.6 rule (section 5.4, quoted in "WP12 decisions") applied by `python -m smallpc.stage2 decide --stage 2f`
to session `s2f` (`data/raw/s2f`, spec `configs/sweeps/stage2-2f.toml`, code commit `7b7daf1`). Tool output: `status: decided`, both contexts choose 2048, no human
decision needed (`data/analysis/stage2/2f.md`, `.json`). The step lead reviewed the checkpoint report and accepted the session and the decision.
The value is used in every later candidate cell and in the tuned configs; stock keeps the default (8192).

Paging-flagged windows (attempt 1, more than 1,000 major faults), per cell of `s2f` (5 repetitions each):

| context | `--cache-ram` | flagged windows | faults per window (min to max) | flagged repetitions |
|---|---|---|---|---|
| 128K (P2-128K-b4096) | 8192 | 2 of 5 | 239 to 15,130 | 1, 2 |
| 128K | 4096 | 1 of 5 | 19 to 1,202 | 1 |
| 128K | 2048 | 0 of 5 | 0 to 889 | none |
| 128K | 0 | 0 of 5 | 0 to 0 | none |
| 64K (P6-64K-b4096) | 8192 | 3 of 5 | 0 to 159,451 | 2, 3, 4 |
| 64K | 2048 | 0 of 5 | 0 to 828 | none |

Caveats recorded with the decision:
- **"Clean" means no window above the 1,000-fault line, not "no paging".** The 2048 cells had repetition-1 windows of 889 faults (128K) and 828 faults (64K), with 450.6 and
  547.6 MiB of `VmSwap` growth. Only `--cache-ram 0` was fault-free and swap-free in all five windows (0 faults, 0.0 MiB, 128K only; 64K was not run at 0).
- **The tool's 3% test is unpaired.** It compares the mean over all 5 repetitions of the candidate with the mean over the 8192 cell's clean units (3 of 5 at 128K, 2 of 5 at 64K),
  and T_turn_400 differs by repetition (prompt variant), so the repetition mix inflates the gap (-0.62 % at 128K and -4.18 % at 64K as printed). On the same repetitions the 2048 against
  8192 differences are **-0.75 % (128K, n = 3) and -0.31 % (64K, n = 2)**. The decision is the same either way (the rule's limit is +3 %).
- **At 64K with 8192 the paging was worse than in Stage 1:** three windows flagged (repetitions 2, 3, 4), up to 159,451 faults in one window (Stage 1: one flagged window of 38 at 64K).
  Flagged windows were not slower: the 159,451-fault window had the lowest T_turn_400 of its cell (6.816 s against 7.054 s in repetition 0). Anecdotal (one cell per setting, one session).
- **Stock keeps the default 8192 cache**, so Stage 3 (stock against tuned) will compare a tuned config at 2048 with a stock config that pages at 64K and 128K. The step lead designs how
  Stage 3 deals with that after the 2a data.
- **Fallback:** if gate criterion f (at most 20 % of the measured windows paging-flagged) fails in a later session, the step lead decides whether to use `--cache-ram 0`. It is not an
  automatic step and the agent does not choose it.
- The data cannot show causation (one cell per setting, one session, one machine state); the dose-response (flagged windows, RssAnon growth and host cache size all fall with the setting)
  and the fault-free cram 0 cell are consistent with the host-prompt-cache hypothesis.

### Sub-stages not run in this continuation
- **2d (threads) is skipped:** the default thread count is 8 in all 82 Stage 1 server logs (`n_threads = 8 (n_threads_batch = 8) / 16`, WP12 part 1 finding), so `-t 8` is the default; recorded with
  `python -m smallpc.stage2 decide --stage 2d --default-threads 8` when needed.
- **2c (`--load-mode dio`) is not part of this continuation**; no 2c spec is generated here.

## Stage 2a 64K gate (2026-11-10)

**What happened.** Session `s2a-64K` failed the step lead's operational gate criterion f: **6 of 25 measured attempt-1 windows paging-flagged (24.0 %)**, above the 20 % stop line
(`s2a-32K`: 4 of 25, 16.0 %, passed). Criteria a to e passed in both sessions. The runner stopped the programme as instructed; the step lead reviewed the stop report
(commits `455eb57`, `7c9d223`) and decided as below. The session is accepted as a **recorded deviation**.

**Evidence (from the stop report).**
- Flagged windows: 32K P6-mtp0 repetition 4 (1,697 faults) and P6-mtp1 repetitions 2, 3, 4 (8,296; 1,243; 1,683); 64K P6-mtp1 repetitions 2, 3, 4 (20,153; 16,162; 18,550) and P6-mtp2
  repetitions 2, 3, 4 (51,759; 4,687; 13,247). None in P2 cells, in mtp3 cells or in repetitions 0 and 1; 64K mtp0 had none.
- Swap activity of the flagged windows: -295 to +58 MiB (almost no swap growth); host prompt cache capped at 1.3 to 1.9 GiB (limit 2,048 MiB); MemAvailable at least 21.1 GiB;
  several flagged windows lost 0.2 to 1.5 GiB of RssFile (file-backed pages of the memory-mapped model).

**Step lead's reading.** The mechanism differs from 2f. In 2f the flagged windows came with swap growth and growth of the host cache and anonymous memory (`--cache-ram 8192`);
here they are file-backed faults of the memory-mapped model, concentrated in P6 cells with MTP (mtp1, mtp2) in repetitions 2 to 4. Therefore **`--cache-ram 0` is not indicated by
the evidence, and `--cache-ram` stays 2048** (the 2f decision stands). Working hypothesis, **not a finding**: first-touch faults on expert pages that were evicted after load, touched
again when later prompt variants use those experts. Nothing in the 2a data tests it yet (the 2a paging diagnostic describes the windows; it does not isolate a cause).

**Rules for the rest of Stage 2.**
- The plan's paging-flag rule (section 5.6) is unchanged: flagged units are re-run once, and units still flagged are excluded from selection and headline numbers.
- Criterion f was the step lead's operational stop rule, not a plan rule. It now reads: **stop if more than 40 % of a session's measured windows are paging-flagged, or if any
  paging-flagged window shows `swap_activity_mib` above 1,024 (the 2f mechanism returning).** This applies to every later Stage 2 session. `docs/runbook-stage2.md` and the `stage2 gate`
  tool still print the 20 % rule (the tool is not changed); the gate output is read with this rule and the figures are reported.
- `--rerun-flagged` is now allowed (the 2f decision is made) and runs once per session with flagged units, never twice.

## Stage 2a: re-run pass and a defect that blocks the 2a decision (2026-11-10, not fixed)

**Re-run pass** (one `--rerun-flagged` per session, commits `d660916`, `ba25f94`, `a8010c5`): 15 units re-run (32K 4, 64K 6, 128K 5), 12 clean, 3 still paging-flagged (`s2a-P6-32K-b4096-mtp1` repetition 4;
`s2a-P2-128K-b4096-mtp2` repetitions 0 and 1). No flagged window of attempt 2 had swap activity above 1,024 MiB (largest 749 MiB). The paging diagnostic is `data/analysis/stage2/2a-paging.md` (`075e88f`).
The step-A reading "repetitions 2 to 4 only" holds at 32K and 64K but not at 128K: the 128K flags are in repetitions 0 and 1 (P2-mtp2) and 0, 1, 2 (P2-mtp3), and the two P2-mtp2 units were flagged again on the fresh server of attempt 2.

**Decision tool output (`python -m smallpc.stage2 decide --stage 2a`) is not clean and its content is wrong for the re-run cells.** Status: `HUMAN DECISION NEEDED: 32K: P6-32K-b4096: the MTP-off cell is missing or not eligible`.
The `s2a-P6-32K-b4096-mtp0` cell is eligible (`data/analysis/stage2/2a.json`, `eligibility`). Cause, found by reading `src/smallpc/stage2/decide.py` and `src/smallpc/sweep/session.py` (nothing in `src/` was changed):
- `Session._job_from_resolved` (`session.py`, the re-run job) builds `Job(name, "measured", profile, data, reps, attempt=2)` without `coords=` and `resolution=`. The re-run rewrites the cell summary `data/raw/<session>/cells/<cell>.json`
  with `"coords": {}` and `"resolution": {}` (the committed pre-re-run version has them; `git show 5a53bbe:data/raw/s2a-32K/cells/s2a-P6-32K-b4096-mtp1-fc15e834.json`).
- `decide_2a` picks the top placement's cells with `_coord(c, "placement") == top.placement`, so the six re-run cells (32K P6-mtp0, P6-mtp1; 64K P6-mtp1, P6-mtp2; 128K P2-mtp2, P2-mtp3) drop out of the
  top placement's cell list. Effect in the committed output: 32K says the MTP-off cell is missing and compares only mtp2 with mtp3; 64K compares only mtp3 (best draft length 3, winner mtp0 by T_reread);
  128K reports no eligible MTP cell. **`data/analysis/stage2/2a.md`, `2a.json` and `2a-2a2-input.json` must not be used to generate the 2a2 spec.** The raw data (`records.jsonl`, `events.jsonl`, telemetry) is intact; only the
  cell-summary fields `coords` and `resolution` of those six cells were blanked, and `data/raw/` is not edited by hand.
- An in-memory run of `decide_2a` with the placement taken from the cell name (nothing written, not a result) gives no "human decision needed" at any context, but a different content from the committed output
  (32K: best draft length 2, MTP wins on T_turn_400; 64K: best draft length 1, MTP wins; 128K: no eligible MTP cell because of minimum free VRAM). That preview is not a decision.

**Eligibility, independent of the defect** (`eligibility` in `2a.json`): `s2a-P6-32K-b4096-mtp1` is ineligible only because of paging (one unresolved flagged unit, n_clean 4 of 5); `s2a-P2-128K-b4096-mtp1` (421 MiB) and `-mtp3` (443 MiB)
are ineligible only because of minimum free VRAM below 512 MiB; `s2a-P2-128K-b4096-mtp2` fails both (503 MiB, and two unresolved flagged units, n_clean 3). The continuation's stop rule (a cell ineligible only because of paging-flagged
units) applies to `s2a-P6-32K-b4096-mtp1`, so everything stops before 2a2 for the step lead.

## Stage 2a decisions (2026-11-11)

Made by the step lead after the stop report of part 2c. Recorded before any code change.

1. **Re-run summary bug.** `Session._job_from_resolved` (`src/smallpc/sweep/session.py`) builds the re-run `Job` without `coords` and `resolution`, so a re-run blanks them in the cell
   summary; the decide tool selects by coords, so six cells dropped out. The writer is fixed in B1; the six summaries (and any Stage 1 ones found in B2) are repaired in B3 from their
   pre-re-run committed versions; the committed outputs `data/analysis/stage2/2a.md`, `2a.json` and `2a-2a2-input.json` are superseded and regenerated in step C (old versions stay in git
   history). Why the tests missed it: the re-run tests did not check `coords` or `resolution` in the cell summary.
2. **`s2a-P6-32K-b4096-mtp1`** is ineligible under the declared rule (repetition 4 still flagged after the one re-run, n_clean 4 of 5). The rule stands. Step C reports a sensitivity
   (mtp1 counted as eligible on its 4 clean units), for information only; the decision follows the rule.
3. **The 128K gap.** `s2a-P2-128K-b4096-mtp1`, `-mtp2` and `-mtp3` are all ineligible (minimum free VRAM 421, 503 and 443 MiB, below 512; mtp2 also has n_clean 3), so the top placement
   has no eligible MTP cell and no best draft length. Rule, declared before any 2a2 data: when a context's top placement has no eligible MTP cell, 2a2 tests the second placement at every
   draft length that won in the other contexts (as decided by the tool), and the anchor is the top placement with MTP off. The same rule applies to any later context in the same situation.
4. **Why this rule.** All P2 MTP cells at 128K fail the VRAM margin because P2's `--fit-target 256` leaves no room for the draft context (about 1 GiB); P6 at 128K leaves about 1.3 GiB free
   and deserves an MTP test. This is a Stage 2 tooling rule; the step lead will fold it into the plan at the end of Stage 2.
5. **Paging picture** (part 2c report): 15 of 75 attempt-1 windows flagged (20.0%): MTP cells 14 of 45, non-MTP 1 of 30; faults from file pages of the mapped model, host cache capped at
   1.3 to 1.9 GiB; one unflagged window with 2,209 MiB swap growth; 12 of 15 attempt-2 units clean. The 2f choice (`--cache-ram 2048`) stays.

Rule changes for this continuation: code changes are limited to the re-run job builder and summary writer, the Stage 2 decide tool and spec generator (step B4 only) and their tests, plus
`tools/`; the only allowed edit of `data/raw/` is the scripted coords/resolution repair (B3) with an audit log; the swap tripwire now applies to all windows (stop if more than 10% of a
session's measured windows show `swap_activity_mib` above 1,024 MiB); a cell ineligible only for paging is a rule outcome, not a stop, except as step C says.

## Stage 2b decision and extension (2026-11-11)

Made by the step lead after the stop report of part 2d. Recorded before any 2b extension data.

1. **2b at 64K: FP16 KV wins** under the declared rule (`data/analysis/stage2/2b.md`): paired T_turn_400 difference q8 minus f16 +0.151 s [+0.050, +0.252], the CI excludes zero; paired
   ratios f16/q8: PP_fresh 0.986, TG 1.030, T_turn_400 0.977; minimum free VRAM 1,019 against 1,103 MiB; expert cache 9,472 against 9,984 MiB. The swap sensitivity (units with more than
   64 MiB swap growth removed) removed 5 of 10 units and left one paired repetition, so it had no CI and fell through to the VRAM tie-break. That is a loss of data, not evidence against
   the verdict, so it is inconclusive. **General reading, from now on:** if a swap-sensitivity re-computation of a decision has fewer than 2 paired units left, it is "inconclusive" and
   cannot overturn the rule's verdict; it is reported as such and the work continues. With 2 or more paired units left, a changed verdict stops the work for the step lead.
2. **32K mtp1 sensitivity** (draft length 1 instead of 2 if `s2a-P6-32K-b4096-mtp1` were eligible on 4 clean units): information only; the rule stands (draft length 2 at 32K).
3. **Probe-cache reuse** for four P6 cells in 2a2 and 2b (`s2a2-P6-32K-b4096-mtp2`, `s2a2-P6-64K-b4096-mtp1`, `s2a2-P6-128K-b4096-mtp0`, s2b kvq8) instead of fresh probes: accepted. The
   cache key is the full config, llama.cpp commit, model and GPU, and the values and minimum free VRAM match the 2a measurements.
4. **2b extension, declared before any of its data:** 2b is also run at 32K and 128K, on the 2a2 winner of each context (`s2a2-P6-32K-b4096-mtp2` and `s2a2-P6-128K-b4096-mtp0`), q8 against
   f16, with the same rules. Reason: FP16 KV won at 64K, and its VRAM cost grows with context (about 1.3 GiB more at 128K, which shrinks the expert cache). The tuned config of each
   context uses the KV type that wins at that context.
5. **2c is still held**; the step lead decides after this continuation. No 2c or 2d spec is generated.

## Stage 2b 32K decision (2026-11-11)

Made by the step lead after the stop report of part 2e. This is a **human decision, not the rule's output**; `data/analysis/stage2/2b.json` and `2b.md` stay as the tool wrote them, and
`data/analysis/stage2/2b-human-decision.md` records the decision beside them.

1. **Decision:** the 32K tuned config uses **FP16 KV** (`-ctk f16 -ctv f16`).
2. **The two readings at 32K** (`s2b-32K`, P6, b4096, mtp2, 5 clean units per cell):
   - *Rule's verdict:* **kvq8** by step `t_reread`. T_turn_400: kvf16 5.546 s [5.291, 5.800], kvq8 5.596 s [5.437, 5.755]; paired difference +0.050 s [-0.050, +0.151] (includes zero).
     Paired T_reread difference -0.038 s [-0.052, -0.025] (excludes zero; kvq8 lower, 7.370 against 7.408 s).
   - *Swap sensitivity:* repetition 1 of both cells removed (699 and 637 MiB of swap growth), 4 paired units left: **kvf16** by `ci_excludes_zero`, paired T_turn_400 +0.083 s [+0.019, +0.147]
     (means 5.469 against 5.552 s).
3. **Reason:** the two readings disagree and neither is robust, so 32K is treated as a tie; both put the difference at about 1 % or less. The tie is broken by simplicity: FP16 is
   llama.cpp's default and lossless, it won by the rule at 64K and 128K, and the tuned configs then need no KV flags.
4. **64K and 128K:** kvf16 by the rule, unchanged (64K +0.151 s [+0.050, +0.252], the sensitivity inconclusive with 1 paired unit; 128K +0.683 s [+0.435, +0.932], the sensitivity unchanged).
5. **Consequence:** the provisional tuned configs of all three contexts use FP16 KV: 32K `s2b-P6-32K-b4096-mtp2-kvf16`, 64K `s2b-P6-64K-b4096-mtp1-kvf16`, 128K `s2b-P6-128K-b4096-mtp0-kvf16`. 2c is still held.

## Stage 2 sanity result and closing decisions (2026-11-11)

Made by the step lead after the report of part 2f. Recorded before any diagnostic data.

1. **The sanity result** (`data/sanity/stage2-{32K,64K,128K}.json`). Both 32K candidates, `s2b-P6-32K-b4096-mtp2-kvf16` and `s2a2-P2-32K-b4096-mtp2`, fail prompt `sanity-v5-2048-r0` on the 8-gram
   rule: the maximum 8-gram repeat is 8 against the reference's 2; the distinct 4-gram ratio is 0.831 and 0.841 against 0.917; the first divergence from the reference is at token 27 for both.
   Everything at 64K and 128K passes. **The rule stands:** a candidate that fails the sanity check is ineligible (plan §3.3, §5.6), so MTP at draft length 2 cannot be the 32K tuned config. The
   thresholds are not changed.
2. **The 2b KV decision at 32K** (FP16, a tie broken by simplicity; "Stage 2b 32K decision") was about draft-length-2 cells, so it is void for the 32K tuned config; the 32K tuned config uses
   the KV type of the cell that wins in the 32K final selection. 64K and 128K stay FP16 (by the rule).
3. **2c (`--load-mode dio`) is not run.** Reasons: it was meant to remedy the paging problem, which `--cache-ram 2048` solved (1 flagged window of 100 in 2a2, 2b and the 2b extension); dio
   pins 18.9 GiB of unswappable memory on a 32 GB machine with the desktop open; no problem is left for it to solve. **2d is skipped** (the default thread count is already 8). Both are plan
   deviations that the step lead will fold into the plan.
4. **Pre-declared reading of the sanity diagnostic** (written before its data exists; the diagnostic runs the P6 and P2 cells of `s2a-32K` as measured, with q8 KV, a self-comparison of the
   reference, a repeat of the two failing cells, and the draft-length-2 control `s2a-P6-64K-b4096-mtp2`):
   - If the MTP-off 32K cells ALSO fail, or if the reference run differs from itself, or if a repeat of a failing cell passes: STOP and report.
   - If MTP-off and draft lengths 1 and 3 at 32K pass, and draft length 2 fails at 64K as well: draft length 2 is excluded from all tuned configs (a finding for the executive chat).
   - If draft length 2 passes at 64K: the failure is specific to the 32K family with draft length 2; it is reported as such.
   In every case the rule's result stands.


## WP13 decisions (2026-11-12)

WP13 part 1 prepares Stages 3 and 4 (tooling, config files, specs, runbook, short GPU checks). Plan v1.7 is adopted (commit `392f80f`, line 3 reads
`*Version 1.7 · 11 November 2026*`). These decisions are recorded before any code of this work package and before any Stage 3 data. No real Stage 3 or Stage 4
session is started in this work package.

### Stage 3 and Stage 4 rules of plan v1.7, section 5.4 (verbatim, copied from `docs/plans/step-0-baseline.md` lines 230 to 243)

> **Stage 3: Final** (5 repetitions, paired; WP13; about 2.5 hours on a quiet machine)
>
> Stock-C against tuned-C for each C. These are the headline results, so gate G3 applies in full: the desktop apps are closed. Rules, declared before any Stage 3 measurement:
> - **Configurations.** The six cells are the released config files, `configs/server/{stock,tuned}-{32k,64k,128k}.toml`. The tuned files are the Stage 2 winners above. Stock is §3.1 unchanged, including its default host prompt cache. The measured argument lists are exactly what those files render, plus `--metrics -lv 4`.
> - **Sessions.** One session per context, each with its own start and end canaries, from a clean committed tree. Stock and tuned of a context share a session, so their repetitions are paired.
> - **Re-runs.** One `--rerun-flagged` pass per session, as before.
> - **Stock paging.** Stock keeps `--cache-ram 8192`, so its later repetitions may be paging-flagged at 64K and 128K. That is how stock behaves on this machine, so it is reported, not hidden. Every stock-against-tuned comparison is computed twice: on clean units only, and on all units with the flags shown.
> - **Headline rule.** The headline for a context is the clean-units comparison if both cells have at least 5 clean, paired units after the re-run pass. Otherwise the headline is the all-units comparison, labelled "includes paging-flagged stock windows", with the clean-units figures beside it, and S4(d) is recorded as a deviation for that context. If the two versions disagree in sign, or one interval excludes 1.0 and the other does not, the report says so in its first paragraph.
> - **Tuned cells.** A tuned cell must be eligible in final mode (§3.3): 5 clean units, at least 512 MiB of VRAM free, and a sanity pass. The sanity check is run again on the three tuned config files. If a tuned cell is not eligible, the step lead decides; nothing is substituted automatically.
> - **Reported figures.** Per context: T_turn_400, T_B with `predicted_n`, T_reread, PP_fresh and PP_inc per depth, TG per depth, TTFT, the VRAM breakdown, and the paired ratios tuned/stock with 95% CIs (§5.5), plus the swap sensitivity.
>
> **Stage 4: Reproducibility** (a different day; WP13; about 30 minutes on a quiet machine)
>
> Stock-64K and tuned-64K, 5 repetitions each, in one session with canaries. S2 is checked with `report repro` on T_turn_400, fresh prefill at 32K and decode at 32K depth. If stock-64K has too few clean units on either day, S2 is evaluated for it on all units, and the report says so.

### Gate G3 applies in full to Stages 3 and 4
Stages 1 and 2 ran with desktop apps open and idle, as a recorded deviation. Stages 3 and 4 produce the headline results, so G3 (plan section 7) applies in full:
browser, IDE, music and chat apps, system monitors, games and VMs are closed, the PC is on mains power, nothing else uses the GPU, and Zack does not use the PC during a session.
This is enforced by `scripts/check-quiet.sh` (process names only, blocklist in `configs/quiet-check.toml`), run before every session and recorded in `docs/stage3-conditions.md`;
it is not run as a gate in the preparation checks of this work package, where the desktop apps are open.

### Known limitation: the 32K tuned config uses 8-bit KV as measured
The 32K tuned config is the Stage 2 final-selection winner `s2a-P6-32K-b4096-mtp0` with 8-bit KV (the sweep default, `-ctk q8_0 -ctv q8_0`). FP16 against 8-bit KV at 32K was
measured only on draft-length-2 cells (2b extension), which the sanity check excluded, so the 32K KV type of the tuned config is the default and not a 2b result. FP16 won at 64K and 128K
by the rule. Stage 3 reports the 32K tuned cell as it is; it does not test FP16 at 32K.

### Corrections to plan v1.7 (for the step lead to fold into the next plan version; the plan file is not edited)
Checked against `docs/stage2-summary.md`, `data/analysis/stage2/*.json` and the sessions under `data/raw/` (`smallpc.analysis` over the sessions; paired ratios by `smallpc.stats`).
The Stage 2 outcome table (tuned configs, T_turn_400 means and intervals, Stage 1 stock values) agrees with `docs/stage2-summary.md`. Statement by statement:

1. **"1 flagged window of 100 in the later sessions" (plan 5.4, Stage 2 outcome, "Not run") is wrong: it is 1 of 80.** The later sessions have 15 + 15 + 20 (`s2a2-32K|64K|128K`) + 10 (`s2b`)
   + 10 + 10 (`s2b-32K`, `s2b-128K`) = 80 attempt-1 windows; the one flagged window is `s2b-P6-64K-b4096-mtp1-kvf16` repetition 2. The same figure (and the same wrong total) appears in
   this file, "Stage 2 sanity result and closing decisions", item 3 ("1 flagged window of 100 in 2a2, 2b and the 2b extension"): the old entry is not rewritten, this is its correction.
   For context, 2a (the first sessions with `--cache-ram 2048`) had 15 of 75 windows flagged (14 of 45 in MTP cells), so "removed the paging" holds for 2a2 and later, not for 2a.
2. **"MTP helped by about 3 to 5% per turn at 32K and 64K" should read about 2 to 5%:** 4.6% at 32K (draft length 2, an excluded configuration) and 2.4% at 64K (draft length 1).
   (2a effects: off minus MTP +0.288 s [+0.121, +0.455] at 32K and +0.168 s [+0.052, +0.285] at 64K; the percentages are those differences over the MTP-off mean T_turn_400.)
3. **"it costs 9 to 15% of prefill speed and about 1 GiB of VRAM" (checked, roughly right):** paired PP_fresh ratio MTP / off is 0.910 at 32K (draft length 2), 0.893 at 64K (draft length 1),
   0.849 / 0.838 / 0.844 at 128K for P2 draft lengths 1 / 2 / 3 (the draft-length-2 cell has n = 3) and 0.866 for P6 draft length 1 against off at 128K (unpaired means): 9 to 16%, so "9 to 15%"
   is about one point short at the top. VRAM: the P6 max-fit expert cache with MTP is smaller than without by 768 MiB (32K), 1,024 MiB (64K) and 1,536 MiB (128K), and peak VRAM at equal or smaller cache is
   higher by 184 to 322 MiB; "about 1 GiB" fits 32K and 64K and understates 128K (probe caches in `data/probes`, cells in the sessions above).
4. **"Only 0 was entirely free of faults and swap" (2f, checked, correct):** at 128K, `--cache-ram 0` has 0 faults and 0.0 MiB swap activity in all 5 windows; 2048 has repetition 1 at 889 faults and
   450.6 MiB, 4096 and 8192 more. At 64K the tested 2048 has 547.6 MiB of swap growth in repetition 1 (0 was not tested at 64K).
No discrepancy changes a tuned config.

### Decisions on the work of this package
1. **`analysis.py` exception (approved by Zack).** `parse_fit_placement` counted every CUDA0 `sched_reserve ... compute buffer` line, so an MTP cell's compute buffers were counted twice.
   The parser change needs one line in `analysis._vram_parts` (stored cell summaries hold the old list; `data/raw` is not edited). Nothing else in `analysis.py` changes. Regression check before
   and after: `smallpc.select` (screening over the three Stage 1 sessions; final over `s2a-32K` with `data/sanity/stage2-all.json`) and `smallpc.stage2 decide --stage 2a|2a2|2b` are saved before
   the change and diffed after; the outputs must be byte-identical except VRAM-breakdown fields, otherwise the `analysis.py` change is reverted.
2. **Spec format.** A reference cell (`config = "..."`) had no coordinates (so `--only context=...` dropped it) and received no `[defaults]` (so it could not get `--metrics -lv 4` without
   those flags being written into the released config files). Smallest change, in `config.py` and `sweep/spec.py` only: reference cells take an optional `coords` and an opt-in `apply_defaults`
   (a key set by both the file and the defaults with different values is an error). No existing spec changes meaning; the runner, session and measurement code are untouched.
3. **Config files** set only `profile` and `context` (and the tuned fields); model, host and port come from `configs/model.toml` and `configs/machine.toml`, exactly as in every Stage 1 and 2 cell.
4. **Headline tool.** The two views of the headline rule use the same analysis code: the clean view is `smallpc.analysis` as it is; the all-units view is the same `_cell_entry` run on the final
   (non-superseded) units with every unit counted. `python -m smallpc.stage3 repro` exists because `report repro` evaluates clean units only.
5. **Gate.** `python -m smallpc.stage3 gate` reuses the Stage 2 gate functions (not modified). Criteria a to e as in Stage 2; criterion f (more than 40% of windows paging-flagged, or any flagged window
   above 1,024 MiB of swap growth) is computed over the TUNED cells' windows and the canary windows only. The STOCK cells' paging and swap figures are reported and never fail the gate (plan 5.4,
   "Stock paging").
6. **Quiet check.** `scripts/check-quiet.sh` reads process names only (`ps -eo comm`; never window titles, URLs, command lines or file contents), compares them with the blocklist in
   `configs/quiet-check.toml`, warns about other processes above 1.5 GiB resident memory (name and size only), exits 1 if a blocklisted app runs, and prints the CPU idle figure as information.
   The desktop environment, the terminal and claude are allowed.
7. Not changed: flags, eligibility, selection, statistics, the sanity thresholds, the request protocol, the workload code, the sweep runner's measurement code, the Stage 2 gate and decision code.

## WP13 part 2 decisions (Stage 3 sessions, 2026-11-12)

1. **S4(d) deviation for 128K (recorded by Claude, the step lead confirms).** The 128K headline is the all-units comparison, labelled "includes paging-flagged stock windows",
   because stock-128K has 4 clean units after the one re-run pass and tuned-128K has 5 (4 paired; 5 needed for the clean-units headline). Unit `stage3-128K:3` of the stock cell is
   still paging-flagged in attempt 2 (22,810 major faults, 4,200 MiB swap growth; attempt 1 had 2,004 faults). Rule S4(d): no headline number rests on a measurement with an unresolved
   flag; here the all-units headline does, and says so. The clean-units figures stand beside it (tuned/stock T_turn_400 0.711 [0.673, 0.750], n = 4, against 0.706 [0.679, 0.735], n = 5 for all units):
   the two versions agree in sign and in whether each interval excludes 1.0. 32K and 64K use the clean-units headline. No tuned cell was ineligible and no sanity failure occurred.
2. **Plan v1.8 adopted** (`8096461`, line 3 `*Version 1.8 · 12 November 2026*`). Five plan-version literals in `tests/` (`test_stage2_rules`, `test_stage2_decide`, `test_stage3_headline`) read 1.7 and failed against the v1.8 plan file; they now read 1.8 (`422eada`). Nothing in `src/`, `configs/` or `scripts/` changed.
3. **Reading of the paging flags (not a rule change).** Contrary to plan 5.4's expectation, the 64K session's *tuned* cell was paging-flagged in 4 of 5 attempt-1 windows (up to 47,576 major faults, 586 MiB swap growth), and the stock cell in none; at 32K and 128K stock paged (1 and 2 windows) and tuned did not. The gate's criterion f passed (36.4% of tuned and canary windows, limit 40%). The four tuned units re-ran clean in attempt 2 (0 faults).
   No explanation was investigated: the machine was quiet (check-quiet QUIET at every poll) and the swap sensitivity shows no change in any verdict.
4. **Intermittent test.** `tests/test_sweep_probe.py` failed a different test in 2 of 4 full runs (and in most of the file's own repeat runs) on this machine (for example `test_max_fit_is_probed_per_draft_length_for_mtp_cells`: 3,840 against 8,704 MiB) and passed the last full run (994 passed). Not investigated; it does not touch the Stage 3 data or tools.

---

## DECISION E-001 (2026-11-12T23:03:27Z)

DECISION E-001
Chosen option: A
Reason: The three Stage 3 session commits (8096461, a80b2dd, b5b7396) differ only by data and re-run commits, and git diff over src, configs, scripts, pyproject.toml and uv.lock between them is empty, so one code state exists; the earliest commit gives R3 the strictest span. The allow list lacked the measurement commands, and Zack widened it himself in a separate commit because the executor must not widen its own permissions.
Scope: this plan
Rule: (1) A5: record 8096461 in docs/recon/stage3-commit.txt; "the Stage 3 session commit" in R3 and the Stage 4 record means 8096461. Mark A5 PASS with a note that the three commits share one code state; state this once in docs/recon/T-001.md. (2) A14: Zack has updated .claude/settings.json (see the latest commit touching it). T-001 re-checks A14 by matching the commands against the updated file, and records any command still unmatched as an INFO line, not a FAIL, and does not edit settings.json. git push, git tag, gh and curl are deliberately not allowed; they prompt at T-015. (3) A7: D2's bracket is "17 attempt-1 windows (tuned-64K 5, four canary cells x 3; stock excluded): 4 flagged = 23.5%; the gate tool reported 36.4% (4 of 11, re-run canary cells excluded); true pass under both". Docs quote the tool's 36.4% together with this sentence.

---

## DECISION E-002 (2026-11-13T09:07:05Z)

DECISION E-002
Chosen option: A
Reason: scripts/wf.sh is the kit dispatcher added by install commit f149338 and listed in .workflow-kit-manifest.json, with the same provenance as the wf-*.sh scripts; the pattern in PLAN.md was written too narrowly (a planning-chat error), and no code change or re-measurement is involved.
Scope: standing rule
Rule: Wherever PLAN.md (R3, A2, the T-001 acceptance, the T-007 precondition) uses the pattern scripts/wf-[A-Za-z0-9_.-]+\.sh for the allowed kit files, read it as scripts/wf(-[A-Za-z0-9_.-]+)?\.sh. For T-001 acceptance criterion 5, run the command with that corrected pattern, record its output in docs/recon/T-001.md under the heading "E-002 corrected check", and treat the criterion as passed by decision E-002. Do not edit PLAN.md or any card; the planning chat re-issues PLAN.md with the corrected pattern via --amend after T-001 is done. If the kit cannot record the criterion as passed by decision, stop and say so in one line instead of escalating again.

---

## 2026-11-12: Step-lead decisions after Stage 3 (planning chat)

<!-- sources: PLAN.md, docs/recon/T-001.md, docs/decisions.md -->

Recorded verbatim from the shared rules of card T-002 (PLAN.md v1.1, frozen with the
plan). The only change: D2's bracket is filled with A7's finding from
docs/recon/T-001.md, verbatim per decision E-001 rule (3).

**Stage 3 decisions (planning chat, 12 November 2026)**
- D1 The 128K headline uses all units, with the label "includes paging-flagged stock windows" and the clean-units figures beside it; S4(d) is a recorded deviation for 128K. This is the declared §5.4 rule, not a judgement call. Until T-009 fixes the rendered report (which calls stock-128K "not reportable"), data/analysis/stage3/headline.md is authoritative.
- D2 The tuned-64K paging is the known file-page faulting of the MTP cell seen in Stage 2a; it is not investigated. Gate denominator per A7: 17 attempt-1 windows (tuned-64K 5, four canary cells x 3; stock excluded): 4 flagged = 23.5%; the gate tool reported 36.4% (4 of 11, re-run canary cells excluded); true pass under both. If stock windows were counted and the gate truly failed, it is accepted as a recorded deviation without re-measurement, because all four flagged units re-ran clean on fresh servers and the cause matches Stage 2a.
- D3 The 32K swap sensitivity is not material. The point estimates barely move, and the wider intervals come from dropping 3 of 5 pairs. Docs state it (§5.5) and call the 32K decode gain small and not robust to excluding swap-active units. The T_turn_400 conclusions are unchanged.
- D4 The edit of five test literals to "1.8" (commit 422eada) is accepted; CI was red at 8096461. T-009 makes the tests read the version from the plan file.
- D5 The flakiness of tests/test_sweep_probe.py is fixed before release (T-009).
- D6 Phase 0's HEAD check, read as HEAD = 8096461 with a clean tree, is accepted.
- D7 The sanity output is named data/sanity/stage3-tuned.json (the runbook said stage3-all.json). Accepted as a minor deviation; docs cite the actual name.
- D8 Git history is not rewritten. The Linux account name in the early WP0 commit matches the author name already public on every commit, and a rewrite would break the commit hashes that data and logs refer to. The current tree is scrubbed, and the history scan escalates only for findings beyond that known occurrence. No committed file may contain the account name; refer to it as <account-name>.
- D9 Expert-cache hit rates are reported with the caveat that they include warm-up and the attempt-1 units of re-run windows. The figure axes (prefill and decode from 0, predicted_n labels clear of the whiskers) are fixed in T-009.
**Stage 4 rules (declared 12 November 2026, before any Stage 4 data)**
- R1 Tuned-64K gets stock's fallback. If it has fewer than 5 clean units after its re-run, S2 is evaluated for it on all units, labelled as such, and recorded as an S4(d) deviation.
- R2 If the Stage 4 gate fails only because of tuned-64K paging, and every flagged unit re-runs clean, the session is accepted with a recorded deviation: a docs/decisions.md line starting "- R2 applied: Stage 4". Any other gate failure is escalated.
- R3 Stage 4 runs on 13 November 2026 or later. Since the Stage 3 session commit, the only changes under src/, configs/, scripts/, pyproject.toml and uv.lock are the kit's new scripts/wf.sh, scripts/wf-*.sh and scripts/_wf.py, and the only existing files changed by the kit install are CLAUDE.md and .gitignore. Check: `S3=$(cat docs/recon/stage3-commit.txt) && git cat-file -e "$S3^{commit}" && ! git diff --name-only "$S3" HEAD -- src configs scripts pyproject.toml uv.lock CLAUDE.md .gitignore | grep -vxE 'CLAUDE\.md|\.gitignore|scripts/wf(-[A-Za-z0-9_.-]+)?\.sh|scripts/_wf\.py'`
- R4 An S2 failure is reported and escalated, never re-measured automatically.


---

## DECISION E-003 (2026-11-13T10:09:30Z)

DECISION E-003
Chosen option: B
Reason: The diff implements the precedence rules correctly (kit wins session flow, umbrella wins safety and the section 12.4 report, kit block byte-identical, --allow-dirty added); two lines need changing because a session-wide stop on any blocked task would freeze other lanes while one task waits for a decision, and because lane choice must be asked, not made by the session.
Scope: this plan
Rule: Apply the drafted diff with exactly two replacements in the new "Every session starts by" section; everything else is approved unchanged. Regenerate docs/recon/claude-md-merge.diff so it contains the replacement lines and passes git apply --check, apply it, and save the final applied diff over docs/recon/claude-md-merge.diff.
Replace item 2 (the two lines beginning "2. Running `bash scripts/wf.sh status`") with:
2. Running `bash scripts/wf.sh status`. A task in blocked-decision waits for the planning
   chat's decision (`wf-decision.sh`): never work on it by hand, but it does not stop other
   ready tasks. If the task you were asked to resume is blocked, show its open escalation
   and stop.
Replace item 3 (the two lines beginning "3. Picking the next task") with:
3. Picking the next task from `bash scripts/wf.sh ready` (if several lanes are ready, ask which
   lane to start, as `/continue` does), claiming and starting it, and reading ONLY its card
   (`bash scripts/wf-card.sh T-xxx`) — never `PLAN.md` whole.

---

## DECISION E-005 (2026-11-13T12:52:02Z)

DECISION E-005
Chosen option: B
Reason: The diagnosis is sound: recompute_ready re-promotes lane-owned placeholders to ready, so the guard fails whenever lanes run concurrently. The fix is small but touches the engine, so it waits until after Stage 4; until then an exact, narrow exception avoids deadlocking the sessions that must run to clear it.
Scope: standing rule
Rule: (1) Interim exception: when the ONLY failing guard lines are of the exact form "GUARD: task T-NNN is in the main state as ready AND in lane N; run wf.sh merge-lanes N", AND bash scripts/wf.sh status shows that task as in-progress, awaiting-gate or blocked-decision, treat the guard as non-fatal and continue; never run merge-lanes N for an active lane. Any other guard line, or such a line where status shows the task as ready, todo or done, stops the session as before. State is still never edited by hand. (2) The fix (recompute_ready leaves tasks owned by a lane mirror alone, with a regression test for concurrent lanes) is scheduled as a new task T-018 after T-008. The planning chat adds it in the next PLAN.md amend; sessions do not add it. scripts/_wf.py is a kit file, so R3 allows the change; it must not happen before Stage 4.

---

## DECISION E-004 (2026-11-13T12:52:02Z)

DECISION E-004
Chosen option: B
Reason: The design is well grounded in the recon. /lane N asks no question, so it is deterministic headlessly, whereas piping yes to /continue is untested and an unattended loop should not rest on an unverified mechanism.
Scope: this plan
Rule: Design in docs/recon/loop-design.md approved with these changes. (1) Lane answer: when tasks in several lanes are ready, the loop starts the lowest-numbered such lane with claude -p "/lane N"; when only one lane has ready tasks it runs claude -p "/continue". The card's literal /continue prompt is relaxed accordingly for this task. (2) T-017 never runs /continue, /lane or /review headlessly in its own tests; fake claude only. (3) The loop stops on any guard failure except the placeholder line defined in the E-005 decision. (4) keep-continuing.md and the loop's start message tell the user to make the first real run a supervised one of about 1 hour while awake. (5) The loop's final message names the stop reason and the task id.

---

## DECISION E-006 (2026-11-13T18:21:00Z)

DECISION E-006
Chosen option: A
Reason: The kit cannot open a review on a ready task, no task in PLAN.md has review pre+post any more (T-007 is post-only since v1.2), the gap is documented in loop-design.md section 11.3, and the loop's pre-review branch is inert and safe, so no code change is needed.
Scope: this plan
Rule: (1) Pre-reviews are not performed under the frozen kit; the loop's pre-review branch stays as inert code. (2) Options B and C are not scheduled; they are reconsidered only if a pre+post task is ever added, and would then ride along with the T-018 kit change (T-018 is the E-005 guard fix, added by the planning chat after T-008). (3) T-017's code is complete: after this decision it may be accepted and finished (re-run accept if the evidence hashes need refreshing, then close it through the kit's normal commands). (4) F-2 follow-up: record in docs/decisions.md, under this decision, the commit hashes that introduced the path docs/recon/loop-states.md with the account name in a home path, and the fix commit bc8e0c3 that removed it. Find the introducing commits with git log --format=%h -S"$VAR" -- docs/recon/loop-states.md, where $VAR is a shell variable holding the string; never write the account name into any file, escalation brief or log. These commits are a second known occurrence for T-013's history scan, allowlisted by commit hash and path only.

**F-2 follow-up (E-006 rule 4, recorded 2026-11-13 by the T-017 address-review session).** The account home path (the `<account-name>` of D8; never written here) in `docs/recon/loop-states.md` was introduced by commit `3f41e18` (T-017 S1–S2 recon) and removed by fix commit `bc8e0c3` (T-017 address review cycle 1, F-2). Found with `git log --format=%h -S"$VAR" -- docs/recon/loop-states.md`, where `$VAR` was the home-path prefix built from the live account (`/home/$(id -un)`) — the account name was never written into any file, brief or log. This is the second known occurrence for T-013's history scan (the first is the WP0 occurrence already allowlisted by D8), allowlisted by commit hash and path only: `3f41e18` and `bc8e0c3`, path `docs/recon/loop-states.md`. No history rewrite (D8).

---

## DECISION E-007 (2026-11-13T18:42:53Z)

DECISION E-007
Chosen option: A
Reason: The card's "escalate once listing every failure" attaches to the final Result. The P8 FAIL was caused by another lane's uncommitted work, cleared by that lane's own commits before T-019 filed anything, with no workaround by T-019 and the full sequence documented and independently verified by the reviewer.
Scope: this plan
Rule: (1) Ratify the reading in stage4-preflight section 2.9 for T-019. Precedent, scoped exactly: a pre-flight or recon check that FAILs transiently needs no escalation when ALL of these hold: the cause is another lane's legitimate work cleared by that lane's own commits; the checking session applied no workaround and committed no other lane's files; the check was re-run and passed; the final Result is all-PASS; the whole sequence is documented in the output file. Any other FAIL still escalates. Record this one line in docs/decisions.md under this decision. (2) T-019 may now be closed through the kit's normal commands; no review cycle 2 is needed because no BLOCKER or MAJOR was fixed. (3) F-3 (runbook line 146: 1,578 should be 1,577) and the review-parser limitation on findings whose action has a parenthetical (scripts/_wf.py:1918) are routed by the planning chat into the T-018 amend after T-008; sessions do not add or fix them.

**Precedent (E-007 rule 1, recorded 2026-11-13 by the T-019 closing session).** A pre-flight or recon check that FAILs transiently needs no escalation when ALL of these hold: the cause is another lane's legitimate work cleared by that lane's own commits; the checking session applied no workaround and committed no other lane's files; the check was re-run and passed; the final Result is all-PASS; the whole sequence is documented in the output file. Any other FAIL still escalates.

---

## DECISION E-008 (2026-11-14T11:14:40Z)

DECISION E-008
Chosen option: A. Stage 4 run 1 is invalid for S2 because the GPU's PCIe link ran at Gen3 x8 instead of Gen4 x8 for the whole session. Restore and verify the Gen4 x8 link under load (new task T-020), then re-measure Stage 4 as a new gated task (T-021, run 2). Options B and C (accept run 1 as-is, or widen the S2 tolerance to absorb the slowdown) are rejected.
Reason: S2 asks whether the same configuration reproduces on the same machine. Run 1 did not run on the same machine state (a slower link, about 25 to 40 percent slower prefill, lower power draw, same clocks), so a FAIL there says nothing about reproducibility, and a PASS obtained by widening the tolerance would be meaningless. The within-session drift rule could not catch this because the link was wrong from the first request.
Scope: Stage 4 run 1 (session id in docs/recon/stage4-session.txt) is marked superseded, never deleted, and reported as an excluded diagnostic. Its raw data, session file and any analysis outputs stay in the repo. T-008 is re-pointed at run 2 and depends on T-021. Planning-chat PLAN.md v1.3 adds T-020 and T-021 and rules R5 to R7. No code, config or script changes. This is the approved escalation that shared rule 3 requires for a RE-MEASURE.
Rule: R5 run 1 is superseded and run 2 (docs/recon/stage4-session-run2.txt) is the S2 run, with R1 to R3 unchanged. R6 run 2 is the only re-run: if it fails S2 with the link verified Gen4 x8 at the start and at every poll, that is a genuine FAIL, escalated under R4, and there is no run 3 without a new decision. R7 every gated GPU session samples the link under load and stops and escalates on anything other than gen 4, width 8. If the link cannot be restored to Gen4 x8, do not run Stage 4 at Gen3: escalate.

---

## 2026-11-14: Stage 4 run 1 invalid, E-008

- R5 (declared 14 November 2026, after E-008) Stage 4 run 1, whose session id is in docs/recon/stage4-session.txt, is invalid for S2: the GPU's PCIe link ran at Gen3 x8 instead of Gen4 x8 for the whole session. Run 1 is marked superseded, never deleted, and is reported as an excluded diagnostic. Run 2 (docs/recon/stage4-session-run2.txt) is the S2 run. R1 to R3 apply to run 2 unchanged.
- R6 Run 2 is the only re-run. If run 2, with the link verified at Gen4 x8 under load at the start and at every poll, fails S2, that is a genuine S2 FAIL: escalate under R4, and no run 3 without a new decision.
- R7 Every gated GPU session checks the link under load with nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.width.current --format=csv,noheader. Anything other than "4, 8" while a server is generating stops the session and escalates; it is never averaged into the data.
- Run-1 session id: `stage4` (`docs/recon/stage4-session.txt`), superseded, never deleted (R5). T-020 verified the restored link at Gen4 x8 under load on 2026-11-14 (`docs/recon/pcie-link.md`, `Result: link PASS`); run 2 (T-021) proceeds under R5 to R7.
- Run-2 session id: `stage4-run2` (`docs/recon/stage4-session-run2.txt`), launched 2026-11-14T14:30:49Z from `c4bdc4d` (clean tree, R3 PASS); main 26.1 min + one re-run pass 9.2 min; gate PASS a to f before and after the re-run; every under-load link sample read "4, 8" (R7; idle-gap downshifts recorded, not averaged, in `docs/stage4-run2-conditions.md`). Both cells end with 5 clean units; R1 fallback and R2 not needed. This is T-008's S2 run (R5). <!-- sources: docs/stage4-run2-conditions.md, data/raw/stage4-run2/session.json -->

## 2026-11-14: Kit exception, T-018

- Kit exception (T-018): the Shared rule 2 code freeze was lifted for the kit scripts `scripts/_wf.py`, `scripts/wf.sh`, `scripts/wf-decision.sh`, `scripts/wf-escalate.sh` and one new kit test file (`tests/test_wf_unblock.py`) only, because the kit could not leave blocked-decision after a review verdict of blocked-decision (T-021 stuck: the verdict recorded no `blocked_from`, escalate overwrote it with blocked-decision, unblock fell back to the illegal `todo`, and decision wrote `docs/decisions.md` before the failing unblock); fix commit `9d91d5a` changed only `scripts/_wf.py` (the three shell wrappers dispatch unchanged), ruled 14 November 2026 in plan v1.4; evidence `docs/recon/T-018-kit-repair.md`.
