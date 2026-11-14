# Review T-005 (cycle 2)

## Model

Running as: qwen4-max-preview (the config records a single model for executor and
reviewer; this review is adversarial re-derivation, not a rubber stamp).

Session note: `wf-guard.sh` passed cleanly ("guard: OK"); no GPU or machine lock held,
no measurement session running, tree clean at HEAD `a90942e`. T-021 sits in
blocked-decision (E-009) and does not block this light review. Cycle 1
(`reviews/T-005/r1-REVIEW_REPORT.md`, accepted 13 Nov) predates the plan v1.5 re-import,
which reset T-005's status to `done`; `review_cycles` still records 1, so this is cycle 2
— the last permitted (`max_review_cycles = 2`). A further review would need an escalation.
Nothing in cycle 1 was taken on trust: every claim below was re-derived from the committed
files, and the per-section attribution check is new in this cycle.

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-005` myself (run 3, appended to
`.workflow/acceptance/T-005.json`, at HEAD `a90942e`, failures: 0). Both evidence files'
current SHA-256 match the recorded evidence exactly (`reports/baseline-report.md`
78c8d07d…, `tools/check_doc_numbers.py` fdb85c29…); `git log 6ffe27c..HEAD` on the three
card files is empty — the artifacts are byte-identical to the work commit.

| item | verdict | note |
|---|---|---|
| A1 | PASS | Checker exit 0: "745 numbers verified, 37 sources" — matches the commit message and cycle 1. Output sha256 identical to runs 1–2 (3c7bafd1…, 80 bytes). Non-vacuity proven by six mutation tests (below). |
| A2 | PASS | `22 passed in 0.02s` — 22 tests, counted in the file and re-run. Output sha256 2f4168c9… equals run 2; run 1 differed only in pytest's elapsed-time string (99 bytes both). Not a discrepancy. |
| A3 | PASS | `ruff check` + `ruff format --check` clean on both new files; output sha256 identical to runs 1–2 (afa20b27…). |
| A4 | PASS | "includes paging-flagged stock windows" present (lines 28, 316); "stage3-tuned.json" present (lines 467, 494); "not reportable" absent — that wording lives only in the rendered report's appendix (reports/stage3/report.md:279), which D1 subordinates to headline.md. Empty-output hash e3b0c442… identical. |
| A5 | PASS (judgement) | Re-derived by hand and by script; basis below. One MINOR attribution gap (F-1) and four NOTEs; no number is wrong and no claim exceeds the data. |

### Checker non-vacuity (mutation tests, copies in /tmp/t005-review, repo untouched)

1. `0.705 → 0.707` on line 26 → exit 1, `m1.md:26: 0.707 not found in sources`.
2. Same mutation + `<!-- derived: … -->` on that line → exit 0 (line exempt, 745→742).
3. All `sources:` lines stripped → exit 2 ("decimal numbers present but no sources line").
4. Bogus `9.999` inside the fenced provenance block → exit 0 (fences skipped, by design).
5. `57 cells → 58 cells` → exit 0 (integers unchecked, by design — see F-3).
6. Bogus `1,379.5` → exit 1 (separator normalization works both directions).

### A5 basis — what was re-derived, and against what

The checker proves a decimal token appears *somewhere* in a declared source; it cannot
prove attribution. I therefore (a) compared every table line-by-line against its named
source, and (b) ran a per-section script checking all 642 decimal tokens in table rows
against *their own section's* declared sources: 641 attributed, 1 gap (F-1).

- **Stage 3 headline** (`data/analysis/stage3/headline.md`, authoritative per D1):
  summary table (0.705 [0.672, 0.739] / 0.690 [0.649, 0.734] / 0.706 [0.679, 0.735]);
  all three 11-metric ratio tables; the 128K clean-units table (n=4, 0.711 [0.673, 0.750]);
  all six per-depth tables (stock/tuned × 3 contexts, including both stock-128K views);
  cell figures; eligibility lines (min free VRAM 1,379 / 1,021 / 1,211 MiB, sanity pass);
  swap-sensitivity figures (0.712 [0.629, 0.807], tg@24576 1.057 [0.859, 1.300], removed
  units 231/115/145 MiB). Every value matches. The §5.4 headline rule is quoted verbatim
  (headline.md:234). "Versions agree in sign and 1.0-exclusion" confirmed against both
  128K tables. Summary's derived ranges re-computed from the ratio tables: pp min 2.304
  (64K@48K) max 2.926 (128K@32K); tg min 1.089 (32K@24K) max 1.239 (64K@32K) — correct.
- **VRAM, hit rates, excluded diagnostics** (`reports/stage3/report.md`): all 6 VRAM rows
  × 10 columns (219–238), all 3 hit-rate rows (248–250: 97.0 / 94.3 / 93.9 % with hits,
  misses, copied, uploaded), all 8 excluded-diagnostic rows (260–267) match exactly.
- **Paging and gate** (`docs/decisions.md` WP13 part 2:1160–1164, E-001:1176, D2:1200):
  tuned-64K 4-of-5 attempt-1 flags, 47,576 faults / 586 MiB; stock-64K none; 32K/128K
  stock paged 1 and 2 windows, tuned none; four tuned units re-ran clean (0 faults);
  stock-128K:3 attempt 2 22,810 faults / 4,200 MiB, attempt 1 2,004. Gate 36.4 % (4 of 11,
  limit 40 %) quoted together with E-001's A7 sentence (17 attempt-1 windows = 5 + 4×3,
  23.5 %, true pass under both) — exactly as E-001 rule (3) requires. 4/11 = 36.36 %,
  4/17 = 23.53 %: arithmetic checked. The excluded-table's flag pattern (stock-32K rep 3;
  stock-128K reps 1, 3; tuned-64K reps 1–4) independently corroborates the 1/2/4 counts.
- **Stage 1** (`reports/stage1/select-screening.md`): all 9 shortlist rows, ranks, CIs and
  "too close to call" notes match (the 64K too-close pair is P9/P5, correctly *not* the
  shortlist pair); "stock never shortlisted" matches. 57 cells is the plan's declared
  expansion (plan:189, 601). "14 of 38 / 1 of 38 / 15 attempt-2 clean, repetition 1"
  verbatim from decisions.md:829–831, consistent with diagnostics.md §E ("15 of 15
  attempt-2 units are clean (1 at 64K, 14 at 128K)").
- **Stage 2** (`docs/stage2-summary.md`): config and results tables match exactly
  (5.916 / 6.486 / 7.967 s with CIs, PP/TG, min free VRAM 1,379/1,019/1,211, MTP 0.771,
  middle depths 16,384/32,768/65,536). WP13 corrections verified against
  decisions.md:1123–1131: 1 of 80 (15+15+20+10+10+10; window `s2b-P6-64K-b4096-mtp1-kvf16`
  rep 2), 2a 15 of 75, MTP 2–5 % (4.6 % / 2.4 %), 9–16 % prefill (ratios 0.838–0.910),
  0.75–1.5 GiB (768/1,536 MiB; derived marker at line 173 arithmetically correct).
  "About 2.1 hours" = (90+38)/60 per shared rule 8, marked derived. 2f rule and stock
  default 8192 match decisions.md:838–840 and headline.md:232.
- **Sanity** (`data/sanity/stage3-tuned.json`): three tuned cells pass, `failed_prompts`
  empty, resolved from `configs/server/tuned-*.toml`; three P1 reference cells pass.
  D7 file name applied, runbook's `stage3-all.json` named as the deviation.
- **Provenance** (fenced block, checker-skipped — verified field by field):
  `data/env/build-info.json` (b12208, 57d04820…, llama-server sha256 c6b14a4b…, v0.9.0
  recorded-only, CUDA arch 120, Release, built 2026-11-08); 120→120a per decisions.md:105;
  `configs/model.toml` (revision f6045267… 2026-08-24, LFS sha256 42739874…,
  21,713,463,040 bytes, base repo 10fbf86f…, MIT, 7828 vs 7536 template bytes, embedded
  template per WP5); 2026-08-23 MTP-weights requirement per decisions.md:10;
  `configs/harness.toml` (1.19.5, 0.2.1-rc.5, 295 plugins, node 26.13.0, npm 12.2.1,
  643 checked / 0 too new, 7-day rule, lockfile d21af6e8…); headline.md:219–221 (session
  commits 80964618df / a80b2dd31a / b5b7396231, spec sha 41a0e384d622fcb2);
  `docs/recon/stage3-commit.txt` (80964618df… → "8096461", E-001 one code state).
  Machine facts (9700X 8c/16t, 32 GB, SK hynix 256 GB, btrfs zstd:1, monitors on iGPU,
  no display clients, frozen tuning) match docs/environment.md:36,52,83,113,132,284,
  configs/machine.toml [bios] and plan §4:101 / §5.7:274.
- **Method pointers** (plan, all re-checked): no hard speed targets (§2:35); S1–S5 names
  and content (§2:39–43, incl. S2's different-day + clean-shell wording and S4(d));
  3,000+400 turn (§3.4:82); T_turn_400 estimate vs T_B with predicted_n (:752); K = 1,024,
  96K = 98,304 (§5.2:122); per-cell idle-CPU gate (§5.3:131–138); 10,000 resamples /
  wider-of CI (§5.5:249); 64 MiB swap threshold (§5.5:252); 1,000-fault paging flag and
  all eight flag names (§5.6:259–266); G3 apps-open deviation (§7:658); P2 = `--fit
  --fit-target 256`, P6 = `-cmoe --moe-cache-mib` (:184, :186). Workloads poetry/axum
  trace to decisions.md:336.
- **Decisions applied**: D1 (label, clean figures beside, S4(d) recorded, headline.md
  authoritative over the rendered report — stated at lines 209–211), D2 (known file-page
  faulting, not investigated, both denominators), D3 (exact wording and numbers), D7
  (file name), D9 (warm-up + attempt-1 caveat, decode-batch only); D4/D5 carried as
  tooling notes. S2/S5 carry `<!-- TODO-T010 -->`. Stages 1–2 labelled selection data,
  apps open. All 37 declared sources exist and are readable (checker exit 0 proves it).
- **Privacy (D8)**: case-insensitive greps for <account-name>, `/home/`, the hostname and
  the author surname: 0 matches in the report.
- **Discipline**: work commit `6ffe27c` touches exactly the card's three files (855
  insertions, all new); done commit `4bc967c` touches only kit state; no progress-log
  entry (shared rule 6 exempts T-005; T-006 appended it at `e315ff5`); precondition
  (headline.md exists) holds; no frozen file touched by T-005.
- **Source drift since the work commit**: none under data/analysis/stage3, reports/,
  data/sanity, configs or data/env (empty diff); `docs/decisions.md` changed purely
  additively (0 deleted lines — E-004…E-009, R5–R7 appended; every cited passage intact);
  `docs/plans/step-0-baseline.md` unchanged. The report's numbers are current.

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | MINOR | FIX-DOC | reports/baseline-report.md:512,523; data/analysis/stage3/headline.md:123; docs/stage2-summary.md:29 | The §7 (S1–S5) table's sources comment names only the plan, but the S4 row's MTP acceptance 0.771 is not in the plan — it comes from headline.md:123 / stage2-summary.md:29 (both named elsewhere in the doc; the value is correct). This makes §8's claim "Every table … naming the file(s) its numbers come from" (line 528) overstated for this one table, and the global checker passes the token only via other sections' sources. Fix: add `data/analysis/stage3/headline.md` to the sources comment at line 512. One line; owner T-010 (finalises this report) or immediately via /address-review. Does not block acceptance: no number is wrong and document-level traceability holds. |
| F-2 | NOTE | FIX-DOC | reports/baseline-report.md:507; docs/decisions.md:949,1123–1131 | The restated corrections "0.75 to 1.5 GiB" on line 507 carry no line-level derived marker (rule 1); the checker passes them by coincidental whole-file matches — "1.5" inside the model name Ornith-1.5 and "-0.75 %" at decisions.md:949, neither of which is the derivation. The values are correct (WP13 item 3: 768/1,536 MiB; shared rule 8 mandates this wording) and the derivation is properly marked at line 173. Optional at T-010: add `<!-- derived: 768 MiB = 0.75 GiB, 1,536 MiB = 1.5 GiB; WP13 item 3 -->` on line 507. |
| F-3 | NOTE | NONE | tools/check_doc_numbers.py:26-29,78-88; mutation tests 4–5 | Checker boundaries, per the card's S1 design and confirmed by mutation: integers and fenced numbers are unchecked; source matching is whole-file, not per-table. This review manually verified the fenced provenance block and the integer claims (57, 643, 295, 7828/7536, 14/38, 1/38, 15, 1/80, 15/75, 4/11, 4/17, 32 GB, 8c/16t, 2048/8192/4096, K=1024, 98,304, dates). Recorded so T-009/T-010 know what the tool does not guarantee. |
| F-4 | NOTE | NONE | reports/baseline-report.md:520-524; docs/decisions.md E-008/E-009 | "Stage 4 pending" and the S2/S5 TODO-T010 markers were accurate at T-005 (13 Nov). Stage 4 run 2 has since been measured (T-021 data committed; E-009 recorded 14 Nov). Updating these is T-010's declared scope, not a T-005 defect; flagged so T-010 does not miss it. |
| F-5 | NOTE | FIX-DOC | reports/baseline-report.md:362 vs 318,355; 159-160 vs 407-409; 37 | Carry-forward of cycle 1's F-1/F-2/F-4, all still present and all faithful to their sources: (a) stock-128K all-units header "n_clean 5, n_total 5" copied verbatim from headline.md:181 while the section correctly says 4 clean — optional clarifying parenthetical; (b) probed expert-cache sizes 9,472/8,704 MiB (Stage 2) vs server-reported 9,471/8,701 (Stage 3) not explicitly reconciled — optional one-line note; (c) summary "decode roughly 1.1–1.2×" is a point-estimate range (32K tg@24K CI includes 1.0), properly caveated in §5/§6 per D3 — optional "(point estimates)". All optional at T-010. |

No BLOCKER or MAJOR findings. The executor's report and my re-run agree on every
mechanical item (output hashes identical across all three runs, modulo pytest timing);
no evidence file contradicts its acceptance claim; no hand-written-looking artifact —
every table traces to machine-generated sources and every derived marker's arithmetic
checks out. The single MINOR is a one-line sources-comment gap in a DRAFT report with a
designated finaliser (T-010).

## Task verdict

accepted

## What I did not verify

- **No measurement or re-analysis was run.** T-005 is a light writing task; I verified the
  report against the committed analysis outputs (headline.md, rendered stage3 report,
  sanity JSON, stage2-summary, select-screening, diagnostics), not against `data/raw/`
  JSONL. I did not re-derive bootstrap/t CIs or recompute statistics from raw data; the
  analysis chain was accepted in earlier tasks.
- **Stage 4 work** (T-007, T-019, T-020, T-021, E-008/E-009) — out of scope except to note
  F-4's staleness; I did not review run-2 data or the R7 reading.
- **The executor's chat reasoning** — not available to the reviewer, not requested.
- **Other tasks' work** (T-004, T-006, the kit install, T-018's kit-script exception) —
  only T-005's diff and its cited sources were in scope. I verified T-005's own commits
  touch no frozen file, not the full R3 chain (T-019's scope).
- **Checker robustness beyond its 22 tests, my six mutations and the per-section script**
  — no fuzzing; hostile inputs beyond the mutations untested.
- **Future integer drift** — integers are unchecked by design (F-3); I verified the ones
  present today.
- **Figures** — the baseline report embeds none; the rendered report's SVGs (D9 axis
  fixes) are T-009's scope.
- **Tree-wide privacy scrub** — I scanned only the report (D8); the full history/tree
  scan is T-013's scope.
- **Working tree state** — carries only kit-written changes from this review: run 3
  appended to `.workflow/acceptance/T-005.json`, the cycle-2 state changes, and the
  archived report. Scratch files live in /tmp/t005-review only. No state was hand-edited;
  no lane merge performed; nothing committed by this review (bookkeeping belongs to the
  driver).
