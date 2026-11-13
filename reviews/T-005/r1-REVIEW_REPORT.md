# Review T-005 (cycle 1)

## Model

Running as: qwen4-max-preview (the config records a single model for executor and
reviewer; this review is adversarial re-derivation, not a rubber stamp).

Session note: `wf-guard.sh` failed with the single line "T-017 is in the main state as
ready AND in lane 3". Per decision E-005's standing interim exception (verified in
`docs/decisions.md:1236-1242`) and Zack's instruction, the line was treated as non-fatal:
it matches the exact prescribed form and `wf.sh status` shows T-017 `in-progress` in
lane 3. No state was repaired; `merge-lanes` was not run.

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-005` myself (run 2, appended to
`.workflow/acceptance/T-005.json`, at HEAD `6761913`, failures: 0). Both evidence files'
SHA-256 in the current tree match the recorded evidence hashes exactly
(`reports/baseline-report.md` 78c8d07d…, `tools/check_doc_numbers.py` fdb85c29…).

| item | verdict | note |
|---|---|---|
| A1 | PASS | Checker exit 0: "745 numbers verified, 37 sources" — matches the commit message's claim. Output sha256 identical to the executor's run 1 (3c7bafd1…). |
| A2 | PASS | 22 tests pass (matches the commit's "22 tests"). Output sha256 differs from run 1 (2f4168… vs 79285b…) with identical byte count (99): `pytest -q` prints its elapsed time, which varies between runs. Not a discrepancy. |
| A3 | PASS | `ruff check` + `ruff format --check` clean on both new files; output sha256 identical to run 1. |
| A4 | PASS | "includes paging-flagged stock windows" present; "stage3-tuned.json" present; "not reportable" absent (D1: the rendered stage3 report's wording is not carried over). Output hash identical (empty output). |
| A5 | PASS (judgement) | Re-derived by hand; basis below. |

### A5 basis — what was re-derived, and against what

The checker only proves a decimal token appears *somewhere* in a declared source file;
it cannot prove attribution. I therefore checked every table line-by-line against its
named source, plus the fenced and integer content the checker skips by design:

- **Stage 3 headline** (`data/analysis/stage3/headline.md`, authoritative per D1):
  summary table (0.705 [0.672, 0.739] / 0.690 [0.649, 0.734] / 0.706 [0.679, 0.735]);
  all three per-context ratio tables (11 metrics each); the 128K clean-units table
  (n=4, 0.711 [0.673, 0.750]); all six per-depth tables (stock/tuned × 3 contexts,
  including the stock-128K clean and all-units views); cell figures; eligibility lines
  (min free VRAM 1,379 / 1,021 / 1,211 MiB, sanity pass); swap-sensitivity figures
  (0.712 [0.629, 0.807], tg@24576 1.057 [0.859, 1.300], removed units 231/115/145 MiB).
  Every value matches. The §5.4 headline rule is quoted verbatim (headline.md:234).
  The "versions agree in sign and 1.0-exclusion" claim was independently confirmed
  against both 128K tables. The summary's derived ranges (pp 2.304–2.926, tg
  1.089–1.239) re-derived from the ratio tables: correct.
- **VRAM breakdown, hit rates, excluded diagnostics** (`reports/stage3/report.md`):
  all 6 VRAM rows × 10 columns, all 3 hit-rate rows (97.0 / 94.3 / 93.9 % with hits,
  misses, copied, uploaded), and all 8 excluded-diagnostic rows match exactly.
- **Paging and gate** (`docs/decisions.md` WP13 part 2, E-001): 4-of-5 tuned-64K
  attempt-1 flags, 47,576 faults / 586 MiB; stock-128K:3 attempt 2 22,810 faults /
  4,200 MiB, attempt 1 2,004; gate 36.4 % (4 of 11, limit 40 %) quoted together with
  E-001's A7 sentence (17 attempt-1 windows, 23.5 %, true pass under both) — exactly
  as E-001 rule (3) requires. 4/11 and 4/17 arithmetic checked.
- **Stage 1** (`reports/stage1/select-screening.md`): all 9 shortlist rows and the
  "too close to call" notes match; 57 cells is the plan's declared expansion
  (plan:601); "14 of 38 / 1 of 38 / 15 attempt-2 clean" is verbatim from
  `docs/decisions.md:830-831` and consistent with `reports/stage1/diagnostics.md:35`.
- **Stage 2** (`docs/stage2-summary.md`): config and results tables match exactly
  (5.916 / 6.486 / 7.967 s with CIs, PP/TG, min free VRAM, MTP acceptance 0.771).
  WP13 corrections verified against `docs/decisions.md:1123-1131`: 1 of 80 (window
  identity `s2b-P6-64K-b4096-mtp1-kvf16` rep 2; 15+15+20+10+10+10 = 80), 2a 15 of 75,
  MTP 2–5 % (4.6 % / 2.4 %), 9–16 % prefill (ratios 0.838–0.910), 0.75–1.5 GiB
  (768/1,536 MiB; derived markers arithmetically correct). Stage 3 "about 2.1 hours"
  = (90+38)/60 per shared rule 8, marked derived.
- **Sanity** (`data/sanity/stage3-tuned.json`): three tuned cells pass, no failed
  prompts, resolved from `configs/server/tuned-*.toml`; three P1 reference cells pass.
  D7 file name applied.
- **Provenance**: the fenced identifier block (checker-skipped) verified field by
  field against `data/env/build-info.json` (b12208, 57d04820…, llama-server sha256,
  v0.9.0 recorded-only, 120→120a per decisions.md:105, built 2026-11-08),
  `configs/model.toml` (revision f6045267…, LFS sha256 42739874…, 21,713,463,040
  bytes, base repo 10fbf86f…, MIT, 7828 vs 7536 template bytes, 2026-08-23 MTP
  weights requirement per decisions.md:10), `configs/harness.toml` (1.19.5,
  0.2.1-rc.5, 295 plugins, node 26.13.0, npm 12.2.1, 643 checked / 0 too new,
  lockfile d21af6e8…), `headline.md` provenance (session commits 80964618df /
  a80b2dd31a / b5b7396231, spec sha 41a0e384d622fcb2) and
  `docs/recon/stage3-commit.txt` (80964618df… → "8096461", E-001 one code state).
  Machine facts (9700X 8c/16t, 32 GB, SK hynix 256 GB, btrfs zstd:1, monitors on
  iGPU, frozen tuning) match `docs/environment.md`, `configs/machine.toml` and the
  plan (§4 line 101; "32 GB" at plan:203/226/735/825).
- **Method pointers** (plan): 3,000+400 turn (§3.4), T_turn_400 estimate vs T_B with
  predicted_n, 10,000 resamples / wider-of CI (§5.5:249), 64 MiB swap threshold
  (§5.5:252), 1,000-fault paging flag (§5.6:260), all eight flag names, K = 1,024,
  G3 apps-open deviation (§7:658), idle-CPU precondition (§5.3:138), no hard speed
  targets (§2:35), S1–S5 names and content (§2:39-43). Workload identities
  (poetry, axum) trace to `docs/decisions.md:336` and `configs/workloads/recipe.toml`.
- **Decisions applied**: D1 (label, clean figures beside, S4(d) recorded), D3 (exact
  wording and numbers), D7 (file name), D9 (warm-up + attempt-1 caveat, decode-batch
  only). S2/S5 carry `<!-- TODO-T010 -->`. Stages 1–2 labelled selection data,
  apps-open. Every table section carries a `sources:` comment; all 37 declared
  sources exist (the checker opens them all).
- **Privacy (D8)**: no account name, home path or hostname in the report
  (case-insensitive grep: no matches).
- **Discipline**: work commit `6ffe27c` touches exactly the card's three files
  (855 insertions, all new); no frozen file (src/, configs/, scripts/, pyproject.toml,
  uv.lock) changed between `6ffe27c^` and HEAD; no progress-log entry (shared rule 6
  exempted T-005); the done commit `4bc967c` touches only kit state. Card precondition
  (headline.md exists) holds. The rendered stage3 report's "No eligible candidate" /
  "not reportable" wording predates the sanity re-run; D1 makes headline.md
  authoritative and the report states this explicitly — a documented relationship,
  not an unescalated disagreement.

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | NOTE | FIX-DOC (optional, T-010) | reports/baseline-report.md:362; data/analysis/stage3/headline.md:181 | The stock-128K **all-units** per-depth header says "n_clean 5, n_total 5", faithfully copied from headline.md, while the same section correctly states 4 clean units (lines 318, 355). The label is the authoritative source's own (in the all-units view it counts units in the view). No number is wrong. T-010 may add a clarifying parenthetical; no T-005 action. |
| F-2 | NOTE | FIX-DOC (optional, T-010) | reports/baseline-report.md:159-160 vs 407-409; docs/stage2-summary.md:12-13; reports/stage3/report.md:229,238 | Expert-cache sizes differ between tables: 9,472 / 8,704 MiB (Stage 2, probed) vs 9,471 / 8,701 MiB (Stage 3, server-reported). Both are faithful to their named sources and the VRAM section says "the size the server reports", but the 1–3 MiB difference is not explicitly reconciled. Optional one-line note at T-010. |
| F-3 | NOTE | none | tools/check_doc_numbers.py:26-29 | Checker boundaries, per the card's own S1 design: integers and fenced numbers are not checked, and source matching is whole-file (no per-table attribution). This review manually verified the fenced provenance block and every integer claim found (57, 643, 295, 7828/7536, 14/38, 1/38, 15/15, 1/80, 15/75, 32 GB, 8c/16t, dates). Recorded so T-010 knows what the tool does not guarantee. |
| F-4 | NOTE | none | reports/baseline-report.md:37; data/analysis/stage3/headline.md:22 | Summary's "decode roughly 1.1–1.2× faster" is a point-estimate range; tg@24K at 32K has CI [0.996, 1.190] (includes 1.0) and D3 calls that gain not robust — properly caveated in §5 (32K) and §6. The summary's CI-backed claim is about T_turn_400, whose intervals all exclude 1.0. No action; T-010 may add "(point estimates)". |

No BLOCKER, MAJOR or MINOR findings. The executor's report and my re-run agree on
every mechanical item; no evidence file contradicts its acceptance claim; no
hand-written-looking artifact (all hashes match, all tables trace to machine-generated
sources, derived markers carry correct arithmetic).

## Task verdict

accepted

## What I did not verify

- **No measurement or re-analysis was run.** T-005 is a light writing task; I verified
  the report against the committed analysis outputs (headline.md, rendered stage3
  report, sanity JSON, stage2-summary, select-screening), not against `data/raw/`
  JSONL. The analysis chain that produced those outputs was accepted in earlier
  tasks; I did not re-derive bootstrap/t CIs or recompute statistics from raw data.
- **The executor's chat reasoning** — not available to the reviewer, not requested.
- **Other tasks' work** (T-004, the kit install, Stage 3 sessions themselves) — only
  T-005's diff and the sources it cites were in scope.
- **Checker robustness beyond its 22 tests and my reading** — no fuzzing or hostile
  inputs; the tests cover the spec's cases (fences, tildes, info strings, derived
  lines, comments, separators both directions, exit codes) and all pass.
- **Future integer drift** — the checker does not check integers by design; I verified
  the ones present today, but a later edit could introduce an unchecked integer.
- **Figures** — the baseline report embeds none; the rendered stage3 report's SVG
  figures (D9 axis fixes) are T-009's scope and were not reviewed.
- **Working tree state** — carries exactly one kit-written modification,
  `.workflow/acceptance/T-005.json` (run 2 appended by my own mandated `wf.sh accept`
  re-run); nothing else is modified. No state was hand-edited; no lane merge performed.
