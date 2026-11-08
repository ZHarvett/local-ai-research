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
