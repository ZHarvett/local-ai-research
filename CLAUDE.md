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

<!-- workflow-kit:begin -->
## Workflow kit (planning-chat plan execution)

This repo runs a planning-chat plan task by task. The full protocol is in
`docs/WORKFLOW.md`; the short version:

- **Session start:** run `bash scripts/wf-guard.sh` (stop if it fails), then
  `bash scripts/wf.sh status`. Zack (or you, when he typed `/continue`) picks the
  next task from `bash scripts/wf.sh ready`. Never read `PLAN.md` whole: the card
  comes from `bash scripts/wf-card.sh T-xxx` and nothing else.
- **Session end:** the task's work is committed, `wf.sh done` has run, and one line
  says `TASK T-xxx DONE | review: … | next ready: …`.
- **State discipline:** `.workflow/` state, `PROGRESS.md` and `PLAN.md` are never
  hand-edited. State changes only through `scripts/wf-*.sh`. New cards go into
  `PLAN-ADDED.md` + `wf.sh add-task`.
- **Hard rules:** no sudo, nothing destructive, `data/` append-only, one GPU job
  at a time (machine-wide lock for gpu / exclusive-machine / cpu-heavy tasks),
  no downloads or publishing without a gate.
- **Decision rights:** every card says what you may decide and what you must
  escalate. Judgement calls and anything unexpected: stop, write an escalation
  brief (`wf-escalate.sh`), wait for the planning chat's decision
  (`wf-decision.sh` records it). Never work around a failure in the tooling you
  are using for measurements.
- **Gates:** tasks with a HUMAN-GATE stop, print exactly what Zack must do
  (`wf.sh gate-wait`), and wait for "go" (`wf.sh gate-release`).
- **Context discipline:** finish the current step, `wf.sh step-done T-xxx Sn`,
  and stop with "Start a fresh session and run /continue" when context grows
  past about 70%.
- Commands: `/continue`, `/lane N`, `/review`, `/address-review`, `/escalate`,
  `/status`, `/calibrate-reviewer`.
<!-- workflow-kit:end -->
