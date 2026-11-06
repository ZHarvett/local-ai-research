# CLAUDE.md — Local AI on a Small PC (umbrella repo)

Repository (absolute path): `/mnt/data/local-ai-research` (256 GB SK hynix NVMe, mounted at `/mnt/data`).

## Project
Measured baseline for running Ornith-1.5-35B-A3B (Q4 GGUF, MoE) with mainline llama.cpp on a
16 GB RTX 5060 Ti PC: stock vs tuned server configs at 32K/64K/128K context, with OpenCode and
dsh harnesses. Step 0 = baseline setup, ending in a tagged v0.1.0.
Plans: `docs/plans/project-plan.md` (whole project), `docs/plans/step-0-baseline.md` (Step 0 reference).

## Every session starts by
1. Reading the current work package's section of `docs/plans/step-0-baseline.md` (§6, plus the
   sections it points to: §4 fixed decisions, §5 measurement design, §8 layout, §11, §12).
2. Reading the latest entry in `docs/progress-log.md`.

## Hard rules
- Never use sudo or change system configuration. Propose the exact commands; Zack runs them.
- Never delete or modify anything outside this repo, except scratch dirs in `/tmp` and
  `/dev/shm/<repo>-*`.
- Never modify existing installs, services, `~/.config/opencode` or `~/.dsh`.
- No downloads over 1 GB beyond those in the step plan without approval.
- Only one GPU job at a time, enforced by the GPU lock.
- Anything that may take longer than ~8 minutes runs via `scripts/run-detached.sh`.
- Do not change global git configuration. No GitHub remote/push unless the WP says so.

## Conventions
- Bash for launch/long-job scripts; Python via uv; TOML configs.
- uv, ruff, pytest (`-m "not gpu"` in CI) and shellcheck.
- llama-server is started only through `scripts/launch-server.sh`, with absolute paths and an
  explicit port (default 9931 is never relied on).
- `data/raw/` is never edited by hand.
- Stock configs keep exactly the §3.1 settings in every stage.

## Measurement rules
- llama-server response `timings` are authoritative; no random-token (llama-bench) numbers for
  expert-cache or MTP results (llama-bench only as the labelled Stage 2e cross-check).
- Every measured run has an environment snapshot, a warm-up and telemetry.
- Report raw evidence, not adjectives. Flagged measurements are re-run once, then excluded.

## Privacy
Public data only. Scrub username, hostname and home paths before anything is published.

## Workflow
- Start as above; at the end of each WP, commit and append a progress-log entry
  (format: `docs/plans/step-0-baseline.md` §12.5).
- One WP per session. Commit message style: `WPn: <summary>`.
- Finish with the standard report (§12.4):
  1. Summary of what was done
  2. Each acceptance criterion PASS/FAIL with evidence
  3. Files changed (`git diff --stat <start>..HEAD`)
  4. Commands run, with verbatim key output
  5. Anything not done, uncertain, or deviating from the plan
  6. Suggested next steps
  7. Commit hash, and confirmation the progress-log entry was added

## Compaction
When compacting, keep the WP id, the acceptance criteria, the modified files and the commands run.
