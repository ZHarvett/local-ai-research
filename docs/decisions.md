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
  `/mnt/data` is owned by `zack:zack` (mode 755), so no sudo was needed.
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
