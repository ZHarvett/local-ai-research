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
