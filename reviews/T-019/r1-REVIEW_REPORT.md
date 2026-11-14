# Review T-019 (cycle 1)

## Model

qwen4-max-preview (the config records a single model for executor and reviewer).

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-019` myself (run 2, 0 failures, evidence hash
`bd457801407d…` matches the file on disk, 26,267 bytes, unchanged since the acceptance
commit `5cd7807`). No heavy items: the task is light, no GPU job was in progress
(`pgrep -x llama-server` empty, GPU lock probe free), nothing DEFERRED.

| item | verdict | note |
|---|---|---|
| A1 | PASS | kit re-run: `grep -cE '^\| P[1-8] \| (PASS\|FAIL) \|'` → `8`; I also read all eight rows (§2 table, lines 77–84). |
| A2 | PASS | kit re-run: `Result: all checks PASS` present (line 345). |
| A3 | PASS | kit re-run and my own `pgrep -x llama-server`: empty. No `data/raw/stage4*`, no job dir created in the task window (newest `data/logs/jobs/` entry predates T-019). |
| A4 | PASS (judgement) | Re-derived independently, below. Every P-row carries re-runnable evidence; P2 covers BOTH cells (and the canary); no server/GPU use is supported by the command classes and the artifact checks. One descriptive number is wrong (F-1) but no acceptance claim is affected. |

### What I re-derived myself (not copied from the executor's record)

- **P1**: all seven named scripts executable; `_common.sh` correctly not executable;
  `.locks/gpu.lock` exists, 0 bytes, `flock -n` probe free.
- **P2 (independent re-render)**: wrote my own script (`/tmp/t019-review/verify_p2.py`,
  scratch, read-only) using the runner's own path (`load_sweep` → `spec.expand` →
  `ServerConfig.model_validate` → `render_argv`, `config_hash`, `render_toml` — verified
  against `session.py:315-327`, `core.py:125-127`, `provenance.py:69-73`, `spec.py:117-160`).
  Results, all matching the doc's table exactly:
  - stock-64K: argv byte-equal to record, argv sha256 `ab87c02d…e04b7f`, config_hash
    `22dc1178c8d9b555`, resolved TOML byte-equal, sha256 `a4272770…d42bbd`, **12 argv items**,
    no `--cache-ram` (llama.cpp default).
  - tuned-64K: argv byte-equal, argv sha256 `4775ccde…86ef31`, config_hash
    `f9b81a840bab20cf`, resolved TOML byte-equal, sha256 `735f0aeb…093ffb`, **33 argv items**
    (the doc says 28 — F-1).
  - canary (extra, beyond the card): rendered through `canary_job`'s inline-cell path, argv
    byte-equal to `canary-start-debea778.json`, config_hash `debea7788d296087`.
  - current `configs/model.toml` declared sha256 `42739874…` and `data/env/build-info.json`
    commit `57d04820…` equal the recorded values in both cells.
  - `smallpc.render` CLI cross-check on both recorded resolved TOMLs: printed string ==
    `shlex.join(recorded argv)` → True for both.
  - `diff configs/sweeps/stage3.toml configs/sweeps/stage4.toml`: differs only in header,
    `name`, `expect_cells` (6 vs 2), the four non-64K cell blocks and one comment above
    `[canary]` — exactly as claimed; 64K blocks, defaults, stock_defaults, canary identical.
  - `sweep check configs/sweeps/stage4.toml` exit 0; JSON: cells 2, cells_in_spec 2,
    stock 1 / tuned 1, both 64K, repetitions 5, canary true.
- **P3**: `sweep run --help` lists `--resume`, `--rerun-flagged`, `--only`; wrapper usage
  lists the same; forwarding verified at `run-sweep.sh:86-90`.
- **P4**: `data/raw/stage4` absent; `run-sweep.sh:77` refusal confirmed.
- **P5**: `du -sb` reproduces 647,211 / 746,917 / 775,006 B exactly; 2 × 775,006 = 1,550,012;
  free space now 152,697,430,016 B (recorded 152,697,622,528 B — normal drift, still PASS by
  ~5 orders of magnitude).
- **P6**: `bash -n` exit 0; sourcing sets `SESSION=stage4` + the six named variables;
  uv, shellcheck, ruff 0.17.4, pytest 9.2.0 exist; module subcommand lists match
  (`{headline,gate,repro}`, `{coverage}`, `{render,coverage,repro}`, scrub `[--check] paths`).
- **P7**: R3 check run verbatim → exit 0; filtered diff is exactly the 12 claimed kit paths;
  `stage3-commit.txt` = `80964618…`; `date -u +%F` = 2026-11-13.
- **P8**: tree fully clean now (`git status --porcelain` empty); sweep dirty check empty;
  `.workflow/state.json` and `PROGRESS.md` tracked; the exemption is on record (T-001 A15,
  `run-sweep.sh:55-61` checks only `src configs scripts`). Historical claims verified:
  `bc8e0c3` (17:50:11Z) carries the loop-design/loop-states edits; `1ba3bf9` (17:52:46Z);
  `ca1d5ad` (17:57:03Z) touches ONLY the pre-flight doc + state.json + PROGRESS.md — no
  other lane's file was committed by T-019.
- **S1 vs runbook**: every command, pass signature and stop rule in §1.1–1.4 checked against
  `docs/runbook-stage3.md` §1–§7 and the code: gate a–f (`gate.py:26-27,90-131`: 40%,
  1,024 MiB, tuned+canaries only, stock never fails), gate exit 0 (`cli.py:50`), repro exit 0
  (`cli.py:60`), REPRO_METRICS and CI-or-5%-whichever-wider (`report.py:1072-1103`),
  MIN_CLEAN_PAIRED=5 and the ALL-units first line (`repro.py:16-38,43-48`), durations
  804+403+370=1,577 s / 26 / 29 / 44 min (runbook line 156), exit 75 / fd 9 / fd 8 probe /
  job-dir naming (`run-detached.sh:37-42`, `with-gpu-lock.sh:22-25`, `_common.sh:7`),
  server lifecycle (`server.py:1-2`), stage1 §5 stop rules (20 min, `kill -INT`, no `kill -9`
  first). All match.
- **Number checker**: `tools/check_doc_numbers.py docs/recon/stage4-preflight.md` → exit 0,
  "33 numbers verified, 32 sources" — matches the progress-log claim. (It does not catch F-1:
  the string "28" occurs in declared source PLAN.md; the checker tests presence, not meaning.)
- **Progress log / commits**: entry present in §12.5 style; commit messages `T-019: …`;
  task diff `1ba3bf9..2061b5c` touches only the two `files_write` + kit bookkeeping; no
  frozen code (`src/ configs/ scripts/ pyproject.toml uv.lock`) changed.

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | MINOR | FIX-DOC | docs/recon/stage4-preflight.md:141 | "(28 items)" for the tuned argv is wrong: the rendered AND recorded argv has **33 items** (my re-render; stock's "12 items" is correct). The flag enumeration on lines 139–141 is itself complete and correct, and every checksum/equality claim holds — only the parenthetical count is off. Change `28` to `33`. |
| F-2 | MINOR | DECIDE | docs/recon/stage4-preflight.md:334-343 (§2.9); card S3 + decision_rights | Card S3: "If any check FAILs, escalate once listing every failure"; must_escalate: "any FAIL". P8 was observed FAIL (T-017's dirty files at `de6d586`) and **no escalation was filed**: the owning lane committed the cause away mid-session, the redo-safe re-check passed, and §2.9 argues the clause attaches to the final Result. Verified: the FAIL was real, the resolution was lane 3's own legitimate commits (not a workaround by T-019 — `ca1d5ad` touches only its own files), the final state is clean, and the reasoning is fully documented. Whether a transient, externally-resolved FAIL triggers the escalation clause is a card-interpretation decision reserved to the planning chat. Options: **(a)** ratify §2.9's reading (recommended — cheapest; optionally record a one-line decision in docs/decisions.md so future pre-flights have precedent); **(b)** require a retroactive escalation brief for the observed P8 FAIL. No re-measurement or code change is implied by either option. |
| F-3 | NOTE | FIX-DOC (not by T-019) | docs/runbook-stage3.md:146 | Pre-existing, outside T-019's scope: the Stage 3 64K row says "804 + 403 + 370 = 1,578 s" but the sum is 1,577 (line 156's Stage 4 row is correct, and the pre-flight correctly copied 1,577). No T-019 action — its `files_write` does not include the runbook. Flag for the step lead / a later docs card (e.g. T-009/T-010). |

## Task verdict

changes-requested

All four acceptance items PASS on my independent re-run, and the pre-flight's substance is
sound — every hash, code citation and runbook signature I re-derived held. F-1 is a one-word
doc fix in the file that stands in for T-007's pre-review, so it should be corrected before
T-007 relies on it. F-2 needs a disposition (DECIDE → planning chat); it does not impugn the
checks themselves. No BLOCKER, no RE-MEASURE, nothing deferred.

## What I did not verify

- The exact dirty diff sizes at first observation (+18/−1 loop-design.md, +2/−1
  loop-states.md at `de6d586`): the transient state is gone. I verified `bc8e0c3` carries
  those files and `ca1d5ad` touches only T-019's own three files, but the observed line
  counts themselves cannot be re-derived.
- The re-check wall-clock time 17:58:14Z (a claim; consistent with the commit sequence
  17:57:03Z → 18:00:22Z → acceptance 18:00:59Z, but not independently recorded).
- The model GGUF's actual sha256 (multi-GB hash): P2's env check compares the DECLARED
  `configs/model.toml` sha256 to the records, exactly as the doc states; the runner verifies
  the real file at session start (`provenance.model_sha256`). I did not re-hash the file.
- `check-quiet.sh` was not executed (it is a Stage 4 session command, not a pre-flight
  check); its exit-code contract and blocklist file were verified from the script/config.
- `docs/runbook-stage1.md` §5 beyond the cited stop rules; `docs/recon/T-001.md` beyond A15
  and the cited acceptance rows; PLAN.md not read whole (protocol) — only grep counts for
  the "28" source-matching explanation.
- T-017's E-006 merits (out of scope; the pre-flight's "unrelated to Stage 4" is consistent
  with the card's note that T-007 is post-review per PLAN v1.2, but I did not review E-006).
- The executor's chat reasoning: not available to me and not requested (protocol).
- No GPU or heavy item was run or deferred: the task is light, and the machine was idle
  (no llama-server, GPU lock free, no in-progress gpu/exclusive-machine task).
