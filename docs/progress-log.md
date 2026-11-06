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
