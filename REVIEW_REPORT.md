# Review T-021 (cycle 2)

## Model

Running as: qwen3.8-max-preview (the config records a single model for executor and reviewer; this
review is adversarial and re-derives from the committed raw data, not from the executor's report).

Task: **T-021 — Stage 4 session, run 2** (`exclusive-machine`, `review: post`, status `in-review`,
cycle 2 of `max_review_cycles = 2`). Cycle 1 (`reviews/T-021/r1-REVIEW_REPORT.md`) ended
`blocked-decision` on F-2 (R7 scope); the planning chat decided **E-009 option A** (ratify the
under-load reading, run 2 stands as the S2 run, no re-measure); the executor applied the ruling
(`7ffabc6`) and opened cycle 2 (`1132d90`, event 211 at 19:58:41Z).

Guard: `bash scripts/wf-guard.sh` → `guard: OK`. No gpu or exclusive-machine task in progress
(`pgrep -x llama-server` empty, no machine lock in `/dev/shm`), so **nothing was deferred**.

**Review-open note (protocol step 8):** cycle 2 was already opened by the recovery path after the
E-009 ruling (state `review_cycles.T-021 = 2`, event `review-opened cycle 2`), as the cycle-1
handoff and `docs/recon/T-018-kit-repair.md` §6 direct. `wf.sh review-open` was therefore **not**
re-run — it refuses any status other than `done`/`changes-requested` and would die on `in-review`.
`review-verdict` archives this report as `reviews/T-021/r2-REVIEW_REPORT.md` (cycle = 2).

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-021` myself (record **run 5**,
`.workflow/acceptance/T-021.json`, at HEAD `1132d90`, **0 failures**). A1–A4 reproduce the
executor's runs 1–4 exactly, including the A2 output hash (`1bdc8ec315118630…`, 574 bytes, all
five runs) and both evidence hashes (`6eb755638dd6…`, `420f0b96b8c0…` — the latter matches the
current file byte-for-byte).

| item | verdict | note |
|---|---|---|
| A1 | PASS | `docs/recon/stage4-session-run2.txt` = `stage4-run2` (11 bytes); `docs/recon/stage4-session.txt` = `stage4`. Files differ; run 1's session file is not in the T-021 diff (`git diff c4bdc4d^..HEAD -- docs/recon/stage4-session.txt` empty). |
| A2 | PASS | `COVERAGE_CMD` exit 0, output sha identical to all four executor runs. |
| A3 | PASS | Ran `GATE_CMD` directly with `SESSION=stage4-run2`: exit 0, PASS a–f. The post-re-run block quoted at `docs/stage4-run2-conditions.md:199-215` is **byte-identical** to my live re-run after removing the 2-space markdown list indentation (diffed programmatically). No `^- R2 applied` line exists (grep count 0) — the PASS branch is the one that holds. |
| A4 | PASS | `git status --porcelain -- data` empty; no `llama-server`. Both job `status.json` files: `exit_code 0`, `state done` (main 14:30:49Z→14:56:54Z, re-run 14:59:35Z→15:08:49Z); pids 9210 / 11147 match `session.json` `runs`. |
| A5 | PASS | Every clause re-verified; the link clause is read **per DECISION E-009** (the ruling's Scope explicitly directs this reading of the frozen card wording — no plan amendment). Detail below. |

### A5 clause by clause (all re-derived this cycle)

- **Clean committed start at an R3-passing commit.** `session.json` git:
  `c4bdc4db4a4378282c68bd858a718ece74710c09`, `dirty: false`, `dirty_paths: []`,
  `allow_dirty: false`. R3 re-run by me at `c4bdc4d` **and** at HEAD: both exit 0. The only
  changed paths since the Stage 3 commit `8096461` are CLAUDE.md, .gitignore and the kit's
  `wf*.sh`/`_wf.py` (T-018's ruled exception); `src/`, `configs/`, `pyproject.toml`, `uv.lock`
  untouched; the one new test file (`tests/test_wf_unblock.py`) is T-018's and outside R3's paths.
  `c4bdc4d^ = 9cc1c16`, as the log states.
- **Runbook followed.** The launch command in the job `status.json` is the runbook §6 form via
  `run-sweep.sh` with `--session-id stage4-run2` — the card-sanctioned adaptation:
  `scripts/run-sweep.sh:77` dies on an existing session dir, so the literal `--session-id stage4`
  cannot create a second session; a CLI argument, no code change, no `--allow-dirty`.
- **Quiet at start and every poll.** Recorded exit 0 at start, 4 polls, pre-re-run and end; the
  committed runner preconditions (7 events in `events.jsonl`) are all `ok: true`, `waited_s 0.0`,
  `attempts 1`, busy 0.03–0.84%, MemAvailable 27.93–28.47 GiB — exactly the log's figures. The
  verbatim `check-quiet.sh` blocks themselves are live readings with no committed source (see
  "What I did not verify"); `check-quiet.sh` is unchanged since the start commit.
- **Link read 4, 8 at every sample — per E-009.** Re-derived from all 7 telemetry files
  (3,805 data rows, 0.5 s cadence): **all 2,657 rows of the three measured cell instances are
  (4,8)** (stock-i0 1,544, stock-i1 342, tuned-i0 771); **3,556 sustained-generation samples
  (P1 ∧ ≥50 W ∧ ≥2500 MHz), 0 non-(4,8)**; and — stronger than the ruling requires — **0 rows
  session-wide violate the clarified predicate itself** (P-state P1 ∨ power ≥ 50 W, any
  utilization). Exactly **2 rows** have util > 0 with gen ≠ 4, both 0.5 s idle→load ramps in
  re-run canaries, each back at Gen4 on the next sample; every field matches the log
  (15:01:21.726Z: util 94, gen 2, 9.92 W, P5, 1012 MHz, preceding power 34.8→23.85→23.85→10.22 W,
  next sample gen 4 / 28.5 W / P1 / 2820 MHz / util 96; 15:07:42.999Z: util 26, gen 2, 9.77 W, P5,
  577 MHz, previous util 0 / gen 2 / 10.12 W, next gen 4 / 32.61 W / P1 / util 96). Poll 3's
  4,2,2,1,4 sequence reproduces from canary-end telemetry at the poll's nominal 1 s phase
  (14:55:43–47), with util 0.0 throughout 14:55:41.474–14:55:46.476Z and the gen transitions at
  the exact logged timestamps. Neither ramp row is inside a measured window (canaries are not
  S2 data).
- **Run 1 untouched.** `git diff c4bdc4d^..HEAD -- data/raw/stage4 docs/recon/stage4-session.txt
  docs/stage4-conditions.md` empty; `data/raw/` byte-identical to the session commit `19015b0`
  reviewed in cycle 1 (`git diff 19015b0..HEAD -- data/raw/` empty).
- **Re-run pass done (once).** Exactly one rerun job dir; its command carries `--rerun-flagged`;
  the attempt-2 stock window (repetition 2) is clean: `major_faults 0`, `vmswap_max 0.0`,
  `n_samples 297`; re-run canaries 6 of 6 windows clean; drift rerun flag null.
- **Conditions log complete.** The cycle-1 omissions are repaired and verified (below); number
  checker exit 1 with exactly **7 of 56** unverified — the seven live poll readings with no repo
  source (75.91, 39.5, 74.60, 4.7, 67.67, 5.8, 107.8), the same established pattern as run 1's
  accepted log.

### Cycle-1 findings: all six verified addressed

- **F-1 (MAJOR, fit warning).** The warning section matches the raw data field-for-field:
  `events.jsonl` 14:40:31Z `fit_changed_explicit_placement` (18 MiB, [42,42],
  `tensor_overrides_to_cpu true`, `fit_succeeded false`); the four `startup_excerpt` lines are
  verbatim; the cross-session table re-computes (14766 projected; 15803/15803/15772 CUDA free;
  headroom 1037/1037/1006; 1024−1006=18). Identity checks re-run by me: `argv` equal across
  stage3-64K/stage4/stage4-run2 (33 items), `resolved_config` equal, both resolved TOMLs
  byte-identical across the three sessions, `props` equal (`n_ctx_per_slot 65536`, build
  `b12208-57d04820d`), run-2 VRAM equals run 1 exactly (14934/15280/15292/1019; stage3 differs by
  2 MiB: 15290/1021), `before_launch_mib` 3→2. The other four sessions each have exactly one
  `code_commit_changed` warning and run 2 has none — as claimed. T-008 handoff named.
- **F-2 (MAJOR DECIDE → E-009).** Ruling applied exactly per its Rule and Scope: the
  `- R7 clarified:` line (`docs/decisions.md:1295`) matches the decision's Rule text; the
  telemetry-verification section, the two ramp rows with context samples, the process note (the
  executor should have escalated the ambiguity) and the evidence wording are all present and
  re-derived correct; the poll-3 entry is marked Resolved with the E-009 pointer; the end-summary
  link bullet and the `docs/decisions.md:1297` run-2 line use the ruling's wording. The run-2
  line's figures all check out (launch 14:30:49Z from c4bdc4d, 26.1 + 9.2 min, gate PASS a–f
  before and after, 5 clean units per cell, R1/R2 not needed).
- **F-3 (MINOR, sources/derived).** The sources line now names `session.json`, `events.jsonl` and
  all eight cited cell records; checker result 7/56 as claimed; the log states the remaining
  readings are live observations with no repo source. `docs/decisions.md`: exit 0, **332 numbers
  verified**, as the progress log claims.
- **F-4 (MINOR, VRAM label).** Relabelled to `min_free_mib` with the after-warmup values beside:
  1019/1031 (tuned), 1353/1355 (stock a1), 1355/1355 (a2), 1329/1329 (canaries) — all match the
  cell records exactly.
- **F-5 (NOTE, poll convention).** The note is accurate. I emulated the loader independently
  (`records.py` groups by `batch_id`, emits only batches with `batch_size` records and unique
  indices; `status.py` counts all requests incl. warm-ups): 127 requests + 7 cell records, 30
  batches, none incomplete in the final file. Visible counts: poll 1 = **41 at 14:39:16Z** (the
  row is stamped at poll start, before check-quiet's 10 s window), poll 2 = **64**, poll 3 =
  **90**, re-run poll = **118** — exactly as logged. The stock repetition-2 batch
  (`e93a808af352`, 7 paging requests) completes at **14:48:37Z**, after poll 2 and before poll 3,
  so poll 2's "still none" is correct. (My first emulation pass disagreed — it had counted the 7
  cell records as requests; corrected, everything reproduces. No finding.)
- **F-6 (NOTE, gitignored job logs).** Carry-forward to T-013/T-015 recorded in the progress log;
  no T-021 file change required, as the finding itself said.

### Other numbers re-derived this cycle

Phase times: stock 750.30 s (150.1/rep), tuned 373.05 s (74.6/rep), canaries 122.04/123.36 s,
re-run canaries 124.39/121.88 s, attempt-2 stock 148.78 s; run 1 stock 1197.08/5 = 239.4 s, tuned
499.88/5 = 100.0 s; run-1 tuned attempt 1 flagged reps [0,2,4] = 3 of 5 (the log's comparison is
about the tuned cell, and is correct). Drift 0.004064964→0.00406 and 0.003733887→0.00373,
threshold 0.05, no flags. Flags: exactly 7 paging request records, all stock-64K repetition 2
attempt 1; flagged window `major_faults 5562`, swap growth 2751.93→2752 MiB. Inhibit tags
`…-1794666649` / `…-1794668375` match the job commands and `session.json`. Provenance
(manifest/sampling/model sha256, llama.cpp commit `57d04820d`, seed 20261109, cell order,
repetitions 5) identical across stage3-64K/stage4/stage4-run2; `spec_sha256 6a11e6b1…` identical
to run 1 (stage3-64K's differs, as expected — it is the stage3 spec; the log claims run-1
identity only, correctly). T-020 citations check out: `pcie-link.md` "ten under-load samples …
all read 4, 8", 14.29/14.38/14.39 GB/s, `Result: link PASS`.

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | NOTE | FIX-DOC | .workflow/acceptance/T-021.json run 4 (`git_commit b02aa4d`, evidence sha `420f0b96…`); `git show b02aa4d:docs/stage4-run2-conditions.md` sha `404b55cd…`; scripts/_wf.py cmd_accept | None for T-021. Acceptance run 4 was executed with the E-009 edits still uncommitted: `cmd_accept` records HEAD at start but hashes the working tree, so the record's commit does not contain its own evidence hash. The kit permits this and the progress log does not misstate it; substance unaffected — my run 5 at HEAD `1132d90` reproduces A1–A4 with the same evidence hash. Kit-hygiene observation only (a future kit task could record a dirty flag); no doc or code change warranted now. |
| F-2 | NOTE | FIX-DOC | reviews/T-021/r1-REVIEW_REPORT.md (4,091 rows; power decay 75→42→35→24→10 W); docs/stage4-run2-conditions.md:231-232,236; escalations/E-009.md:28 | None. Two cycle-1 review figures do not reproduce from the raw data: the session total is **3,805** data rows (not 4,091) and the ramp's preceding power decay is **34.8→23.85→23.85→10.22 W**. The executor's amended log carries the correct values and an explicit count note; every substantive count (3,556 / 2,657 / 2 ramp rows) was always correct and the E-009 ruling does not depend on the wrong total. The archived r1 report and the E-009 brief stay as written (append-only history); this note records the correction for the audit trail. |

No BLOCKER, MAJOR or MINOR findings. Nothing warrants RE-ANALYSE or RE-MEASURE; none is ordered.

## Task verdict

accepted

A1–A4 PASS on my own re-run (run 5, 0 failures, evidence hashes match HEAD). A5 PASS with the
link clause read per DECISION E-009, as the ruling's Scope directs: every measured-cell sample
is Gen4 x8, the clarified R7 predicate has zero violations session-wide, and the only non-(4,8)
readings are idle downshifts and the two documented 0.5 s ramp rows. All six cycle-1 findings are
verified addressed, the E-009 ruling is applied exactly, run 1 is untouched, the raw data is
byte-identical to the session commit, and every measurement claim I sampled re-derives from the
committed data. The two NOTEs require no action. T-008 proceeds on run 2 (R5), carrying the
kernel/driver confound with F-1's 31 MiB free-memory drop as a second concrete symptom, and
reporting run 1 as the excluded diagnostic; the F-6 carry-forward to T-013/T-015 stands.

## What I did not verify

- **The executor's chat reasoning** — not available to me and not requested, per protocol.
- **Live, point-in-time readings with no committed source**: the `check-quiet.sh` verbatim blocks
  and process counts (405/420/421/412/415/410); top-5 resident/CPU process names and figures;
  `nvidia-smi` memory.used 2 MiB before start/after end; pre-start MemAvailable 29,410,316 kB and
  load 0.27; poll-time MemAvailable, swap, GPU MiB and pid readings; the 30-sample R7 burst at
  14:56:52–14:57:07Z (quoted only in the log, never saved as a repo file). The poll-3 link
  sequence **is** independently confirmed by telemetry; the burst itself is not. The committed
  runner preconditions, telemetry and cell snapshots — the machine-state claims that do have a
  source — were all re-derived.
- **The exact sub-second sampling phase of poll 3's five link samples.** The logged 4,2,2,1,4
  reproduces at the poll's nominal whole-second phase (14:55:43–47); a different phase could
  yield a different sequence. The idle-gap conclusion (util 0.0 throughout the downshift) is
  phase-independent and machine-confirmed, and E-009 rules on that basis.
- **"Mains power: yes"** and Zack's "go" at the human gate — recorded in the log, not re-derivable.
- **The pre-re-run gate output as a live re-run.** The session now contains the re-run data, so
  `GATE_CMD` reproduces only the post-re-run block (byte-identical). The pre-re-run block was
  checked for internal consistency: 4 cells listed, `drift {'main': None}`, "0 of 11" denominator
  (5 tuned + 3 canary-start + 3 canary-end). No pre-re-run session directory was reconstructed.
- **`model_sha256` against the GGUF on disk** — cross-session identity confirmed, the ~20 GB file
  not re-hashed.
- **`REPRO_CMD` (the S2 check), `REPORT_CMD`, `SCRUB_CMD`, `CI_CMD`** — not run; S2 is T-008's
  step, the release checks T-013/T-015's.
- **T-020's repair work and `pcie-link.md` beyond the cited figures** (ten under-load samples,
  14.29–14.39 GB/s, `Result: link PASS`, kernel/driver lines); run 1's conditions log beyond the
  figures re-derived here (239.4/100.0 s per repetition, 3 of 5 tuned paging-flagged, the 38.3 min
  duration was a cycle-1 check, not re-run).
- **Whether the 31 MiB CUDA free-memory drop is caused by the driver upgrade** — correlation
  established (same projected usage, configs, binary; different driver), old driver not tested;
  no such test should run without a decision.
- **Docs outside the T-021 diff** — `PLAN.md` (never read whole, per protocol), `PROGRESS.md`
  rendering, `docs/decisions.md` beyond the R5–R7/E-009/run-2 lines.
- **State changes**: the only tree modification I made before the verdict is
  `.workflow/acceptance/T-021.json` (run 5, via the sanctioned `wf.sh accept`) plus this report;
  `review-open` was not re-run (cycle 2 already open, see above); the sole state change is
  `wf.sh review-verdict`.
