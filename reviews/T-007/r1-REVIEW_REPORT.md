# Review T-007 (cycle 1)

## Model

qwen4-max-preview (the config records a single model for executor and reviewer).

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-007` myself (run 2, 2026-11-13T23:48:48Z, at HEAD `e6c33be`):
A1–A4 PASS with output hashes identical to run 1; A5 judgement assessed below. No gpu or
exclusive-machine task is in progress and no machine lock is held, so nothing was DEFERRED —
every acceptance command is light analysis (no GPU).

| item | verdict | note |
|---|---|---|
| A1 | PASS | `docs/recon/stage4-session.txt` non-empty: `stage4` + newline, 6 bytes, sha256 `f0a2f992de07…` — identical to run 1. |
| A2 | PASS | `COVERAGE_CMD` exit 0; output byte-identical to run 1 (sha `1bdc8ec3…`, 574 bytes). Caveat: this is the generic WP10/WP11 interval-coverage simulation, not a stage4-specific check — see F-3. |
| A3 | PASS | Re-ran `GATE_CMD` myself: `gate for stage3 session stage4: PASS`, a–f all PASS, exit 0. Output matches the conditions log's post-rerun block verbatim (f: 3 of 17 attempt-1 tuned+canary windows = 17.6%, limit 40%; no flagged window >1024 MiB swap growth; stock 0 of 5 reported). No `- R2 applied: Stage 4` line in `docs/decisions.md` — the gate passed outright (the only "R2" match is the rule definition at line 1210). |
| A4 | PASS | `git status --porcelain -- data` empty; `pgrep -x llama-server` empty; GPU lock free (`flock -n .locks/gpu.lock` succeeded). |
| A5 | PASS | Judgement, re-derived from evidence: **(1) Clean start at an R3-passing commit** — `session.json` git: commit `1307244870bf…`, `dirty: false`, `dirty_paths: []`, `allow_dirty: false`; `git show --stat 1307244` touches only the two conditions docs + kit bookkeeping; the R3 check re-run at `1307244` and at HEAD both PASS; zero changes under `src/ configs/ scripts/ pyproject.toml uv.lock tests/` in `33c9231..HEAD`. **(2) Runbook followed** — spec check re-run (2 cells, 5 repetitions, canary true, `total_h 0.58`); `run-sweep.sh` detaches via `run-detached.sh --gpu` under the GPU lock + `systemd-inhibit` (job `status.json` command lines confirm both jobs); gate → exactly one `--rerun-flagged` pass (`session.json` runs: run + rerun; `rerun_plan` tuned-64K [0,2,4]) → gate again → commit, per §6. The rerun's `code_commit_changed` warning (1307244→2179877) matches established Stage 3 practice (all three Stage 3 reruns carry the identical warning). Human gate released on Zack's "go" 22:40:34Z; date condition met (13 Nov 22:42 UTC / 14 Nov local). **(3) Quiet at start and every poll** — pre-start, pre-launch, 5 session polls, pre-rerun and 2 rerun polls recorded verbatim with exit 0; poll timestamps align with the `events.jsonl` cell timeline; cadence ~7–8 min (card's sleep 420). **(4) Re-run done** — 3 units, attempt 2, all clean (0 major faults each; swap 0/0/50 MiB), resolved 3 / still flagged 0; re-run canaries 6/6 clean; tuned-64K ends with 5 clean units (my S2 evidence run confirms both cells evaluated on clean units, R1 fallback not needed). **(5) Conditions log complete** per the stage3 template; every numeric claim checked re-derives (below). |

Numbers re-derived from raw data (all match the conditions log and progress entry): 21 paging
flags = 3 windows × 7 requests, tuned-64K attempt 1 reps 0/2/4 (`records.jsonl`); flagged-window
max swap growth 219.65→220 MiB and max major faults 6,751 (`cells/tuned-64K-f9b81a84.json`
`windows[].paging`); stock 0/5 flagged, max 41 faults; canary-start max 383 faults; attempt-2
windows 0 faults, swap 0/0/50 MiB; measure times stock 1197.08 s, tuned a1 499.88 s, a2 295.82 s,
canaries 167.23/167.88 s; after-warmup min free VRAM 1031/1355/1329 MiB; cell preconditions
26.48/27.62/27.71/27.77 GiB, all `ok: true`, 0 s idle waits; drift main `pp_fresh_16k` rel diff
0.00046 (<0.05), rerun no flag; durations 38.3 min (22:42:12→23:20:30Z) and 13.6 min rerun
(23:23:46→23:37:19Z); both job `status.json` exit 0 / done; gate denominators 3/11 = 27.3%
pre-rerun, 3/17 = 17.6% post-rerun; resolved configs equal the committed server configs plus the
spec's `--metrics -lv 4` (stock keeps llama.cpp defaults incl. `--cache-ram 8192`); all kB→GiB
conversions in the log correct; `scrub --check data/raw/stage4`: 0 findings in 25 files.

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | MAJOR | RE-ANALYSE | `data/raw/stage4/session.json` (drift) vs `data/raw/stage3-64K/session.json`; `data/raw/*/telemetry/*.csv.gz` (`pcie_gen`); `nvidia-smi --query-gpu=pcie.link.gen.max` | **Between-day machine-state change — not a T-007 protocol violation, but it breaks reproducibility.** The PCIe link trained at **Gen4 x8 in all three Stage 3 sessions but Gen3 x8 throughout Stage 4** (telemetry counts: stage3-32K/64K/128K dominated by 4.0; stage4 5,718 samples at 3.0, none at 4.0; the GPU now reports `pcie.link.gen.max=3`). Canary fresh prefill fell **945.26 → 575.56 tok/s (−39%)** while canary decode was ~unchanged (78.83→78.35, 89.70→88.27); config hash, model sha256 and llama.cpp commit are identical across days. Measure times vs Stage 3 actuals: stock 760.32→1197.08 s (+57%), tuned 377.08→499.88 s (+33%). I ran `REPRO_CMD` as read-only review evidence: **S2 FAILS 5 of 6 rows** — stock T_turn_400 9.288→11.797 s, stock fresh-prefill-32K 844.2→505.9 tok/s, tuned T_turn_400 6.413→8.050 s, tuned fresh-prefill-32K 2024.9→1481.1 tok/s, tuned decode-32K 91.64→76.48 tok/s; stock decode-32K PASS (73.88→73.39); both cells on clean units; exit 1. No T-007 stop rule covers link state (the drift gate is within-session; quiet/MemAvailable/GPU-process checks all passed), and the card deliberately defers S2 to T-008. **T-008 must run S2 officially, report it, and escalate per R4 — never auto-re-measure.** The escalation brief should carry this PCIe evidence so the planning chat can DECIDE: (a) restore the Gen4 link (BIOS/kernel setting — Zack's hands, no sudo by Claude) and re-measure Stage 4 as a new gated task via approved escalation, or (b) accept a recorded reproducibility deviation with cause. The reviewer does not order RE-MEASURE. |
| F-2 | MINOR | FIX-DOC | `docs/stage4-conditions.md:82-85` | The pace note compares only to the Stage 1/2 *estimate inputs* (153.3 / 75.5 s per repetition) and attributes the overrun mainly to stock; it does not record the between-day canary prefill drop (945.26→575.56 tok/s) or the PCIe Gen4→Gen3 change, and tuned is also +33% vs the Stage 3 *actual*. Append a clearly-marked post-session review observation with these numbers and telemetry pointers (or carry them in T-008's analysis). No change to any recorded measurement; `data/raw/` untouched. |
| F-3 | NOTE | NONE | `docs/recon/commands.env` (`COVERAGE_CMD`); `.workflow/acceptance/T-007.json` A2 | A2's `COVERAGE_CMD` is the generic interval-coverage simulation (20,000 experiments, 1,000 resamples, seed 1) and ignores `$SESSION`; it passes as the card specifies but is not evidence about Stage 4's intervals. Card-defined; no executor action. |
| F-4 | NOTE | NONE | `.gitignore:8` (`data/logs/*/`); conditions-log citations of job `status.json` | The job logs (`data/logs/jobs/sweep-stage4-20261113T224212Z/`, `rerun-stage4-20261113T232346Z/`) are gitignored, so gate criterion a's job-exit evidence is local-only — consistent with Stage 3 practice, and the gate re-derives it at run time. Recorded so the release checks know the repo alone cannot re-derive criterion a after a machine wipe. |

## Task verdict

accepted

All five acceptance items hold on re-derivation: the session ran detached from a clean,
R3-passing committed tree, the runbook was followed command-for-command, quiet held at the
start and every poll, exactly one re-run pass resolved all 3 flagged units clean, both gates
passed a–f, and the conditions log is complete and numerically faithful to the raw data. The
executor's report and my re-run agree everywhere. F-1 is a real, material problem for the
*project* (Stage 4 does not reproduce Stage 3, and the PCIe link downgrade is the leading
candidate cause), but it is not a defect in T-007's work: the card assigns S2 to T-008 and R4
prescribes report-and-escalate on failure. T-008 should not start its analysis assuming S2 will
pass — my evidence run shows it fails 5 of 6 rows.

Kit bookkeeping note: this review left `.workflow/acceptance/T-007.json` (run 2),
`REVIEW_REPORT.md`, `reviews/T-007/r1-REVIEW_REPORT.md` and the wf state changes in the working
tree; per established practice (e.g. commit `33c9231`) the next session commits them.

## What I did not verify

- Historical quiet-check outputs and poll samples (process counts, MemAvailable, GPU memory,
  CPU busy at poll times): taken from the conditions log as recorded. They are internally
  consistent and align with the `events.jsonl` timeline, but are not re-derivable after the fact.
- The pre-rerun gate output (the "3 of 11" block): checked for internal consistency (correct
  denominator, drift main-only, no rerun canaries listed) and against the commit history, but
  not re-run against the historical tree at `2179877` — the job logs are untracked, so criterion
  a could not be re-derived there.
- The cause of the PCIe Gen4→Gen3 change (BIOS setting, kernel update, ASPM): outside the repo;
  not investigated. The link–prefill correlation is evidence, not a proven causal chain. Note
  also that tuned decode at 32K depth fell 16.5% while the canary `tg_16k` fell only 0.6% —
  T-008's analysis should look at that asymmetry (MTP interaction is one candidate).
- The executor's chat reasoning: not available to me, and not requested (protocol).
- `CI_CMD`, report render, headline: not T-007 acceptance items; not run.
- The S2 table quoted in F-1 is my read-only evidence run, not T-008's official recorded run;
  T-008 must re-run and record it.
