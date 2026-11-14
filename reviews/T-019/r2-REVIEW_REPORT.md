# Review T-019 (cycle 2)

## Model

qwen4-max-preview (the config records a single model for executor and reviewer).

## Why this cycle exists

Cycle 1 (`reviews/T-019/r1-REVIEW_REPORT.md`) returned **changes-requested** with F-1
(MINOR FIX-DOC: tuned argv parenthetical "28 items" → 33), F-2 (MINOR DECIDE: does card
S3's escalation clause attach to a transient, externally-resolved P8 FAIL?) and F-3
(NOTE, out of T-019 scope: runbook line 146 sum 1,578 → 1,577). Since then:

- F-1 fixed in `1607d8e` (disposition accept, event 121); acceptance runs 2–3, 0 failures.
- F-2 escalated as **E-007** (`e3e0e8d`, disposition escalate, event 122); the planning
  chat decided **option A** (2026-11-13T18:42:53Z): the clause attaches to the final
  Result; §2.9's reading is ratified; a scoped one-line precedent is to be recorded in
  `docs/decisions.md`; rule 3 routes F-3 and the review-parser limitation into the T-018
  amend after T-008 (sessions do not add or fix them).
- The closing session (`56e1c39`) applied E-007: precedent line recorded, acceptance
  run 4 (0 failures), closed `start → accept → done` (events 126–127). It opened **no**
  cycle 2, per rule 2 ("no review cycle 2 is needed because no BLOCKER or MAJOR was
  fixed"), and flagged the consequence: the frozen kit's `task_deps_satisfied`
  (`scripts/_wf.py:434-443`, re-read by me) requires a post-review dependency to be
  `accepted`, so **T-007 stays `todo` at T-019 `done`**; the only path to `accepted` is a
  review verdict, and the entry names "a manual `/review T-019`" as the confirming path.

Zack then invoked `/review` (no argument); the command's selection rule picks T-019 (the
first `done` task whose card requires review — T-001…T-006 are `done` + `review: none`,
which the kit treats as complete, `_wf.py:1338-1340`). **This cycle is that confirming
review.** E-007 rule 2 is permissive ("not needed"), not prohibitive; nothing in the
decision conflicts with reaching `accepted` through the kit's normal review path, and
this verdict is what unblocks T-007. It uses the last permitted cycle
(`max_review_cycles = 2`). Session note: the closing commit landed while this review
session was starting (status read `changes-requested` at first, `done` at card time);
everything below was re-derived against the final state `56e1c39`, tree clean.

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-019` myself (**run 5**, 2026-11-13T18:59:58Z at
`56e1c39`): A1–A3 PASS, A4 judgement, **0 failures**; evidence hash `3acb8be31223…`
matches the file on disk (26,267 bytes), identical to runs 3–4. No heavy items: the task
is `light`, no GPU job in progress (`pgrep -x llama-server` empty, `.locks/gpu.lock`
probe free, no gpu/exclusive-machine task in progress — T-007 is `todo`). Nothing
DEFERRED.

| item | verdict | note |
|---|---|---|
| A1 | PASS | kit run 5: `grep -cE '^\| P[1-8] \| (PASS\|FAIL) \|'` → `8`; I read all eight rows (lines 77–84) and re-derived every one (§ below). |
| A2 | PASS | kit run 5: `Result: all checks PASS` present (line 345, the file's last line). |
| A3 | PASS | kit run 5 and my own `pgrep -x llama-server`: empty. No `data/raw/stage4*` path; newest `data/logs/jobs/` entry is `t001-probe20-20261112T223847Z` (12 Nov, predates T-019). |
| A4 | PASS (judgement) | Every P-row carries re-runnable evidence (each §2.x inlines its commands); P2 compares BOTH cells' argument lists plus the canary; no server/GPU use is supported by the command classes (file reads, `--help`/`check`, git queries, lock probes) and the artifact checks above. Re-derived independently below. |

### What I re-derived myself (not copied from the executor's or cycle 1's record)

- **F-1 fix scope**: `git diff 2061b5c HEAD -- docs/recon/stage4-preflight.md` is exactly
  one line, `(28 items)` → `(33 items)`. Raw records:
  `data/raw/stage3-64K/cells/stock-64K-22dc1178.json` argv has **12** items,
  `tuned-64K-f9b81a84.json` argv has **33** — counted myself. Doc sha256
  `3acb8be3122303723db1a9ec4a5828292d258069bab0d028754c19778107609e`, 26,267 B = the
  acceptance evidence hash.
- **P2 (independent re-render)**: my own scratch script
  (`/tmp/t019-review-c2/render_check.py`, read-only, not the executor's inlined one)
  through the runner's path (`load_sweep` → `spec.expand` → `ServerConfig.model_validate`
  → `render_argv` / `spec.render_toml` / `provenance.config_hash`, verified against
  `session.py:315-327` and `canary_job` `session.py:813-836`). Results match the doc's
  table exactly:
  - stock-64K: argv byte-equal, sha256 `ab87c02d…e04b7f`, config_hash `22dc1178c8d9b555`,
    resolved TOML byte-equal, sha256 `a4272770…d42bbd`, 12 items, no `--cache-ram`.
  - tuned-64K: argv byte-equal, sha256 `4775ccde…86ef31`, config_hash `f9b81a840bab20cf`,
    resolved TOML byte-equal, sha256 `735f0aeb…093ffb`, 33 items.
  - canary (inline-cell path): argv byte-equal to `canary-start-debea778.json` (22 items),
    config_hash `debea7788d296087`, resolved TOML byte-equal; all four recorded canary
    cells share that single hash.
  - `smallpc.render` CLI on each recorded resolved TOML prints exactly
    `shlex.join(recorded argv)` → True for both cells; `configs/model.toml` declared
    sha256 and `data/env/build-info.json` commit equal the recorded values in both cells.
    Summary: `all_equal: true`.
- **P1**: all seven named scripts executable; `_common.sh` correctly not executable;
  `.locks/gpu.lock` exists, 0 bytes, `flock -n` probe free.
- **P3**: `sweep run --help` lists `--resume`, `--rerun-flagged`, `--only`; wrapper usage
  lists the same; forwarding at `run-sweep.sh:86-90` re-read.
- **P4**: `data/raw/stage4` absent (no `stage4*` path at all); `run-sweep.sh:77` refusal
  re-read.
- **P5**: `du -sb` reproduces 647,211 / 746,917 / 775,006 B exactly; 2 × 775,006 =
  1,550,012; free space now 152,697,049,088 B (recorded 152,697,622,528 B — normal
  drift), PASS by ~5 orders of magnitude.
- **P6**: `bash -n` exit 0; sourcing sets `SESSION=stage4` + the six named variables;
  uv, shellcheck, ruff 0.17.4, pytest 9.2.0 exist; module subcommand lists match
  (`{headline,gate,repro}`, `{coverage}`, `{render,coverage,repro}`, scrub `[--check] paths`).
- **P7**: R3 check run verbatim at `56e1c39` → exit 0; the filtered diff is exactly the
  12 claimed kit paths; `stage3-commit.txt` = `80964618df8ff8bba88c784298e4fae3cf712f05`;
  `date -u +%F` = 2026-11-13.
- **P8**: `git status --porcelain` empty before my accept run (only the run-5
  bookkeeping is dirty now); sweep dirty check (`src configs scripts`) empty;
  `.workflow/state.json` and `PROGRESS.md` tracked. Historical claims re-derived:
  `bc8e0c3` (2026-11-13T17:50:11Z) carries the loop-design/loop-states edits; `1ba3bf9`
  (17:52:46Z); `ca1d5ad` (17:57:03Z) touches ONLY T-019's three files — no other lane's
  file was committed by T-019.
- **S1 spot-checks against code and runbook** (the promises T-007 will rely on):
  `gate.py:26-27` `PAGING_LIMIT_PCT = 40`, `SWAP_LIMIT_MIB = 1024.0`; judged groups
  tuned+canary only, stock "reported only; stock windows never fail the gate"; gate JSON
  `pass`/`failed`; `cli.py` gate/repro return EXIT_OK on pass (lines 50/60);
  `repro.py` `MIN_CLEAN_PAIRED` fallback and the exact `**S2 evaluated on ALL units
  (flagged units included) for: …**` first line; `report.py:1072` `REPRO_METRICS`
  (`T_turn_400 (s)` first), `REPRO_REL = 0.05`, "inside the original 95% CI or within 5%
  … whichever is wider"; `run-sweep.sh:53` spec check, `:55-61` dirty check on
  `src configs scripts` only, `:77` existing-session refusal; `run-detached.sh:37-42`
  fd-8 probe / exit 75; `with-gpu-lock.sh:22-25` fd 9 / exit 75; `_common.sh:7`
  `.locks/gpu.lock`; `server.py:1-2` start/stop only through the launch/stop scripts;
  runbook line 19 "Stock keeps llama.cpp's defaults, **including `--cache-ram 8192`**"
  (consistent with the rendered stock argv carrying no explicit `--cache-ram`);
  runbook line 156: 804 + 403 + 370 = 1,577 s / 26 / 29 / 44 min. All match the doc.
- **Spec identity**: `diff configs/sweeps/stage3.toml configs/sweeps/stage4.toml` differs
  only in header, `name`, `expect_cells` (6 vs 2), the four non-64K cell blocks and one
  comment above `[canary]`; 64K blocks, `[defaults]`, `[stock_defaults]`, `[canary]`
  identical. `sweep check configs/sweeps/stage4.toml` exit 0: cells 2, cells_in_spec 2,
  stock 1 / tuned 1, both 64K, repetitions 5, canary true, first_in_order
  `[tuned-64K, stock-64K]`.
- **Number checker**: pre-flight doc → exit 0, "33 numbers verified, 32 sources"; the
  three T-019 progress-log entries extracted alone → exit 0, "8 numbers verified,
  17 sources".
- **E-007 application**: the **Precedent** line under DECISION E-007 in
  `docs/decisions.md` is verbatim rule 1's scoped sentence (all five conditions + "Any
  other FAIL still escalates"); `56e1c39` touches only `.workflow/acceptance/T-019.json`,
  `.workflow/state.json`, `PROGRESS.md`, `docs/decisions.md`, `docs/progress-log.md`
  (the decisions.md write is decision-directed by rule 1 itself); events 126–127 record
  `started` → `done` with accept run 4 at `e3e0e8d`, 0 failures, hash unchanged.
- **Rule 3 compliance**: `docs/runbook-stage3.md:146` still says 1,578 (NOT fixed —
  correct, routed to the T-018 amend); runbook last touched at `f697aa8` (WP13);
  `git diff ca1d5ad^ HEAD -- src configs scripts pyproject.toml uv.lock` is EMPTY — no
  frozen code changed anywhere in the T-019 window, so the parser limitation
  (`_wf.py` `parse_review_report`, action-column regex) is untouched as required.
- **Dispositions**: F-1 accept, F-2 escalate recorded (events 121–122). F-3 could not be
  registered: the frozen parser's regex `^\|\s*(F-\d+)\s*\|\s*([A-Z]+)\s*\|\s*([A-Z-]+)\s*\|`
  does not match r1's action column "FIX-DOC (not by T-019)" — I re-read the code and
  confirm the refusal is real; it is documented in E-007's secondary note and the
  progress log, and routed by rule 3. No hand edits of state or archived reports.
- **Progress log**: three T-019 entries (pre-flight, address-review, E-007 close) in
  §12.5 style with sources lines; the closing entry honestly flags the T-007 dependency
  tension ("flagged, not worked around").

## Observations (no action required of T-019)

- The number checker over the WHOLE progress log exits 2: the **T-017** entry (line 471,
  added by `92c9935`) declares `.workflow/lanes/3.json`, which no longer exists in the
  main checkout. Pre-existing, already flagged in T-019's first log entry; it belongs to
  T-017's pending cycle-2 review, not to T-019.
- Doc lines 138–141: "the same head plus … `--metrics`, `-lv 4`" has an ambiguous
  antecedent (stock's "head" already lists `--metrics`/`-lv 4`). The tuned enumeration is
  in fact the exact rendered argv order and the count 33 is correct (my re-render);
  every checksum pins the list. No substantive claim affected; no action.
- This cycle's bookkeeping (accept run 5, this report, `reviews/T-019/r2-…`, cycle-2
  state) is uncommitted at verdict time; the next session commits it before T-007's
  clean-tree check, exactly as `1607d8e` committed cycle 1's.

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| (none) | | | | |

## Task verdict

accepted

All four acceptance items PASS on my own re-run (run 5, 0 failures). F-1 is fixed and
independently verified against the raw argv records and my own re-render; F-2 is resolved
by E-007 option A with the precedent recorded verbatim and §2.9 ratified; F-3 and the
parser limitation are routed per rule 3 and were correctly left untouched. No frozen code
changed, `files_write` respected (the decisions.md write is decision-directed), the
close-out went through the kit's normal commands, and the dependency-gate tension was
flagged rather than worked around. This confirming cycle — invited by the closing
session's flag and invoked by Zack via `/review` — supplies the `accepted` status the
kit requires for T-007 to become ready. No findings against T-019.

## What I did not verify

- The transient dirty diff sizes at first observation (+18/−1 loop-design.md, +2/−1
  loop-states.md at `de6d586`): the state is gone. I verified `bc8e0c3` carries those
  files and `ca1d5ad` touches only T-019's own three files, but the observed line counts
  cannot be re-derived (same limit as cycle 1).
- The re-check wall-clock time 17:58:14Z: a claim, consistent with the commit sequence
  (17:57:03Z → 18:00:22Z → acceptance 18:00:59Z), not independently recorded.
- The model GGUF's actual multi-GB sha256: P2 compares the DECLARED `configs/model.toml`
  sha256 to the records, exactly as the doc states; the runner verifies the real file at
  session start (`provenance.model_sha256`). I did not re-hash the file.
- `check-quiet.sh` was not executed (a Stage 4 session command, not a pre-flight check);
  its exit-code contract and blocklist were verified from the script/config only.
- The runbook was spot-checked at the cited signatures (gate, repro, durations,
  `--cache-ram`, stop rules), not re-read line by line; cycle 1 did the full §1–§7 pass
  and the pre-flight doc is byte-identical since then except the one-word F-1 fix.
- T-017's pending cycle-2 review and the merits of E-006: out of scope (T-017 is
  `in-review`, a separate cycle).
- The executor's chat reasoning: not available to me and not requested (protocol).
- No GPU or heavy item was run or deferred: the task is light and the machine was idle
  (no llama-server, GPU lock free, no in-progress gpu/exclusive-machine task).