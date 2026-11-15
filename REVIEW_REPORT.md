# Review T-010 (cycle 1)

## Model

Running as: qwen4-max-preview (same model as the executor; adversarial, read-only review).

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-010` myself (run 2, 2026-11-15T09:05:28Z, HEAD f015f12):
3/3 mechanical PASS, 0 failures, output hashes identical to the executor's run 1
(A2 `37689a87…`, A1/A3 empty-output hash), evidence-file hashes identical
(README `5af8480b…`, report `47cdcf23…`, writeup `5dd9843f…`, CHANGELOG `2f54fb22…`).

| item | verdict | note |
|---|---|---|
| A1 | PASS | Re-ran: no `TODO-T010` in README.md, reports/baseline-report.md, reports/writeup.md. The only remaining repo mentions are historical progress-log entries describing the draft state (append-only history, out of A1's scope). |
| A2 | PASS | Re-ran the checker on all three docs: exit 0, byte-identical output to the executor's run. Extra: also ran it on CHANGELOG.md (not required by A2) — 15 numbers verified, exit 0. Checker scope understood and its blind spots covered manually (see F-1). |
| A3 | PASS | Re-ran: `## v0.1.0 — Step 0 baseline` present. Card S2 content checked: the entry covers the six configs + launch/stop scripts, sweep/analysis tooling, data (incl. run 1 kept superseded), reports, and provenance (b12208 / 57d04820…, model revision + SHA-256, harness pins). |
| A4 | PASS | Judgement re-derived from the evidence, not the executor's report. Detail below. |

### A4 evidence (what was checked, against what)

- **Plan §9 README coverage.** All five §9 README bullets present: what-this-is + hardware
  (`README.md:15-61`), quick start with prerequisites/build/download-verify/launch
  (`README.md:86-170`), rerun on a 12–16 GB machine via `machine.toml` (`README.md:172-226`),
  results with CIs (`README.md:228-320`), limitations and licences (`README.md:322-370`).
  Provenance and exact commands also covered. Non-README §9 items (tag, CI, scrub, write-up
  review, completion report) are correctly stated as pending, not claimed.
- **S2 stated as measured.** `reports/baseline-report.md:591-598` ("S2 is measured … PASS,
  6 of 6 rows"), S5 row "pending T-015/T-016" as the card requires; the clean-shell half of
  S2 is explicitly pending T-012 in all three docs. The S2 tables in README (`README.md:298-305`),
  report (`reports/baseline-report.md:513-520`) and `data/analysis/stage4/s2-summary.md` match
  `data/analysis/stage4/repro-output.txt` **verbatim, row for row** (means, CIs, allowed ranges,
  results, clean-unit sets); `s2-summary.json` `overall: PASS` (precondition re-checked).
  "Two rows inside the CI, four inside ±5%" matches the summary's band analysis; the ±5%
  arithmetic re-derived (e.g. 844.155×0.95 = 801.947, ×1.05 = 886.363).
- **D1–D9, R1–R7 applied correctly.** D1: 128K all-units headline labelled "includes
  paging-flagged stock windows", clean-units figures beside it, S4(d) deviation recorded —
  in all three docs, matching `headline.md:139` and the rendered `reports/stage3/report.md:229`
  (T-009 fix confirmed present, so the README's updated D1 note is accurate). D2: tuned-64K
  paging = known Stage 2a file-page faulting, not investigated, 4/4 re-ran clean; gate 36.4%
  (4 of 11, limit 40%) and A7 denominator 23.5% (4 of 17 = 5 + 4×3) both match
  `docs/progress-log.md:405,438`. D3: 32K swap sensitivity not material, decode gain small /
  not robust (TG 1.157 [0.981, 1.365] / 1.142 [0.999, 1.305] / 1.057 [0.859, 1.300];
  T_turn 0.712 [0.629, 0.807]) — matches `headline.md:67-75`. D7: actual sanity file name
  cited with the deviation note. D8: grep of the four docs finds no account name, hostname
  or home path (only the public licence name ZHarvett, as in LICENSE/LICENSE-DATA.md).
  D9: hit-rate caveats (warm-up + attempt-1 units, decode-batch only, public-code workloads)
  in report §5 and writeup. D4/D5/D6 are tooling/historical and correctly recorded in report
  §7 without touching data. R1 not triggered (5 clean of 5 both cells both days, per
  s2-summary and the run-2 render); R2 not needed; R3 clean tree `c4bdc4d`; R4/R6 no automatic
  re-measure, run 2 the only re-run; R5 run 1 superseded, kept (`reports/stage4/`,
  `data/analysis/stage4-run1-superseded/` exist; its summary reads "FAIL — 5 of 6 rows fail",
  matching the report's "overall FAIL, 5 of 6 rows"); R7 every measured-window sample "4, 8"
  per E-009 clarification, idle/ramp samples recorded not averaged.
- **Numbers attached to the right metric/cell (the checker cannot see this).** Compared in
  full against their named sources: all Stage 3 ratio tables and per-depth tables
  (report §5 vs `headline.md` — every row matches, incl. stock-128K clean vs all-units views);
  README headline min–max rows re-derived from the per-depth ratios (all four rows correct);
  absolute T_turn cell figures; Stage 2 table vs `docs/stage2-summary.md:26-34`; Stage 1
  shortlist vs `reports/stage1/select-screening.md`; VRAM breakdown, hit rates
  (97.0/94.3/93.9 % with hits/misses/copied/uploaded) and the 8-row excluded-diagnostics table
  vs `reports/stage3/report.md:337-385`; run-2 render ratio 0.691 [0.655, 0.730] and spec sha
  `6a11e6b13d8f94de` (runs 1 and 2) vs `reports/stage4-run2/report.md:15,88`; provenance block
  vs `data/env/build-info.json` (tag, commit, date, flags, cmake 4.4.5 / ninja 1.13.2 /
  nvcc V13.4.92 / gcc 16.2.1, binary sha `c6b14a4b…`, v0.9.0 recorded-only, 120a rewrite per
  decisions:105), `configs/model.toml`, `configs/harness.toml` (1.19.5, 0.2.1-rc.5, 295, 643,
  node 26.13.0, npm 12.2.1, lockfile sha), `configs/machine.toml` (127.0.0.1:8080);
  hardware table vs `docs/environment.md` (615.78.08, 180.00 W, 30.46 GiB, zram 30.5G,
  swappiness 150, 7.3.1-1-cachyos, 16,311 MiB, iGPU displays, uv 0.13.7, EXPO 6000 MT/s).
- **Integer claims the checker skips — all verified:** 57 Stage 1 cells; 6/6, 5/5, 4/5 unit
  counts; 14 of 38 + 1 of 38, 15 clean attempt-2; 15 of 75 (2a); 1 of 80 (later Stage 2);
  2f 2-of-5 / 3-of-5 at 8192, 0-of-5 at 2048, 159,451 faults; 47,576 faults / 586 MiB
  (tuned-64K), 22,810 / 4,200 and attempt-1 2,004 (stock-128K:3, decisions:1160),
  5,562 / 2,752 (run-2 stock rep 2); 82 Stage 1 logs at n_threads 8; 8-gram 8 vs reference 2;
  expert-cache 11,520/9,472/8,704 (probed) vs 9,471/8,701 (server-reported) correctly
  distinguished; VRAM peaks/min-free incl. writeup's 14,926–15,290 range.
- **Derived lines re-derived:** (18.4+26.4+45.9+8.2+11.6+17.8)/60 = 2.14 h ≈ 2.1 h
  (per-session figures match progress-log:404-407); (90+38)/60 ≈ 2.1 h; 1−(0.690…0.706) ≈
  30 %; pp 2.304–2.926 → "2.3–2.9×", tg 1.089–1.239 → "1.1–1.2×"; 768/1536 MiB = 0.75/1.5 GiB
  (and the README's "of max-fit expert cache" phrasing is faithful to decisions:1131 — the
  MTP cache reduction is exactly 768/1024/1536 MiB); 15,803−15,772 = 31 MiB.
- **Shared-rule-8 corrections carried:** 1 of 80 (not 100); MTP 2–5 % (4.6 % at 32K draft-2
  excluded, 2.4 % at 64K draft-1), 9–16 % prefill, 0.75–1.5 GiB; Stage 3 ≈ 2.1 h — all present
  and matching decisions:1123-1132.
- **Commands and script claims:** rerun commands match runbook §3 (README's sanity-file name
  correctly uses the actual `stage3-tuned.json` with the D7 note); hf download matches
  decisions WP4 (huggingface_hub 2.4.0, HF_HOME, --local-dir); launch-server.sh health default
  300 s, `/dev/shm/local-ai-research-*` enforcement, GPU lock; stop-server.sh SIGINT→SIGKILL
  default 60 s; run-detached.sh `<name> -- <cmd>` → `data/logs/jobs/<name>-<UTC>/` job.log +
  status.json; run-sweep.sh systemd-inhibit + GPU lock; build script MIN_BUILD=12017, targets
  llama-server/llama-bench/llama-cli, "15–40 minutes" header; runbook 24 GiB expected /
  20 GiB abort; Stage 4 estimate 26/29/44 min (runbook:156); run-1 38.3+13.6 min
  (progress-log T-007); run-2 26.1+9.2 min (conditions:252); "within 1.3 % of selection data"
  (progress-log:412); plan §4 ≈30 GB, §5.5 coverage 95/91–92/88–90 %, §13 batch 2.3–2.9×.
- **Diff scope and freeze.** `git diff 7a7f2b2..HEAD` touches only the four card files plus
  kit state (`.workflow/`, PROGRESS.md via `wf.sh done`). No src/configs/scripts/pyproject/
  uv.lock change (freeze respected). Removed lines in the docs are only TODO placeholders,
  DRAFT banners and section renumbering — **no T-005/T-006 conclusion changed** (the one
  substantive edit, README's D1 note, updates "rendering not yet fixed" → "fixed in T-009",
  which I confirmed in the rendered report). No progress-log entry added (shared-rule-6
  exemption for T-010 respected; T-012 appends it).

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | NOTE | none (recorded for T-013) | tools/check_doc_numbers.py:29,69-70 | The checker guarantees only decimal-token presence somewhere in the union of declared sources; integers (counts, MiB) and whole `derived:` lines are exempt, and metric/cell attachment is not checked. A2's PASS is therefore weaker than "every number is right". This review covered those blind spots manually (above) and found no mismatch. No T-010 action; keep the limitation in mind for the T-013 release checks. |
| F-2 | NOTE | none | reports/writeup.md:89; docs/plans/step-0-baseline.md:225,822 | "Draft length 1 is bit-identical to MTP off" is copied from the plan (§5.4 Stage 2 outcome, §13) — a declared source, so the evidence rule is satisfied. It is not re-derivable from the committed sanity JSONs (they store pass/fail, not outputs). The claim stands as the plan's recorded finding; flagging only so T-014/T-016 know its provenance is the plan text, not a raw-output diff in this repo. |
| F-3 | NOTE | none (optional FIX-DOC) | README.md:55; README.md:316-318 | The hardware table shows the Stage-3-era kernel/driver (7.3.1 / 615.78.08) per `docs/environment.md`; run 2's changed kernel/driver (7.3.4 / 620.70.06) is disclosed in the Reproducibility section and Limitations. No contradiction and nothing claimed beyond the data; a one-line pointer in the table ("Stage 3 inventory; run 2 differs — see Reproducibility") would help skimmers but is not required. |

No BLOCKER, MAJOR or MINOR findings. Executor's acceptance run and my re-run agree exactly.

## Task verdict

accepted

## What I did not verify

- No measurement was re-run (T-010 is light; all acceptance items are cheap and were re-run).
  The frozen analysis/tool outputs (`headline.md`, `repro-output.txt`, rendered reports) were
  accepted as evidence — their underlying raw JSONL/telemetry was verified in T-007/T-008/T-021,
  not re-derived here. In particular I did not re-derive the R7 link samples from
  `data/raw/stage4-run2/telemetry/*.csv.gz` (I read the conditions log and caveats).
- I compared every headline/S2/Stage-1/Stage-2 table and the provenance block in full, and
  spot-checked prose numbers; I did not manually re-attach every one of the ~hundreds of
  decimal tokens in the three docs beyond the checker's token-presence guarantee (F-1).
- The "bit-identical" draft-1 claim was traced to the plan, not re-derived from raw outputs (F-2).
- The WP10 interval-coverage simulation figures were read from plan §5.5, not re-simulated.
- CHANGELOG work-package history was spot-checked (WP9/WP11/WP12/WP13 claims against the
  progress log and decisions), not audited line-by-line against all 668 progress-log lines.
- Figures/SVGs were not reviewed (T-009 scope, reviewed there); full CI was not re-run
  (T-009 acceptance, 5× green); the clean-shell walkthrough is T-012, pending by design.
- I did not read the executor's chat reasoning (not available to me, per protocol).
