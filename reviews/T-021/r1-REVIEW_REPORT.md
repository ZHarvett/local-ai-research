# Review T-021 (cycle 1)

## Model

Running as: qwen4-max-preview (the config records a single model for executor and reviewer; this
review is adversarial and re-derives from the committed raw data, not from the executor's report).

Task: **T-021 — Stage 4 session, run 2** (`exclusive-machine`, `review: post`, status `done`,
0 prior review cycles, `max_review_cycles = 2`). Selected as the first `done` task with a review
requirement: T-001…T-004, T-006 and T-020 are `review: none`.

Guard: `bash scripts/wf-guard.sh` → `guard: OK`. No gpu or exclusive-machine task in progress
(`pgrep -x llama-server` empty), so **nothing was deferred** — every acceptance item was re-run.

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-021` myself (record run 2,
`.workflow/acceptance/T-021.json`, `finished_utc 2026-11-14T15:18:07Z`, **0 failures**).
A1–A4 reproduce the executor's run-1 record exactly, including the output hashes
(A2 `1bdc8ec315118630…`, 574 bytes, both runs).

| item | verdict | note |
|---|---|---|
| A1 | PASS | `docs/recon/stage4-session-run2.txt` = `stage4-run2` (11 bytes, sha `6eb755638dd6…`); `docs/recon/stage4-session.txt` = `stage4`, last touched by `9c64812` (T-007). Files differ; run 1's file is not in the T-021 diff. |
| A2 | PASS | `COVERAGE_CMD` exit 0, 7.5 s, output sha identical to the executor's run. |
| A3 | PASS | Ran `GATE_CMD` directly with `SESSION=stage4-run2`: exit 0, `PASS` on a–f. The post-re-run block quoted at `docs/stage4-run2-conditions.md:144-160` is **byte-identical** to my live re-run (diffed programmatically). R2 was not needed and no `R2 applied` line exists — the PASS branch is the one that holds. |
| A4 | PASS | `git status --porcelain -- data` empty; no `llama-server`. Both job `status.json` files read: `exit_code 0`, `state done` (main 14:30:49Z→14:56:54Z, re-run 14:59:35Z→15:08:49Z). |
| A5 | ESCALATE | Every clause verified **except two**. (i) "the link read 4, 8 at every sample" is not literally true and its scope is the planning chat's to rule on — see **F-2**. (ii) "the conditions log is complete" fails on the omitted runner warning — see **F-1**. All other clauses PASS: clean committed start (`session.json` git `c4bdc4db4a4…`, `dirty: false`, `dirty_paths: []`, `allow_dirty: false`); R3 re-verified by me at `c4bdc4d` (PASS); runbook §6 followed command-for-command; quiet at start/polls/re-run/end; run 1's data, session file and conditions log untouched (`git diff c4bdc4d^..HEAD -- data/raw/stage4 docs/recon/stage4-session.txt docs/stage4-conditions.md` empty); exactly one `--rerun-flagged` pass. |

### What I re-derived independently (not taken from the report)

- **R7 from raw telemetry, 0.5 s cadence, all 7 cell instances (4,091 rows).** Defining sustained
  generation as `pstate P1` ∧ `power ≥ 50 W` ∧ `gr clock ≥ 2500 MHz`: **3,556 samples, 0 non-`(4,8)`**.
  Stronger: **every sample of the three measured cell instances is Gen4 x8** — `stock-64K-i0` 1,544,
  `stock-64K-i1` 342, `tuned-64K-i0` 771 = 2,657 rows, no exception at any utilization. Only the
  canary instances show idle downshifts. Exactly **2** rows in the whole session have
  `util > 0` with `gen ≠ 4`; both are idle→load ramps (see F-2).
- **Poll 3 reconstructed.** `canary-end` telemetry shows `util 0.0` from 14:55:41.474Z to
  14:55:46.476Z, with `gen` 4→2 at 14:55:43.975 and 2→1 at 14:55:45.976, back to 4 at 14:55:46.977.
  Sampling that at 1 s yields **4, 2, 2, 1, 4** — the exact sequence logged at
  `docs/stage4-run2-conditions.md:75-76`. The executor's "idle gap between canary requests"
  inference is confirmed by machine data it did not cite.
- **Poll counts.** Emulated `records.py:225-231` (group by `batch_id`, emit only complete batches)
  against `records.jsonl` timestamps: poll 2 = **64 requests, flags none**; poll 3 = **90 requests,
  paging 7**; re-run poll = **118 requests, 6 cell records** — all three exactly as logged. Poll 1's
  "41" is reached at 14:39:16Z, ~4 s after the row's 14:39:12Z timestamp (F-5).
- **Flags and clean units.** 7 `paging` request flags, all `stock-64K` repetition 2 attempt 1
  (14:46:16Z…14:48:37Z). Windows: stock a1 4 clean of 5, stock a2 1 of 1, tuned a1 5 of 5,
  canaries 3 of 3 each. Gate f denominators 11 (5+3+3) before and 17 (5+3×4) after the re-run
  are correct. **Both cells end with 5 clean units; R1 fallback not needed** — confirmed.
- **Major faults / swap from telemetry.** Attempt-2 stock window: `majflt` delta **0**,
  `server_vmswap` max **0.0 MiB**, 297 rows = the recorded `n_samples`. Attempt-1 rep 2:
  `majflt` delta **5,562** = the gate's figure. Both re-run canaries: `majflt` delta **0**.
- **Provenance equality with run 1 and Stage 3.** `spec_sha256`, `manifest_sha256`,
  `sampling_sha256`, `model_sha256`, `llama_cpp_commit`, `shuffle_seed 20261109`,
  `cell_order [tuned-64K, stock-64K]`, `repetitions 5` all identical across
  `stage3-64K`, `stage4`, `stage4-run2`. `configs/` unchanged since the Stage 3 commit
  (`git diff --stat 8096461 HEAD -- configs/` empty). `resolved/{stock,tuned}-64K.toml`
  byte-identical across the three sessions.
- **Arithmetic and durations.** 26.1 min (14:30:49→14:56:54), 9.2 min (14:59:35→15:08:49),
  run 1 38.3 min (22:42:12→23:20:30); stock 750.30/5 = 150.1 s, tuned 373.05/5 = 74.6 s;
  run 1 stock 1197.08/5 = 239.4 s, tuned 499.88/5 = 100.0 s; drift 0.004064964→0.00406 and
  0.003733887→0.00373; all GiB/MiB conversions in the log recomputed and correct;
  7 preconditions all `ok: true`, `waited_s 0.0`, `attempts 1`, busy 0.03–0.84%,
  MemAvailable 27.93–28.47 GiB. Inhibit tags match `session.json`.
- **Session-id adaptation is card-sanctioned and necessary.** `scripts/run-sweep.sh:77`
  dies with `session already exists: data/raw/$sid (use --resume)`, so the runbook's literal
  `--session-id stage4` cannot produce a second session. `--session-id stage4-run2` is a CLI
  argument — no code change, no `--allow-dirty` — and A1 requires the two files to differ.
  `src/smallpc/stage3/repro.py` has no session-id validation, so T-008's `REPRO_CMD` will accept it.
- **Confound confirmed live.** `uname -r` = `7.3.4-1-cachyos`, driver `620.70.06`, as logged.
- **`check-quiet.sh` semantics.** It exits 1 only on a blocklisted app; the 1.5 GiB resident
  warning exempts `llama-server` and `claude`, and the CPU busy figure is informational. So
  `exit 0` at loaded polls (busy 10.9%, 20.2%) is correct, not a contradiction.

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | MAJOR | FIX-DOC | data/raw/stage4-run2/events.jsonl (14:40:31Z warning); cells/tuned-64K-f9b81a84.json `placement_check` + `startup_excerpt`; docs/stage4-run2-conditions.md:162-192 | Record the session-unique `fit_changed_explicit_placement` warning on tuned-64K, with the identity check and the driver-confound link, in the conditions log; hand it to T-008. No re-measure. |
| F-2 | MAJOR | DECIDE | docs/stage4-run2-conditions.md:75-94,189-192; card T-021 `decision_rights.must_escalate`; telemetry/canary-rerun-start-debea778-i0.csv.gz 15:01:21.726; telemetry/canary-rerun-end-debea778-i0.csv.gz 15:07:42.999 | Planning chat rules on the scope of R7's "while a server is generating" and on the executor resolving it without an escalation brief. Options and reviewer recommendation below. Reviewer does **not** order RE-MEASURE. |
| F-3 | MINOR | FIX-DOC | docs/stage4-run2-conditions.md:9,137,170-172,175,184; `tools/check_doc_numbers.py` exit 1 | Add the committed raw-data paths to the `<!-- sources: -->` line and put `<!-- derived: -->` on each line carrying a rounded figure. Tested: 20→8 unverified. |
| F-4 | MINOR | FIX-DOC | docs/stage4-run2-conditions.md:179-180; cells/tuned-64K-f9b81a84.json `vram`; cells/stock-64K-22dc1178.json `vram` | Relabel "min free VRAM (after warmup)": the quoted figures are `min_free_mib`, not `after_warmup_min_free_mib`. Not material to eligibility. |
| F-5 | NOTE | FIX-DOC | docs/stage4-run2-conditions.md:60-66; src/smallpc/sweep/records.py:225-231; src/smallpc/sweep/status.py:80-84,107 | Optional one-line note that poll rows are timestamped at poll start and that `sweep-status` counts only complete batches. No numeric error found. |
| F-6 | NOTE | FIX-DOC | .gitignore:8 (`data/logs/*/`); data/logs/jobs/{sweep,rerun}-stage4-run2-*/status.json | None required for T-021 (pre-existing design; the substance is already quoted in the log). Carry to T-013/T-015: the release archive will not contain the job logs behind gate criterion (a). |

### F-1 — the omitted warning, and why it is benign but must be recorded

`data/raw/stage4-run2/events.jsonl` carries one `warning` event, at 14:40:31Z on **tuned-64K**:
`kind: fit_changed_explicit_placement`, `fit_succeeded: false`, `fit_intervened: true`,
`required_reduction_mib: 18`, `offloaded_layers: [42, 42]`, `tensor_overrides_to_cpu: true`.
**No other session has this warning.** `stage3-32K`, `stage3-64K`, `stage3-128K` and run 1
(`stage4`) each have exactly one warning, `code_commit_changed`. The conditions log mentions
warnings only to say run 2 had *no* `code_commit_changed` warning (line 167); the warning it
actually had appears nowhere in the log or the progress-log entry, while A5 claims the log is
complete.

I re-derived the cause and the impact from the committed data:

| session | projected use | CUDA free at launch | headroom | fit result |
|---|---|---|---|---|
| stage3-64K | 14766 MiB | **15803 MiB** | 1037 MiB | succeeded, no change needed |
| stage4 (run 1) | 14766 MiB | **15803 MiB** | 1037 MiB | succeeded, no change needed |
| stage4-run2 | 14766 MiB | **15772 MiB** | 1006 MiB | **18 MiB short of the 1024 MiB target → aborted** |

The server's own log (`startup_excerpt`) says why nothing changed:
`context size set by user to 65536 -> no change` and
`failed to fit params to free device memory: model_params::tensor_buft_overrides already set by
user, abort`. **The launched server is identical**: `argv` byte-identical across all three
sessions, `resolved/tuned-64K.toml` identical, offload 42→42, `props` identical
(`n_ctx_per_slot 65536`, build `b12208-57d04820d`), and run 2's measured VRAM equals run 1's
exactly (`loaded 14934`, `after_warmup_used 15280`, `peak 15292`, `min_free 1019`; Stage 3
differs by 2 MiB). So this is **not** a placement change and **not** a data-validity problem.

Why it is nevertheless MAJOR: the projected usage is unchanged and CUDA-reported free device
memory fell **31 MiB** while `nvidia-smi` `memory.used` before launch went the *other* way
(3 MiB → 2 MiB). That is a driver-level change in reported/reserved device memory, and it is a
concrete, measurable manifestation of the exact confound T-020 flagged for this session
(615.78.08 → 620.70.06). T-008 reads this conditions log as the session's condition record and
must not have to rediscover it from `events.jsonl`.

Required (cheap, doc-only): add the warning, the table above, the two `startup_excerpt` lines and
the argv/config/VRAM identity check to `docs/stage4-run2-conditions.md`, and name it in the
T-008 handoff. **No RE-MEASURE, no RE-ANALYSE of the measurements** — the data stands.

### F-2 — R7: the executor's call was substantively right, but it was the planning chat's to make

The card's `decision_rights.must_escalate` lists "any stop rule firing, **including R7**", and
shared rule 7 says escalate on anything unexpected. At poll 3 the executor saw
`4,8 / 2,8 / 2,8 / 1,8 / 4,8` while a server was running, investigated with a 30-sample burst,
concluded "documented idle downshift", and continued — including into the S4 re-run pass —
without an escalation brief. It labelled the entry "executor judgement, flagged for the
post-review" and named itself as the escalation point. That is transparent, but it is still the
executor taking a decision the card reserves.

**My re-derivation supports the executor's conclusion, on stronger evidence than it had** (see
above): 3,556 sustained-load samples all `4, 8`; all 2,657 samples of the three *measured* cell
instances Gen4 x8; and poll 3's exact sequence reproduced from telemetry showing `util 0.0`
throughout. R7's stop condition was not met on the under-load reading.

**I also found something the executor did not have:** two rows, both in *re-run canary* cells,
where `util > 0` and the link was not Gen4 —

- `canary-rerun-start` 15:01:21.726Z: util **94%**, gen **2**, width 8, power **9.92 W**, P5,
  clock 1012 MHz. The four preceding rows are util 0 with power decaying 75→42→35→24→10 W;
  the next row (0.5 s later) is gen **4**, 28.5 W, P1, 2820 MHz.
- `canary-rerun-end` 15:07:42.999Z: util **26%**, gen **2**, width 8, power **9.77 W**, P5,
  clock 577 MHz; previous row util 0 / gen 2 / 10.12 W; next row gen **4**, 32.6 W, P1.

Both are the idle→load ramp: `utilization.gpu` is a trailing average, so it reads high while
power, clock and P-state still show an idle card, and the link re-negotiates to Gen4 within one
0.5 s sample. Under a **strict** reading of "while a server is generating" (any kernel activity),
these two rows violate R7 and the session should have stopped and escalated. Under the
**under-load** reading they are transition artefacts, like the idle downshifts. Neither reading
touches a measured window: stock-64K and tuned-64K are Gen4 x8 in every row.

This is a rule interpretation with a real consequence — R6 forbids a run 3 without a new
decision — so it is not mine to settle. **DECIDE, options for the planning chat:**

- **Option A — ratify the under-load reading (reviewer recommendation).** R7 applies to sustained
  generation. Run 2 stands as the S2 run; record the ruling as a `docs/decisions.md` line, add the
  telemetry verification and the two ramp rows to the conditions log, and note that the executor
  should have escalated the ambiguity even though its conclusion was correct. T-008 proceeds.
  Cost: one decision line plus a doc edit.
- **Option B — strict reading.** Any kernel activity counts. Then two re-run-canary samples
  violate R7, the executor's continuation was a stop-rule breach, and R6 bars run 3 without a new
  decision. The planning chat would still have to decide whether run 2's S2 data stands with a
  recorded deviation, since every measured-cell sample is Gen4 x8. Cost: a decision, and possibly
  a new gated task — **the reviewer does not order RE-MEASURE**. If a re-measure were ever
  approved, the steps to redo are T-021 S1–S5 (about 45 min gated GPU: 26 min session + 9 min
  re-run + analysis), and R6 requires a fresh decision first.

A5's link clause stays **ESCALATE** until this is ruled on. Note that A5 as written ("the link
read 4, 8 at every sample") is stronger than what the log itself claims ("every
confirmed-generation sample"); whichever option is chosen, the acceptance wording and the
evidence should be brought into line.

### F-3 — number checker: exit 1, and most of it is cheaply fixable

`uv run python tools/check_doc_numbers.py docs/stage4-run2-conditions.md` → **exit 1, 20 of 61
numbers unverified**. The `<!-- sources: -->` line (line 9) names only docs, the runbook, the
spec, `check-quiet.sh` and `pcie-link.md` — not the committed raw data the log actually quotes.
12 of the 20 (148.78, 122.04, 123.36, 124.39, 121.88, 27.93, 28.47, 0.03, 0.84) are literals in
`data/raw/stage4-run2/session.json` and `cells/*.json`.

I tested the fix on a scratch copy (`/tmp/t021-review-check/conditions-fixed.md`, outside the
repo, no repo file touched): adding `session.json` and the six `cells/*.json` to the sources line
takes it to **8 of 56 unverified**. Of those 8, seven are live poll readings that exist in no repo
file (power draw 75.91 / 74.60 / 67.67 / 107.8 W, python CPU 4.7 / 5.8%, swap 39.5 MiB) and one is
`0.00406` at line 170, whose `<!-- derived: -->` marker must sit on line 170, not 171 — the
checker exempts a whole line and the sentence wraps.

For fairness: run 1's accepted log fails the same checker at **45 of 75**, so unverifyable live
readings are an established pattern here, not a T-021 regression. The fixable part is the missing
raw-data sources. Required: add them, put derived markers on the rounded/converted lines, and
state in the log that the remaining poll readings are live observations with no repo source.
T-021's progress-log entry does not mention the number checker at all; T-020's recorded
"exit 0, 31 numbers verified".

### F-4 — VRAM label

Line 179 reads "Lowest min free VRAM (**after warmup**): 1,019 MiB (tuned-64K); stock-64K
1,353 MiB (attempt 1) / 1,355 MiB (attempt 2); canaries 1,329 MiB". Those are `min_free_mib`
(minimum over the whole cell). The `after_warmup_min_free_mib` values are **1031** (tuned),
**1355** (stock a1), 1355 (stock a2), 1329 (canaries). Relabel, or quote both. Not material:
every figure is far above the 512 MiB eligibility floor in runbook §5, and the tuned cell's
window minima (1019–1021 MiB) are consistent.

### F-5 — poll row convention (no error found)

A naive re-derivation flags poll 2: `records.jsonl` already holds 5 `paging` request records by
14:47:51Z (14:46:16…14:47:31) and 69 request rows, yet the log says "still none (64 requests)".
**The log is right.** `records.py:225-231` groups by `batch_id` and drops incomplete batches, so
the stock repetition-2 batch (7 requests, `batch_id e93a808af352`) only becomes visible when its
last request lands at **14:48:37Z** — after poll 2, before poll 3. Emulating the loader reproduces
64 / none, 90 / paging 7 and 118 / 6 exactly. Poll 1's 41 is reached at 14:39:16Z, ~4 s after the
row timestamp, consistent with `check-quiet.sh`'s 10 s CPU window running first. Worth one line in
the log so the next reviewer does not raise a false MAJOR.

## Notes carried to T-008 (not findings against T-021)

- **R5's "reported as an excluded diagnostic" is still outstanding.** Run 1 is marked superseded
  in `docs/decisions.md:1292,1295` and `docs/recon/pcie-link.md:5,123`; `data/raw/stage4/` carries
  no marker, which is correct (append-only, never hand-edited). Reporting run 1 as an excluded
  diagnostic belongs to T-008's Stage 4 analysis, not to T-021.
- T-008's S2 inputs are sound: both cells have 5 clean units, so neither the R1 all-units fallback
  nor an S4(d) deviation is needed. The kernel/driver confound is real and now has a second,
  concrete symptom (F-1's 31 MiB).
- The runbook §6 still shows `--session-id stage4`. The executor correctly left it alone (not in
  T-021's `files_write`); the wording update belongs to T-009/T-010.

## Task verdict

blocked-decision

A1–A4 PASS on my own re-run. The session data is valid and I could re-derive every measurement
claim in the log from the committed raw data; the gate output is byte-identical to my re-run;
run 1 is untouched; the re-run pass was done once and came back clean. Two things stop me from
accepting: **F-1**, a material omission from the evidence document that A5 claims is complete
(cheap FIX-DOC), and **F-2**, an R7 interpretation the card explicitly reserves to the planning
chat, on which A5's link clause depends and which R6 makes consequential. F-2 is a DECIDE finding,
so it goes to the planning chat rather than being worked inline. Nothing here warrants a
re-measurement, and none is ordered.

Suggested sequence: planning chat rules on F-2 (Option A recommended) → executor applies the
F-1/F-3/F-4 doc fixes and records the ruling → re-open review (cycle 2 of 2).

## What I did not verify

- **The executor's chat reasoning** — not available to me and not requested, per protocol.
- **Live, point-in-time pre-start and poll readings that have no committed source**: the
  `check-quiet.sh` process counts (405 / 420 / 421 / 412 / 415 / 410) and its verbatim output
  blocks; the top-5 resident and CPU process names and figures; `nvidia-smi` memory.used 2 MiB
  before the start and after the end; MemAvailable 29,410,316 kB and load 0.27 before the start;
  the poll-time MemAvailable, swap, GPU MiB and pid readings; the 30-sample R7 burst at
  14:56:52–14:57:07Z (its per-sample utilization and power figures are quoted only in the log —
  the burst was not saved as a repo file). I verified the *machine-state* claims that do have a
  committed source: the 7 runner preconditions, the telemetry, and the cell snapshots. The
  poll-3 link sequence is independently confirmed by telemetry; the burst itself is not.
- **"Mains power: yes"** and Zack's "go" at the human gate — recorded in the log, not re-derivable.
- **The pre-re-run gate output as a live re-run.** The session now contains the re-run data, so
  `GATE_CMD` reproduces only the post-re-run block (byte-identical). I checked the pre-re-run
  block for internal consistency instead: 4 cells listed, `drift {'main': None}`, and the
  "0 of 11" denominator recomputed from the window records (5 tuned + 3 canary-start + 3
  canary-end). I did not reconstruct a pre-re-run session directory to re-run it.
- **`model_sha256` against the GGUF on disk** — I confirmed it is identical across Stage 3, run 1
  and run 2, but did not re-hash a ~20 GB model file.
- **`REPRO_CMD` (the S2 check), `REPORT_CMD`, `SCRUB_CMD`, `CI_CMD`** — not run. S2 is T-008's
  step, not a T-021 acceptance item; the release checks belong to T-013/T-015. I only confirmed
  that `repro.py` imposes no session-id validation that would reject `stage4-run2`.
- **Run 1's conditions log and analysis beyond three figures** (38.3 min, 239.4 s and 100.0 s per
  repetition, tuned 3 of 5 paging-flagged). I did not review T-007's or T-020's work.
- **Whether the 31 MiB CUDA free-memory drop is *caused* by the driver upgrade.** I established
  the correlation (same projected usage, same configs, same binary, different driver) and that
  nothing about the launched server changed. I did not test the old driver, and no such test
  should be run without a decision.
- **Docs outside the T-021 diff** — `PLAN.md` (never read whole, per protocol), `PROGRESS.md`
  rendering, and the rest of `docs/decisions.md` beyond the R5–R7 block and the added run-2 line.
- **The `.workflow/` state transition itself** — I read `state.json` for status, review fields and
  cycle counts, and used `wf.sh accept`; I made no other state change before `review-open` /
  `review-verdict`. `.workflow/acceptance/T-021.json` now carries my run-2 record and is the only
  modified file in the tree.
