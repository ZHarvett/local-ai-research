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
- iGPU: BIOS left at its default; both displays are on the iGPU (card0, amdgpu).
- PBO/Eco mode: BIOS default, never changed by Zack; exact mode not recorded.

## WP3 decisions (2026-11-08)

### Desktop GPU steering (apps prefer the iGPU)
- **What:** after WP2 (2026-11-07) and before WP3 (2026-11-08) Zack moved both monitors to the iGPU
  outputs and then configured the desktop session so that applications prefer the iGPU. Zack did this
  without telling Claude Code how; the exact time is not recorded.
- **Mechanism:** NOT IDENTIFIED. A read-only search found no GPU-selection variable or setting
  (`DRI_PRIME`, `__NV_PRIME_RENDER_OFFLOAD`, `__GLX_VENDOR_LIBRARY_NAME`, `VK_ICD_FILENAMES`,
  `VK_DRIVER_FILES`, `MESA_VK_DEVICE_SELECT`, `WLR_DRM_DEVICES`, `AQ_DRM_DEVICES`, EGL vendor) in
  `~/.config/environment.d` (absent), `~/.config/cosmic`, `~/.config/fish`, `~/.config/systemd/user`,
  `~/.zprofile`, `~/.profile`, `~/.zshenv`, the systemd user manager environment, the session
  environment, the cosmic-comp process environment, `/etc/environment`, `/etc/profile.d` or
  `/etc/udev/rules.d`. The only file in those directories modified in the last 3 days is
  `~/.config/cosmic/com.system76.CosmicPortal/v1/screenshot`, which is unrelated. Zack to name the
  mechanism (file and setting) so it can be recorded here.
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
- **How to undo (description only, not run):** remove or revert whatever Zack set (to be named by
  Zack) and log in again; the desktop then returns to the G1 state.
- **Games:** applications now render on the iGPU. A game that should use the RTX 5060 Ti needs a
  per-application launch option (the PRIME-offload variables of the chosen mechanism).
- **Status:** this state is part of the frozen machine tuning (step plan section 4). Any change to it
  triggers the short re-check (the canary set).

### Flag table verified against build b12208
- All 22 flags in `FLAG_TABLE` exist in `llama-server --help`; none needed renaming, so the golden
  argv files are unchanged. Widened to what the build accepts: `spec_type` (11 values including
  `draft-mtp`), `load_mode` (`auto, none, mmap, mlock, mmap+mlock, dio`), `log_verbosity` 0-5.
- Build choices: newest b-tag built (b12208); upstream's newest semver tag
  (v0.9.0) is recorded in `build-info.json` only; CMake rewrote `CMAKE_CUDA_ARCHITECTURES=120` to `120a`.
