# Step 0, remaining work: Stage 4, release v0.1.0, completion report
*Version 1.0 · 13 November 2026*

## Shared rules

Context: Step 0 (baseline setup) of "Local AI on a Small PC". Reference plan: docs/plans/step-0-baseline.md (v1.8; v1.9 from T-011). Runbook: docs/runbook-stage3.md. Decisions: docs/decisions.md. The planning chat cannot see the repo, so every escalation brief must be self-contained.

1. Evidence, not memory. Every number written anywhere is copied from a named repo file. Docs carry a `<!-- sources: path, path -->` line for tools/check_doc_numbers.py (built in T-005), and derived numbers are marked `<!-- derived: how -->` on their line. Commands come from the runbook or from docs/recon/commands.env (written in T-001), never from memory.
2. Code is frozen until T-008 is accepted. No change to any existing file under src/, configs/ or scripts/, or to pyproject.toml or uv.lock. After T-008, only the cards that name such files may change them.
3. data/raw/ is append-only and never edited by hand. A superseded run is marked superseded, never deleted. A RE-MEASURE happens only after an approved escalation, as a new gated task.
4. Safety (the umbrella's rules win):
   - no sudo (propose the commands instead) and no --allow-dirty;
   - GPU work only through the runbook and the GPU lock;
   - anything over about 8 minutes runs detached via scripts/run-detached.sh;
   - no heavy command while a measurement session runs;
   - nothing written outside the repo except /tmp and /dev/shm/local-ai-research-*.
5. Nothing is pushed, tagged on a remote or made public outside T-015 and T-016.
6. Each task ends with a commit and a docs/progress-log.md entry (plan §12.5). The exceptions are the parallel-group tasks T-004, T-005, T-010 and T-011: they don't touch the progress log, and T-006 and T-012 append their entries.
7. Escalate instead of working around a surprise, a failed precondition or an assumption mismatch.
8. Carry these corrections into any text:
   - 1 flagged window of 80 (not 100) in the later Stage 2 sessions;
   - MTP helped about 2 to 5% per turn (not 3 to 5%), and costs 9 to 16% of prefill speed and 0.75 to 1.5 GiB of VRAM;
   - Stage 3 took about 2.1 hours (90 minutes of sessions plus 38 minutes of re-runs).

**Stage 3 decisions (planning chat, 12 November 2026)**

- D1 The 128K headline uses all units, with the label "includes paging-flagged stock windows" and the clean-units figures beside it; S4(d) is a recorded deviation for 128K. This is the declared §5.4 rule, not a judgement call. Until T-009 fixes the rendered report (which calls stock-128K "not reportable"), data/analysis/stage3/headline.md is authoritative.
- D2 The tuned-64K paging is the known file-page faulting of the MTP cell seen in Stage 2a; it is not investigated. Gate denominator per A7: [filled in by T-002 from docs/recon/T-001.md]. If stock windows were counted and the gate truly failed, it is accepted as a recorded deviation without re-measurement, because all four flagged units re-ran clean on fresh servers and the cause matches Stage 2a.
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
- R3 Stage 4 runs on 13 November 2026 or later. Since the Stage 3 session commit, the only changes under src/, configs/, scripts/, pyproject.toml and uv.lock are the kit's new scripts/wf-*.sh and scripts/_wf.py, and the only existing files changed by the kit install are CLAUDE.md and .gitignore. Check: `S3=$(cat docs/recon/stage3-commit.txt) && git cat-file -e "$S3^{commit}" && ! git diff --name-only "$S3" HEAD -- src configs scripts pyproject.toml uv.lock CLAUDE.md .gitignore | grep -vxE 'CLAUDE\.md|\.gitignore|scripts/wf-[A-Za-z0-9_.-]+\.sh|scripts/_wf\.py'`
- R4 An S2 failure is reported and escalated, never re-measured automatically.

## Assumption register

- A1: HEAD descends from f2f37df only through the kit-install commit and PLAN.md/workflow-state commits; src/, configs/, scripts/, data/, tests/ have no uncommitted changes; no llama-server is running; .locks/gpu.lock is free; /dev/shm/local-ai-research-* is empty — checked by T-001
- A2: the kit install changed exactly two existing files, CLAUDE.md and .gitignore, and added only files listed in .workflow-kit-manifest.json; nothing under src/ or configs/, and under scripts/ only wf-*.sh and _wf.py — checked by T-001
- A3: the Stage 4 sweep spec exists and renders stock-64K and tuned-64K with argument lists identical to Stage 3's; docs/runbook-stage3.md contains the Stage 4 commands — checked by T-001
- A4: `python -m smallpc.stage3 repro` evaluates T_turn_400, fresh prefill at 32K and decode at 32K depth, and has an all-units mode for stock; whether that mode also works for tuned (R1) is recorded — checked by T-001
- A5: the three Stage 3 sessions ran from one recorded commit — checked by T-001
- A6: the plan version is asserted only in tests/, not in src/, configs/ or scripts/ — checked by T-001
- A7: the composition of the 64K gate's 36.4% denominator (tuned and canary windows only, or also stock) — checked by T-001
- A8: which module renders "not reportable" for stock-128K, and why — checked by T-001
- A9: the scrub tool's exact invocation is known and accepts arbitrary paths — checked by T-001
- A10: gh is installed and the repo has no git remote — checked by T-001
- A11: the account name occurs only in the known WP0 commit(s) and nowhere in the current tree; whether data/raw records commit hashes is recorded — checked by T-001
- A12: README.md (stub) and CHANGELOG.md (with an Unreleased section) exist; the state of docs/methodology.md and docs/environment.md is recorded — checked by T-001
- A13: the flakiness of tests/test_sweep_probe.py can be fixed in tests/ without touching src/ — checked by T-001
- A14: .claude/settings.json allows every command the cards and docs/runbook-stage3.md need (uv run, bash scripts/*.sh, git including commit/tag/push, gh, nvidia-smi, systemd-inhibit, flock, setsid, nohup, pgrep, sha256sum, shellcheck, curl to localhost) and denies nothing the plan relies on — checked by T-001
- A15: whether .workflow/ and PROGRESS.md are tracked, and whether the sweep runner's clean-tree check would see workflow bookkeeping changes — checked by T-001
- A16: `wf accept` runs cmd items through bash (pipes, $(...), !, for loops and `source` work) — checked by T-001

## Phases

- P0: Pilot setup (13 Nov): T-001, T-002, T-003
- P1: Drafts, the first parallel pair: T-004 and T-005 in parallel, then T-006
- P2: Stage 4 (13 Nov or later, quiet machine): T-007, T-008
- P3: Post-Stage-4 code fixes: T-009
- P4: Release: T-010 and T-011 in parallel, then T-012 to T-016

## Task cards

### T-001 — Smoke test and recon (read-only)
id: T-001
title: Smoke test and recon (read-only)
phase: P0
depends_on: none
lane: 1
resources: cpu-heavy
files_read: PROGRESS.md, .workflow-kit-manifest.json, .claude/settings.json, CLAUDE.md, .gitignore, docs/runbook-stage3.md, docs/plans/step-0-baseline.md, docs/decisions.md, data/raw/, data/analysis/stage3/, reports/, src/smallpc/, configs/sweeps/, scripts/, tests/, .github/workflows/ci.yml, PLAN.md
files_write: docs/recon/T-001.md, docs/recon/stage3-commit.txt, docs/recon/commands.env
gates: none
review: none
preconditions:
  - cmd: test -f .workflow-kit-manifest.json
    expect: exit_code 0
  - cmd: test -z "$(git status --porcelain -- src configs scripts data tests)"
    expect: exit_code 0
  - cmd: ! pgrep -x llama-server
    expect: exit_code 0
steps:
  - S1: Smoke test. Record in docs/recon/T-001.md section 1 the output of `git rev-parse HEAD`, `git log --oneline -8` and the kit's status (as /status shows it), and confirm that this card was found and claimed through /continue. (redo-safe)
  - S2: Check A1 to A16 one by one, read-only, with evidence (command plus output excerpt, or file:line) for each. For A2, find the install commit with `git log --format=%H --grep='install workflow-kit' -1`. For A7, count the windows in the 64K gate's denominator by kind from the session data. For A11, never write the account name into any file; call it <account-name>. For A13, run the file's tests 20 times and classify each failure's cause. For A14, list every command the cards and docs/runbook-stage3.md use, then match each to its allow or deny rule in .claude/settings.json. For A16, read how _wf.py executes cmd items. (redo-safe)
  - S3: Write the Stage 3 session commit (A5), and nothing else, to docs/recon/stage3-commit.txt. (redo-safe)
  - S4: Write docs/recon/commands.env, a bash-sourceable file with these variables in single quotes, using $SESSION where a session id or path is needed: GATE_CMD, COVERAGE_CMD, REPRO_CMD and REPORT_CMD (taken from docs/runbook-stage3.md and each tool's --help), SCRUB_CMD (with data reports docs as paths), and CI_CMD (the CI workflow's commands chained with &&). Record the pass signature of GATE_CMD and REPRO_CMD next to each as a comment. (redo-safe)
  - S5: End docs/recon/T-001.md with a table of one row per assumption, formatted `| A<n> | PASS or FAIL or INFO | evidence |` (INFO only for A7), then a line `Result: all assumptions PASS` or `Result: FAIL <ids>`. Commit and append the progress-log entry. (redo-safe)
  - S6: If any assumption FAILs, escalate once (assumption-mismatch) listing every failure. After the DECISION, append `Resolved by decision E-NNN: <one line>` to docs/recon/T-001.md and commit. (not redo-safe)
acceptance:
  - expect: file_exists docs/recon/T-001.md
  - cmd: grep -cE '^\| A([1-9]|1[0-6]) \| (PASS|FAIL|INFO) \|' docs/recon/T-001.md
    expect: stdout_regex ^16$
  - cmd: S3=$(cat docs/recon/stage3-commit.txt) && git cat-file -e "$S3^{commit}" && echo ok
    expect: stdout_regex ^ok$
  - cmd: bash -n docs/recon/commands.env && source docs/recon/commands.env && for v in GATE_CMD COVERAGE_CMD REPRO_CMD REPORT_CMD SCRUB_CMD CI_CMD; do [ -n "${!v}" ] || exit 1; done
    expect: exit_code 0
  - cmd: S3=$(cat docs/recon/stage3-commit.txt) && git cat-file -e "$S3^{commit}" && ! git diff --name-only "$S3" HEAD -- src configs scripts pyproject.toml uv.lock CLAUDE.md .gitignore | grep -vxE 'CLAUDE\.md|\.gitignore|scripts/wf-[A-Za-z0-9_.-]+\.sh|scripts/_wf\.py'
    expect: exit_code 0
  - cmd: grep -qE '^Result: all assumptions PASS|^Resolved by decision E-[0-9]+' docs/recon/T-001.md
    expect: exit_code 0
  - cmd: test -z "$(git status --porcelain -- src configs scripts data reports tests)"
    expect: exit_code 0
evidence: docs/recon/T-001.md, docs/recon/stage3-commit.txt, docs/recon/commands.env
estimate: 60m
decision_rights:
  - may: how evidence is gathered and laid out beyond the required table; the A7 outcome, which feeds D2 without escalation
  - must_escalate: any FAIL; any need to change a file outside docs/recon/; Stage 3 sessions that ran from different commits

### T-002 — Record Stage 3 decisions and merge CLAUDE.md
id: T-002
title: Record Stage 3 decisions and merge CLAUDE.md
phase: P0
depends_on: T-001
lane: 1
resources: light
files_read: docs/recon/T-001.md, CLAUDE.md, docs/WORKFLOW.md, PLAN.md
files_write: docs/decisions.md, CLAUDE.md, docs/recon/claude-md-merge.diff, docs/progress-log.md
gates: none
review: none
preconditions:
  - cmd: grep -qE '^Result: all assumptions PASS|^Resolved by decision E-[0-9]+' docs/recon/T-001.md
    expect: exit_code 0
steps:
  - S1: Append to docs/decisions.md a section "2026-11-12: Step-lead decisions after Stage 3 (planning chat)". Copy the Shared rules blocks "Stage 3 decisions" and "Stage 4 rules" into it verbatim, one line per item starting "- D1 " to "- R4 ". The only change allowed is filling D2's bracket with A7's finding, in the form "<n> windows: <composition>; <true pass | true fail at x%>". Skip this step if the section already exists. (redo-safe)
  - S2: Write docs/recon/claude-md-merge.diff, a unified diff of CLAUDE.md that resolves every overlap between the umbrella text and the kit block. The kit wins on session flow (start with /continue, state in PROGRESS.md, one task per session). The umbrella wins on safety (no sudo, GPU lock, data/raw append-only, no --allow-dirty, long jobs detached) and on the standard report format (plan §12.4). docs/progress-log.md stays an append-only history that tasks append to. Keep the workflow-kit begin/end markers intact. (redo-safe)
  - S3: Commit S1 and the diff file, then escalate (judgement: "CLAUDE.md merge approval"). The brief must contain the full diff and, for each overlapping line, both the umbrella and the kit versions. Stop. (not redo-safe)
  - S4: After the DECISION is recorded, apply exactly the approved diff with `git apply`, including any edits the decision names. If the decision changed the diff, save the final applied diff over docs/recon/claude-md-merge.diff. Commit and append the progress-log entry. (not redo-safe)
acceptance:
  - cmd: for i in D1 D2 D3 D4 D5 D6 D7 D8 D9 R1 R2 R3 R4; do grep -q "^- $i " docs/decisions.md || exit 1; done
    expect: exit_code 0
  - cmd: ! grep -qF '[filled in by T-002' docs/decisions.md
    expect: exit_code 0
  - cmd: git apply --check -R docs/recon/claude-md-merge.diff
    expect: exit_code 0
  - cmd: grep -q 'workflow-kit:begin' CLAUDE.md && grep -q 'workflow-kit:end' CLAUDE.md && grep -qi 'sudo' CLAUDE.md && grep -qF -- '--allow-dirty' CLAUDE.md
    expect: exit_code 0
  - cmd: git diff --quiet HEAD -- CLAUDE.md docs/decisions.md
    expect: exit_code 0
evidence: docs/decisions.md, docs/recon/claude-md-merge.diff, CLAUDE.md
estimate: 40m
decision_rights:
  - may: wording of the merged CLAUDE.md lines; diff layout
  - must_escalate: the merge itself (always); any CLAUDE.md change beyond the approved diff; any wording change to D1–D9 or R1–R4 other than D2's bracket

### T-003 — Reviewer calibration
id: T-003
title: Reviewer calibration
phase: P0
depends_on: T-002
lane: 1
resources: light
files_read: .workflow/calibration.json
files_write: docs/recon/calibration-summary.md, docs/progress-log.md
gates: Open a second terminal in the repo, start a fresh Claude Code session and run /calibrate-reviewer. When it has written .workflow/calibration.json, close that session and reply go here.
review: none
preconditions:
  - cmd: test -d .claude
    expect: exit_code 0
steps:
  - S1: Read .workflow/calibration.json and write docs/recon/calibration-summary.md: what was tested, what the reviewer caught and missed, and the kit's own verdict on how far reviews can be trusted. (redo-safe)
  - S2: If the calibration marks the reviewer as unreliable for numbers, docs or code, escalate with the summary. The plan relies on post-review for T-005, T-008, T-010 and T-013, and on pre+post review for T-007. (not redo-safe)
  - S3: Commit and append the progress-log entry. (redo-safe)
acceptance:
  - expect: file_exists .workflow/calibration.json
  - cmd: python3 -c "import json; json.load(open('.workflow/calibration.json'))"
    expect: exit_code 0
  - expect: file_exists docs/recon/calibration-summary.md
evidence: docs/recon/calibration-summary.md
estimate: 30m
decision_rights:
  - may: summary wording
  - must_escalate: any calibration result the kit marks as failing or low-trust

### T-004 — README draft
id: T-004
title: README draft
phase: P1
depends_on: T-002, T-003
lane: 1
resources: light
files_read: docs/plans/step-0-baseline.md, docs/decisions.md, configs/server/, configs/model.toml, configs/harness.toml, configs/machine.toml, scripts/launch-server.sh, scripts/stop-server.sh, scripts/build-llama.sh, docs/runbook-stage3.md, data/analysis/stage3/headline.md, data/env/build-info.json, docs/recon/T-001.md
files_write: README.md
gates: none
review: none
preconditions:
  - expect: file_exists data/analysis/stage3/headline.md
steps:
  - S1: Write README.md to plan §9: what this is and the hardware it was measured on; quick start (prerequisites, build with scripts/build-llama.sh, download and verify, launch stock or tuned with scripts/launch-server.sh), with commands copied from the scripts' real usage; how to rerun the sweep on your own 12–16 GB machine via machine.toml; a results summary with CIs from headline.md, applying D1 and D3; limitations (the standardised 3,000 + 400 turn is not real agent use, Stages 1–2 ran with desktop apps open, the draft-length-2 repetition, host-memory paging); licences. Put a sources line at the top. Mark every Stage 4 or S2 spot with `<!-- TODO-T010 -->`. (redo-safe)
  - S2: Commit. No progress-log entry; T-006 appends it. (redo-safe)
acceptance:
  - cmd: for h in 'Quick start' 'Results' 'Limitations' 'Licen'; do grep -qiE "^#+ .*$h" README.md || exit 1; done
    expect: exit_code 0
  - cmd: grep -q 'TODO-T010' README.md && grep -q 'includes paging-flagged stock windows' README.md && grep -q '<!-- sources:' README.md
    expect: exit_code 0
evidence: README.md
estimate: 45m
decision_rights:
  - may: structure and wording within plan §9
  - must_escalate: any number not found in a repo file; any claim that would need a new measurement

### T-005 — Baseline report draft and number checker
id: T-005
title: Baseline report draft and number checker
phase: P1
depends_on: T-002, T-003
lane: 2
lane_reason: It writes different files from T-004, and both are about 45–75 minutes of light writing, so running them together saves about 40 minutes and is a harmless first test of lane locking.
resources: light
files_read: docs/plans/step-0-baseline.md, docs/decisions.md, docs/stage2-summary.md, reports/stage1/, reports/stage2/, reports/stage3/, data/analysis/stage3/, data/sanity/, data/health/, data/env/, configs/model.toml, configs/harness.toml
files_write: reports/baseline-report.md, tools/check_doc_numbers.py, tests/test_check_doc_numbers.py
gates: none
review: post
preconditions:
  - expect: file_exists data/analysis/stage3/headline.md
steps:
  - S1: Write tools/check_doc_numbers.py using only the standard library. It reads a doc's `<!-- sources: ... -->` line(s) and extracts every decimal number (digits with a decimal point, thousands separators allowed) outside fenced code. A number passes if it appears in a source file (with separators removed on both sides) or its line carries `<!-- derived: ... -->`. It prints each failing number with its line number and exits 1 if any fail. Add tests in tests/test_check_doc_numbers.py. (redo-safe)
  - S2: Write reports/baseline-report.md covering: a summary; setup and provenance (build tag and commit, model revision and SHA-256, harness versions); the method (pointer to plan §5); Stages 1 and 2, labelled as selection data measured with apps open; the Stage 3 headline per context, with the full per-depth table from headline.md, D1's label and clean figures at 128K, D3's sensitivity wording, the VRAM breakdown, hit rates with D9's caveat, the paging picture and the sanity results (D7's file name); flags and deviations from docs/decisions.md; an S1–S5 status table with S2 and S5 as `<!-- TODO-T010 -->`. (redo-safe)
  - S3: Run the number check, the new test and ruff on the new files, then commit. No progress-log entry; T-006 appends it. (redo-safe)
acceptance:
  - cmd: uv run python tools/check_doc_numbers.py reports/baseline-report.md
    expect: exit_code 0
  - cmd: uv run pytest -q tests/test_check_doc_numbers.py
    expect: exit_code 0
  - cmd: uv run ruff check tools/check_doc_numbers.py tests/test_check_doc_numbers.py && uv run ruff format --check tools/check_doc_numbers.py tests/test_check_doc_numbers.py
    expect: exit_code 0
  - cmd: grep -q 'includes paging-flagged stock windows' reports/baseline-report.md && grep -q 'stage3-tuned.json' reports/baseline-report.md && ! grep -q 'not reportable' reports/baseline-report.md
    expect: exit_code 0
  - expect: manual "Every table traces to a named file; selection data and headline results are labelled correctly; D1, D3, D7 and D9 are applied; nothing is claimed beyond the data."
evidence: reports/baseline-report.md, tools/check_doc_numbers.py
estimate: 75m
decision_rights:
  - may: report structure; which existing figures under reports/ to include; the checker's internals within S1
  - must_escalate: any number that cannot be traced; any disagreement between headline.md and other Stage 3 outputs; any change to src/, configs/ or scripts/

### T-006 — Write-up draft
id: T-006
title: Write-up draft
phase: P1
depends_on: T-004, T-005
lane: 1
resources: light
files_read: reports/baseline-report.md, docs/decisions.md, docs/plans/step-0-baseline.md, data/analysis/stage3/headline.md
files_write: reports/writeup.md, docs/progress-log.md
gates: none
review: none
preconditions:
  - expect: file_exists reports/baseline-report.md
steps:
  - S1: Draft reports/writeup.md, "What a 16 GB GPU actually does with a 35B MoE model" (GitHub only), covering: the problem and the approach; the results, taken from baseline-report.md; what didn't work (draft length 2, --fit against P6, host prompt cache paging, and why 2c was skipped); limitations. Keep it to at most about 1,500 words, with a sources line and a `<!-- TODO-T010 -->` placeholder for Stage 4. (redo-safe)
  - S2: Run the number check, append progress-log entries for T-004, T-005 and T-006, and commit. (redo-safe)
acceptance:
  - cmd: uv run python tools/check_doc_numbers.py reports/writeup.md
    expect: exit_code 0
  - cmd: test "$(wc -w < reports/writeup.md)" -le 1800 && grep -q 'TODO-T010' reports/writeup.md
    expect: exit_code 0
  - cmd: for t in T-004 T-005 T-006; do grep -q "$t" docs/progress-log.md || exit 1; done
    expect: exit_code 0
evidence: reports/writeup.md
estimate: 45m
decision_rights:
  - may: tone, structure and the choice of figures
  - must_escalate: any result not in baseline-report.md or a data file

### T-007 — Stage 4 session
id: T-007
title: Stage 4 session
phase: P2
depends_on: T-002, T-003
lane: 1
resources: exclusive-machine
files_read: docs/runbook-stage3.md, docs/recon/T-001.md, docs/recon/commands.env, docs/recon/stage3-commit.txt, configs/sweeps/, configs/server/stock-64k.toml, configs/server/tuned-64k.toml
files_write: data/raw/, docs/stage3-conditions.md, docs/stage4-conditions.md, docs/recon/stage4-session.txt, docs/decisions.md, docs/progress-log.md
gates: Stage 4, the headline reproducibility run (about 45 minutes). It must be 13 November or later. Close every app except one terminal running Claude Code (scripts/check-quiet.sh must exit 0), keep the PC on mains power, and don't use it until this session says it has finished; following along on your phone is fine. Reply go.
review: pre+post
preconditions:
  - cmd: [ "$(date +%Y%m%d)" -ge 20261113 ]
    expect: exit_code 0
  - cmd: S3=$(cat docs/recon/stage3-commit.txt) && git cat-file -e "$S3^{commit}" && ! git diff --name-only "$S3" HEAD -- src configs scripts pyproject.toml uv.lock CLAUDE.md .gitignore | grep -vxE 'CLAUDE\.md|\.gitignore|scripts/wf-[A-Za-z0-9_.-]+\.sh|scripts/_wf\.py'
    expect: exit_code 0
  - cmd: test -z "$(git status --porcelain -- src configs scripts data tests pyproject.toml uv.lock)"
    expect: exit_code 0
  - cmd: ! pgrep -x llama-server
    expect: exit_code 0
steps:
  - S1: Run scripts/check-quiet.sh (it must exit 0). Commit any workflow bookkeeping so that the whole tree is clean, as A15 found necessary. Then, with no state-changing wf command in between, start the Stage 4 session exactly as the runbook's Stage 4 section says (detached, from the clean committed tree). Write the session id to docs/recon/stage4-session.txt. (not redo-safe)
  - S2: Poll as the runbook says (sleep 420 plus scripts/sweep-status.sh plus a light CPU sample), apply its stop rules, and keep the conditions log the runbook names. (redo-safe)
  - S3: Run GATE_CMD. If it fails, apply R2 or escalate. (redo-safe)
  - S4: Run one --rerun-flagged pass as the runbook says, then the gate again. (not redo-safe)
  - S5: Commit the data and the conditions log, append the progress-log entry, and confirm that no server is running and the GPU lock is free. (redo-safe)
acceptance:
  - cmd: test -s docs/recon/stage4-session.txt
    expect: exit_code 0
  - cmd: source docs/recon/commands.env && SESSION="$(cat docs/recon/stage4-session.txt)" && eval "$COVERAGE_CMD"
    expect: exit_code 0
  - cmd: { source docs/recon/commands.env && SESSION="$(cat docs/recon/stage4-session.txt)" && eval "$GATE_CMD"; } | grep -qw PASS || grep -q '^- R2 applied: Stage 4' docs/decisions.md
    expect: exit_code 0
  - cmd: test -z "$(git status --porcelain -- data)" && ! pgrep -x llama-server
    expect: exit_code 0
  - expect: manual "The session started from a clean committed tree at a commit that passes R3; the runbook was followed; the quiet check passed at the start and at every poll; the re-run pass was done; the conditions log is complete."
evidence: docs/recon/stage4-session.txt, docs/stage4-conditions.md
estimate: 75m
decision_rights:
  - may: commit messages; the polling cadence within the runbook
  - must_escalate: any stop rule firing; a gate failure not covered by R2; a quiet-condition violation; any failed precondition; anything that would need --allow-dirty or a code change

### T-008 — S2 check and Stage 4 analysis
id: T-008
title: S2 check and Stage 4 analysis
phase: P2
depends_on: T-007
lane: 1
resources: light
files_read: docs/recon/commands.env, docs/recon/stage4-session.txt, data/raw/, data/analysis/stage3/, docs/decisions.md
files_write: data/analysis/stage4/, reports/stage4/, docs/decisions.md, docs/progress-log.md
gates: none
review: post
preconditions:
  - cmd: test -s docs/recon/stage4-session.txt
    expect: exit_code 0
steps:
  - S1: Run REPRO_CMD, saving its full output to data/analysis/stage4/repro-output.txt, and apply R1 to tuned-64K. Write data/analysis/stage4/s2-summary.md with a sources line: for stock and tuned, and for each of T_turn_400, fresh prefill at 32K and decode at 32K depth, give the Stage 3 value with its CI, the Stage 4 value, whether it falls within the CI or ±5% (whichever is wider), the unit set used (clean or all) and PASS or FAIL. Also write data/analysis/stage4/s2-summary.json with the key "overall" set to "PASS" or "FAIL" and one key per row. (redo-safe)
  - S2: Render the Stage 4 report with REPORT_CMD into reports/stage4/. (redo-safe)
  - S3: If any row FAILs, escalate under R4 and stop. (not redo-safe)
  - S4: Record any R1 deviation in docs/decisions.md, append the progress-log entry and commit. (redo-safe)
acceptance:
  - cmd: source docs/recon/commands.env && SESSION="$(cat docs/recon/stage4-session.txt)" && eval "$REPRO_CMD"
    expect: exit_code 0
  - expect: json_eq data/analysis/stage4/s2-summary.json overall PASS
  - cmd: uv run python tools/check_doc_numbers.py data/analysis/stage4/s2-summary.md
    expect: exit_code 0
  - expect: manual "The S2 rows match repro-output.txt, and R1 is applied only if tuned-64K had fewer than 5 clean units."
evidence: data/analysis/stage4/repro-output.txt, data/analysis/stage4/s2-summary.md, data/analysis/stage4/s2-summary.json
estimate: 40m
decision_rights:
  - may: the summary layout
  - must_escalate: any S2 FAIL (R4); any discrepancy between the repro output and the summary; any need to change analysis code

### T-009 — Post-Stage-4 code fixes
id: T-009
title: Post-Stage-4 code fixes
phase: P3
depends_on: T-008
lane: 1
resources: cpu-heavy
files_read: docs/recon/T-001.md, docs/recon/commands.env, tests/, src/smallpc/, data/analysis/stage3/headline.md, data/analysis/stage4/
files_write: tests/, src/smallpc/, reports/stage3/, reports/stage4/, docs/recon/T-009-start.txt, docs/progress-log.md
gates: none
review: none
preconditions:
  - expect: json_eq data/analysis/stage4/s2-summary.json overall PASS
steps:
  - S1: Write `git rev-parse HEAD` to docs/recon/T-009-start.txt and commit. (redo-safe)
  - S2: Fix the flakiness of tests/test_sweep_probe.py according to A13's diagnosis, changing tests/ only. (redo-safe)
  - S3: Make the tests read the plan version from the header of docs/plans/step-0-baseline.md instead of a literal. (redo-safe)
  - S4: In the report-rendering module that A8 identified, make the rendered report apply the §5.4 headline rule: clean units if both cells have at least 5 clean paired units, otherwise all units with the label "includes paging-flagged stock windows" and the clean figures beside it, consistent with headline.md. Add a test for the 4-of-5 stock case. Fix the figures: the prefill and decode y-axes start at 0, and the predicted_n labels sit clear of the whiskers. (redo-safe)
  - S5: Re-render reports/stage3/ and reports/stage4/ with REPORT_CMD. Only the rendering may change, not any number. (redo-safe)
  - S6: Run CI_CMD 5 times, commit, and append the progress-log entry. (redo-safe)
acceptance:
  - cmd: source docs/recon/commands.env && for i in 1 2 3 4 5; do eval "$CI_CMD" || exit 1; done
    expect: exit_code 0
  - cmd: grep -rq 'includes paging-flagged stock windows' reports/stage3 && ! grep -rq 'not reportable' reports/stage3
    expect: exit_code 0
  - cmd: ! git diff --name-only "$(cat docs/recon/T-009-start.txt)" HEAD -- data src configs scripts | grep -vE '^src/smallpc/report(\.py|/)'
    expect: exit_code 0
  - cmd: ! grep -rnE 'version.{0,20}"1\.[0-9]"' tests/
    expect: exit_code 0
evidence: reports/stage3/, reports/stage4/
estimate: 90m
decision_rights:
  - may: implementation details in tests/ and in the report-rendering module
  - must_escalate: any change to measurement, statistics or headline code; any change under data/; a re-rendered number that differs from headline.md or the repro output; a flakiness cause found in src/

### T-010 — Final README, report, write-up and changelog
id: T-010
title: Final README, report, write-up and changelog
phase: P4
depends_on: T-004, T-005, T-006, T-009
lane: 1
resources: light
files_read: data/analysis/stage4/, reports/stage3/, reports/stage4/, docs/decisions.md, docs/plans/step-0-baseline.md
files_write: README.md, reports/baseline-report.md, reports/writeup.md, CHANGELOG.md
gates: none
review: post
preconditions:
  - expect: json_eq data/analysis/stage4/s2-summary.json overall PASS
steps:
  - S1: Replace every TODO-T010 with Stage 4 and S2 results from data/analysis/stage4/. Complete the S1–S5 table in the report, marking S5's open items as "pending T-015/T-016". Make sure the README covers every plan §9 item. Add sources to each doc's sources line. (redo-safe)
  - S2: Add a CHANGELOG.md entry for v0.1.0 covering the configs, the launch script, the sweep and analysis tools, the data, the reports and provenance. (redo-safe)
  - S3: Run the number checks and commit. No progress-log entry; T-012 appends it. (redo-safe)
acceptance:
  - cmd: ! grep -rq 'TODO-T010' README.md reports/baseline-report.md reports/writeup.md
    expect: exit_code 0
  - cmd: for f in README.md reports/baseline-report.md reports/writeup.md; do uv run python tools/check_doc_numbers.py "$f" || exit 1; done
    expect: exit_code 0
  - cmd: grep -qE '^#+ .*0\.1\.0' CHANGELOG.md
    expect: exit_code 0
  - expect: manual "The README covers every plan §9 item; all three docs apply D1–D9 and R1–R4 correctly; S2 is stated as measured; nothing is claimed beyond the data."
evidence: README.md, reports/baseline-report.md, reports/writeup.md, CHANGELOG.md
estimate: 60m
decision_rights:
  - may: wording and structure
  - must_escalate: any number that cannot be traced; any change to a conclusion drawn in the T-005 draft

### T-011 — Plan v1.9, upstream drafts, methodology
id: T-011
title: Plan v1.9, upstream drafts, methodology
phase: P4
depends_on: T-008, T-009
lane: 2
lane_reason: It writes only the plan, docs/upstream/, docs/methodology.md and docs/environment.md, none of which T-010 writes; both tasks are about an hour of light writing, so running them in parallel saves about 40 minutes.
resources: light
files_read: docs/plans/step-0-baseline.md, docs/recon/T-001.md, data/sanity/, data/health/, data/env/, configs/
files_write: docs/plans/step-0-baseline.md, docs/upstream/, docs/methodology.md, docs/environment.md
gates: none
review: none
preconditions:
  - cmd: grep -q '^\*Version 1\.8 · 12 November 2026\*' docs/plans/step-0-baseline.md
    expect: exit_code 0
steps:
  - S1: Plan edit (a) to docs/plans/step-0-baseline.md: Replace the line `*Version 1.8 · 12 November 2026*` with `*Version 1.9 · <today's date, e.g. 20 November 2026>*`. (redo-safe)
  - S2: Plan edit (b) to docs/plans/step-0-baseline.md: Directly above the line starting `**Stage 4: Reproducibility**`, insert: `**Stage 3 outcome (12 November, quiet machine).** The three sessions took about 2.1 hours (90 minutes of sessions plus 38 minutes of re-run passes). No stop condition applied. The headline results are in reports/baseline-report.md, and the step-lead decisions on them (D1–D9) are in docs/decisions.md.` (redo-safe)
  - S3: Plan edit (c) to docs/plans/step-0-baseline.md: Directly after the Stage 4 paragraph, insert `Rules declared on 12 November 2026, before any Stage 4 data:` followed by R1 to R4 copied verbatim from PLAN.md's Shared rules (redo-safe)
  - S4: Plan edit (d) to docs/plans/step-0-baseline.md: Directly after the heading `## 12. Working protocol with Claude Code`, insert: `*§12.1–12.3 are superseded from 12 November 2026: execution follows PLAN.md through the workflow kit (docs/WORKFLOW.md), and the merged CLAUDE.md is the session guide. The standard report (§12.4) and the progress-log format (§12.5) still apply.*` (redo-safe)
  - S5: Plan edit (e) to docs/plans/step-0-baseline.md: At the end of §13, append two bullets. First: `**Stock pages at 32K too.** In Stage 3, one stock-32K repetition had 12,456 major faults and 6,321 MiB of swap growth with the default --cache-ram of 8192, so host-memory pressure is not limited to 64K and 128K.` Second: `**Idle desktop apps cost about 1%.** Stage 3 means on a quiet machine were 0.7 to 1.3% faster than the Stage 1 and 2 selection figures for the same configurations.` (redo-safe)
  - S6: Plan edit (f) to docs/plans/step-0-baseline.md: Directly above the §14 row starting `| 1.8 |`, insert: `| 1.9 | <same date as (a)> | After Stages 3 and 4 and the workflow-kit pilot: Stage 3 outcome and measured time, and the Stage 4 rules R1–R4 declared before its data (§5.4); §12.1–12.3 superseded by the workflow kit (§12); two notes for the executive chat (§13) |` (redo-safe)
  - S7: In docs/upstream/, write issue drafts with evidence paths and reproduction commands, not to be filed: (1) llama.cpp: MTP draft length 2 gives a deterministic repeated phrase on one of three sanity prompts on four configurations, possibly a threshold artifact; (2) a comment draft for llama.cpp #28619: the MTP draft state survived slot save/restore and the host prompt cache on b12208 up to 8,192 tokens, with no negative control. (redo-safe)
  - S8: Create docs/methodology.md (plan §5 in prose for readers) and update docs/environment.md, if A12 found them missing or outdated. Write no username, hostname or home path. (redo-safe)
  - S9: Check that steps S1–S6 made no other change to the plan (`git diff` of the plan shows only edits (a)–(f)), then commit. No progress-log entry; T-012 appends it. (redo-safe)
acceptance:
  - cmd: grep -q '^\*Version 1\.9 · ' docs/plans/step-0-baseline.md && grep -qE '^\| 1\.9 \|' docs/plans/step-0-baseline.md
    expect: exit_code 0
  - cmd: grep -qF 'Stage 3 outcome (12 November, quiet machine)' docs/plans/step-0-baseline.md && grep -qF 'Rules declared on 12 November 2026' docs/plans/step-0-baseline.md && grep -qF '§12.1–12.3 are superseded' docs/plans/step-0-baseline.md && grep -qF 'Stock pages at 32K too' docs/plans/step-0-baseline.md
    expect: exit_code 0
  - cmd: test "$(ls docs/upstream/*.md | wc -l)" -ge 2
    expect: exit_code 0
  - expect: file_exists docs/methodology.md
  - expect: file_exists docs/environment.md
  - cmd: source docs/recon/commands.env && eval "$CI_CMD"
    expect: exit_code 0
evidence: docs/plans/step-0-baseline.md, docs/upstream/
estimate: 60m
decision_rights:
  - may: wording of the issue drafts and methodology.md
  - must_escalate: any plan edit beyond (a)–(f) of steps S1–S6; a test failure after the version bump; any version check found outside tests/

### T-012 — README walkthrough from a clean shell
id: T-012
title: README walkthrough from a clean shell
phase: P4
depends_on: T-010, T-011
lane: 1
resources: gpu
files_read: README.md, configs/server/
files_write: data/health/readme-walkthrough.log, docs/progress-log.md
gates: The GPU is needed for about 15 minutes. Make sure no game or other GPU job is running; the machine doesn't need to be quiet. Reply go.
review: none
preconditions:
  - cmd: ! pgrep -x llama-server
    expect: exit_code 0
steps:
  - S1: For each of the six configs (stock and tuned at 32K, 64K and 128K), run exactly the README's launch commands in a clean shell (`env -i HOME="$HOME" TERM="$TERM" bash -l`). Wait for /health, check that /props reports the expected context size, and stop the server with the README's stop command. Log everything with timestamps to data/health/readme-walkthrough.log, with one line per config: `RESULT <config> PASS` or `RESULT <config> FAIL`. (redo-safe)
  - S2: Append progress-log entries for T-010, T-011 and T-012, and commit. (redo-safe)
acceptance:
  - cmd: grep -cE '^RESULT [^ ]+ PASS$' data/health/readme-walkthrough.log
    expect: stdout_regex ^6$
  - cmd: ! pgrep -x llama-server
    expect: exit_code 0
  - cmd: for t in T-010 T-011 T-012; do grep -q "$t" docs/progress-log.md || exit 1; done
    expect: exit_code 0
evidence: data/health/readme-walkthrough.log
estimate: 30m
decision_rights:
  - may: how the README commands are extracted and logged
  - must_escalate: any README command that needed changing to work (FIX-DOC); any config that fails to launch

### T-013 — Scrub and release checks
id: T-013
title: Scrub and release checks
phase: P4
depends_on: T-010, T-011, T-012
lane: 1
resources: light
files_read: docs/recon/T-001.md, docs/recon/commands.env, src/smallpc/, data/, reports/, docs/
files_write: scripts/release-check.sh, docs/recon/scrub-report.md, docs/progress-log.md
gates: none
review: post
preconditions:
  - cmd: test -z "$(git status --porcelain -- data reports docs)"
    expect: exit_code 0
steps:
  - S1: Write scripts/release-check.sh: read-only, bash, shellcheck-clean. It exits 0 only if all of these pass: (a) SCRUB_CMD over data, reports, docs, configs, README.md, CHANGELOG.md and CLAUDE.md finds nothing; (b) a scan of every commit and every path in the history (e.g. `git log -p --all` with the scrub module's patterns) finds nothing beyond the known WP0 occurrence of the account name, which is allowlisted by commit and path, never by the string itself (D8); (c) tools/check_doc_numbers.py passes on README.md, reports/baseline-report.md and reports/writeup.md; (d) there are no TODO-T010 placeholders; (e) LICENSE and LICENSE-DATA.md exist. (redo-safe)
  - S2: Run it and write docs/recon/scrub-report.md with counts and locations only, never the matched values. (redo-safe)
  - S3: If anything is found beyond the known occurrence, escalate and stop. (not redo-safe)
  - S4: Commit and append the progress-log entry. (redo-safe)
acceptance:
  - cmd: bash scripts/release-check.sh
    expect: exit_code 0
  - cmd: shellcheck scripts/release-check.sh
    expect: exit_code 0
  - expect: file_exists docs/recon/scrub-report.md
  - expect: manual "The history scan covers every commit and every path; the allowlist names only the known WP0 occurrence, by commit and path; the report contains no matched values."
evidence: docs/recon/scrub-report.md, scripts/release-check.sh
estimate: 60m
decision_rights:
  - may: the script's structure and its output format
  - must_escalate: any finding beyond the known occurrence; any need to edit committed data to remove a finding

### T-014 — Completion report and planning-chat review
id: T-014
title: Completion report and planning-chat review
phase: P4
depends_on: T-012, T-013
lane: 1
resources: light
files_read: reports/baseline-report.md, reports/writeup.md, data/analysis/stage4/, docs/decisions.md, docs/plans/step-0-baseline.md, docs/progress-log.md
files_write: docs/step-0-completion-report.md, reports/writeup.md, docs/progress-log.md
gates: none
review: none
preconditions:
  - cmd: bash scripts/release-check.sh
    expect: exit_code 0
steps:
  - S1: Upstream re-check, read-only: compare the newest llama.cpp release with the pinned b12208; record the status of #28619, #30594, #30664, #23262, #26448, #20697 and #22384; compare the newest dsh and OpenCode versions with the pinned ones. Give each a date. (redo-safe)
  - S2: Draft docs/step-0-completion-report.md for the executive chat, at most about 4 pages, with a sources line, covering: what was built; results with numbers; deviations (from docs/decisions.md); open issues; notes for the executive chat (plan §13); suggested project-plan changes; the §9 checklist with evidence, with T-015 and T-016 items marked pending; the upstream re-check. (redo-safe)
  - S3: Run the number check and commit. Escalate (judgement: "planning-chat review of the completion report and write-up") with a brief that lists the two files for Zack to upload, the checks that were run and anything uncertain. Stop. (not redo-safe)
  - S4: After the DECISION, apply exactly the edits it lists, run release-check.sh again, append a progress-log entry naming the decision (E-NNN), and commit. (not redo-safe)
acceptance:
  - cmd: uv run python tools/check_doc_numbers.py docs/step-0-completion-report.md
    expect: exit_code 0
  - cmd: bash scripts/release-check.sh
    expect: exit_code 0
  - cmd: grep -qE 'T-014.*E-[0-9]+' docs/progress-log.md
    expect: exit_code 0
evidence: docs/step-0-completion-report.md
estimate: 60m
decision_rights:
  - may: report structure; the upstream re-check method
  - must_escalate: the review itself (always); any edit beyond those the decision lists

### T-015 — Private repo, CI and tag v0.1.0
id: T-015
title: Private repo, CI and tag v0.1.0
phase: P4
depends_on: T-014
lane: 1
resources: light
files_read: CHANGELOG.md, reports/baseline-report.md, docs/recon/commands.env
files_write: reports/release-notes-v0.1.0.md, docs/progress-log.md
gates: Run `gh auth status`; if it is not logged in, run `gh auth login` (GitHub.com, HTTPS, log in with a browser). Your go also confirms that Claude Code may create the PRIVATE repo ZHarvett/local-ai-research, push main, and push tag v0.1.0.
review: none
preconditions:
  - cmd: gh auth status
    expect: exit_code 0
  - cmd: test -z "$(git rev-list --objects --all | git cat-file --batch-check='%(objectsize) %(rest)' | awk '$1 > 95000000')"
    expect: exit_code 0
  - cmd: bash scripts/release-check.sh
    expect: exit_code 0
steps:
  - S1: Write reports/release-notes-v0.1.0.md from the CHANGELOG entry and the report summary, with a sources line, run the number check and CI_CMD, and commit. (redo-safe)
  - S2: Run `gh repo create ZHarvett/local-ai-research --private --source . --remote origin`, then push main. If the repo already exists, check that it is private and escalate if it isn't. (not redo-safe)
  - S3: Wait for the CI run on the pushed HEAD to finish, without pushing any fixes. If it is red, escalate. (redo-safe)
  - S4: Create the annotated tag v0.1.0 on that HEAD and push the tag. (not redo-safe)
  - S5: Append the progress-log entry with the CI run URL, commit and push main. (redo-safe)
acceptance:
  - cmd: gh repo view ZHarvett/local-ai-research --json visibility -q .visibility
    expect: stdout_regex ^PRIVATE$
  - cmd: test "$(git rev-parse 'v0.1.0^{commit}')" = "$(git ls-remote origin 'refs/tags/v0.1.0^{}' | cut -f1)"
    expect: exit_code 0
  - cmd: gh run list --repo ZHarvett/local-ai-research --commit "$(git rev-parse 'v0.1.0^{commit}')" --json conclusion -q '.[0].conclusion'
    expect: stdout_regex ^success$
  - cmd: uv run python tools/check_doc_numbers.py reports/release-notes-v0.1.0.md
    expect: exit_code 0
evidence: reports/release-notes-v0.1.0.md
estimate: 45m
decision_rights:
  - may: release-notes wording; commit messages
  - must_escalate: red CI; any push error; a repo that exists and is public; any push to another remote; any force push

### T-016 — Publish v0.1.0
id: T-016
title: Publish v0.1.0
phase: P4
depends_on: T-015
lane: 1
resources: light
files_read: reports/release-notes-v0.1.0.md
files_write: docs/progress-log.md, docs/step-0-completion-report.md
gates: Publish. Run `gh repo edit ZHarvett/local-ai-research --visibility public --accept-visibility-change-consequences` and `gh release create v0.1.0 --repo ZHarvett/local-ai-research --title "v0.1.0: Step 0 baseline" --notes-file reports/release-notes-v0.1.0.md` (or do both on github.com). File the drafts in docs/upstream/ now if you want to. Then reply go.
review: none
preconditions:
  - cmd: git ls-remote origin 'refs/tags/v0.1.0'
    expect: stdout_regex v0\.1\.0
steps:
  - S1: Check that the repo is public and the release exists. In the completion report, mark the §9 items for T-015 and T-016 done, with evidence. (redo-safe)
  - S2: Append a progress-log entry "Step 0 complete" with S1–S5 status, commit and push main. (redo-safe)
acceptance:
  - cmd: gh repo view ZHarvett/local-ai-research --json visibility -q .visibility
    expect: stdout_regex ^PUBLIC$
  - cmd: gh release view v0.1.0 --repo ZHarvett/local-ai-research --json tagName -q .tagName
    expect: stdout_regex ^v0\.1\.0$
  - cmd: grep -q 'Step 0 complete' docs/progress-log.md && test -z "$(git status --porcelain -- docs)"
    expect: exit_code 0
evidence: docs/step-0-completion-report.md
estimate: 15m
decision_rights:
  - may: commit messages
  - must_escalate: a release or visibility that doesn't match the gate
