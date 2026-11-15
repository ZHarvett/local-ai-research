# Step 0 close-out snapshot — for the Step 1 planning chat

Date: 2026-11-15. Written by the human-directed close-out session (Parts A–E) after
T-014 finished. Self-contained: the planning chat cannot see the repo. Every number is
copied from a named repo file (declared in `sources:` comments) or is a **live reading**
(command + date, in a fenced block). Account name, hostname and home paths are scrubbed
by convention (`~`, `<account-name>`); the git author name is already public on every commit.

<!-- sources: docs/step-0-completion-report.md, reports/baseline-report.md, reports/writeup.md, data/analysis/stage3/headline.md, data/analysis/stage4/s2-summary.md, docs/decisions.md, docs/recon/pcie-link.md, docs/recon/T-022-kit-fixes.md, docs/recon/scrub-report.md, configs/model.toml, configs/harness.toml, data/env/build-info.json, data/health/model-check.json, data/health/readme-walkthrough.log, docs/progress-log.md, docs/runbook-stage3.md, scripts/_wf.py, scripts/wf-loop.sh, .claude/settings.json -->

## 1. Repo state

- HEAD at snapshot time: `7cb32538c9ffdf2d1811da88151a6a0f65b420e1`
  (`T-014: done — progress-log entry (E-015, Part A commit de20fcf), acceptance run 1
  (0 failures) and kit state`). This file is committed as the next commit after that HEAD.
- `git status`: clean (nothing to commit, working tree clean) — verified before and after
  the close-out work.
- Branches: `main` (current), `lane-2`, `lane-3`. Both lane branches are fully merged into
  main (`git branch --merged main` lists both).
- Tags: **none** (v0.1.0 is T-015's job, deferred).
- Remotes: **none** (`git remote -v` empty). Nothing has ever been pushed.

```text
git log --oneline -15   (live reading, 2026-11-15, at snapshot HEAD)
7cb3253 T-014: done — progress-log entry (E-015, Part A commit de20fcf), acceptance run 1 (0 failures) and kit state
e42c809 T-014: S4 apply E-015 option C — exact edit list C1-C4, W1-W3
f87269e workflow: record E-015 decision
de20fcf docs: baseline report status wording after T-012/T-013 (planning chat, E-015)
96cda09 T-014: S3 escalate E-015 — planning-chat review of completion report and write-up
175a392 T-014: S2 draft step-0 completion report (S1 upstream re-check included)
0d6626a workflow: bookkeeping
e8395cd T-013: done — progress-log entry, acceptance run 1 (0 failures, A4 judgement) and kit state
158078b T-013: S3 apply E-014 option A — allowlist dfcd7d9 x docs/decisions.md (D8 removal side); release-check exit 0, run 2 report
4c273b4 workflow: record E-014 decision
1978f71 workflow: bookkeeping (T-013 blocked-decision E-014)
933444c T-013: S1-S2 release-check script and scrub report; escalate E-014 (dfcd7d9 removal side of WP0 occurrence), task blocked-decision
4e5ba57 workflow: restore T-005/T-018 to accepted (fold regression repaired)
471c8fb workflow: merge lane 2 (T-022 accepted)
baa0ad7 Merge branch 'lane-2'
```

Close-out commits this session: `de20fcf` (Part A, baseline-report wording, Zack-directed),
`f87269e` (E-015 recorded), `e42c809` (T-014 S4 edits), `7cb3253` (T-014 done + bookkeeping).

## 2. Kit state

Full `bash scripts/wf.sh status` (live reading, 2026-11-15, after T-014 done):

```text
plan: Step 0, remaining work: Stage 4, release v0.1.0, completion report (PLAN.md)
phase: P4
T-001  done               lane 1  Smoke test and recon (read-only)
T-002  done               lane 1  Record Stage 3 decisions and merge CLAUDE.md
T-003  done               lane 1  Reviewer calibration
T-004  done               lane 1  README draft
T-005  accepted           lane 2  Baseline report draft and number checker
T-006  done               lane 1  Write-up draft
T-007  accepted           lane 1  Stage 4 session
T-008  accepted           lane 1  S2 check and Stage 4 analysis
T-009  done               lane 1  Post-Stage-4 code fixes
T-010  accepted           lane 1  Final README, report, write-up and changelog
T-011  done               lane 2  Plan v1.9, upstream drafts, methodology
T-012  done               lane 1  README walkthrough from a clean shell
T-013  accepted           lane 1  Scrub and release checks
T-014  done               lane 1  Completion report and planning-chat review
T-015  ready              lane 1  Private repo, CI and tag v0.1.0
T-016  todo               lane 1  Publish v0.1.0
T-017  accepted           lane 3  Unattended loop (wf-loop.sh)
T-018  accepted           lane 2  Kit repair: leave blocked-decision after a review verdict
T-019  accepted           lane 1  Stage 4 pre-flight (no GPU)
T-020  done               lane 1  Restore and verify the PCIe Gen4 link (hands-on)
T-021  accepted           lane 1  Stage 4 session, run 2
T-022  accepted           lane 2  Kit fixes: lane merge status and state riders
READY: T-015
```

(`accepted` is the terminal status for reviewed tasks, `done` for tasks with review: none.)

- **Lanes:** all released and merged. `wf.sh lane-status`: lane 1 no lock, no worktree, no
  mirror file; `.workflow/lanes/` empty; `git worktree list` shows only the main checkout.
- **Locks:** machine lock free (no lock record in state); GPU lock free (`flock -n
  .locks/gpu.lock true` succeeded, live reading 2026-11-15).
- **No llama-server running** (`pgrep -a llama-server` empty, live reading 2026-11-15).
- **Escalations:** none open. E-001 to E-015 all decided (`docs/decisions.md`).
- **Reviews:** none open. Review cycles used: T-005 2, T-007 1, T-008 1, T-010 1, T-013 1,
  T-017 2, T-018 1, T-019 2, T-021 2, T-022 1 (`.workflow/state.json`).
- `wf.sh render` clean (PROGRESS.md re-rendered, no diff); `wf-guard.sh` OK. The guard
  removed one stale lane-1 lock at session start (holder pid gone) — its own cleanup,
  committed as kit bookkeeping in `f87269e`.
- **CI:** `CI_CMD` (docs/recon/commands.env:43) ran detached via scripts/run-detached.sh,
  job `data/logs/jobs/closeout-ci-20261115T171407Z/` (gitignored; status.json + job.log):

```text
CI result (live reading, 2026-11-15): exit 0
uv sync --frozen, ruff check, ruff format --check: clean
pytest -m "not gpu": 1103 passed, 2 deselected in 306.70s (0:05:06)
shellcheck scripts/*.sh: clean
```

**T-005 / T-018 repair status:** both are `accepted`, the correct terminal state. The
T-022 restore-status step **already ran** on 2026-11-15T14:30:26Z (commit `4e5ba57`):
events seq 444 (`T-005 done -> accepted, review-verdict seq 210`) and 445 (`T-018
done -> accepted, review-verdict seq 204`) in `.workflow/state.json`. Nothing to repair.

**What T-015 and T-016 wait for** (cards via `wf-card.sh`, PLAN.md):

- **T-015 — Private repo, CI and tag v0.1.0** (`ready`, human gate). Zack must: run
  `gh auth status` / `gh auth login` (GitHub.com, HTTPS, browser), then say go — the go
  authorises creating the PRIVATE repo `ZHarvett/local-ai-research`, pushing main and
  pushing tag v0.1.0. Preconditions: `gh auth status` exit 0; no git object over
  95,000,000 bytes; `scripts/release-check.sh` exit 0. Steps: release notes, repo create +
  push, wait for CI (red CI escalates, no fixes pushed), annotated tag v0.1.0 + push,
  progress-log entry with the CI URL. Deferred by Zack at this close-out.
- **T-016 — Publish v0.1.0** (`todo`, depends on T-015, human gate). Zack must: make the
  repo public (`gh repo edit … --visibility public …`) and create the release
  (`gh release create v0.1.0 … --notes-file reports/release-notes-v0.1.0.md`), optionally
  file the docs/upstream/ drafts (the #28619 draft is retired per E-015; the
  draft-length-2 issue draft is Zack's choice), then say go. Deferred with T-015.

## 3. Decisions (one line each; full text in docs/decisions.md)

Stage 3 decisions (docs/decisions.md:1199-1207):

- **D1** — 128K headline uses all units, labelled "includes paging-flagged stock windows",
  clean-units figures beside it; the declared §5.4 rule, a recorded S4(d) deviation.
- **D2** — tuned-64K paging is the known Stage 2a MTP-cell file-page faulting; not
  investigated; gate passed under both denominators (36.4% tool / 23.5% per A7).
- **D3** — 32K swap sensitivity not material; wider intervals from dropping 3 of 5 pairs;
  32K decode gain small and not robust; T_turn_400 conclusions unchanged.
- **D4** — five test literals edited to "1.8" (commit 422eada) accepted; T-009 makes tests
  read the version from the plan file.
- **D5** — tests/test_sweep_probe.py flakiness fixed before release (T-009).
- **D6** — Phase 0 HEAD check read as HEAD = 8096461 with a clean tree, accepted.
- **D7** — sanity output named data/sanity/stage3-tuned.json (runbook said stage3-all.json);
  minor deviation, docs cite the actual name.
- **D8** — git history not rewritten; the early WP0 account-name occurrence matches the
  already-public author name; current tree scrubbed; history scan escalates only beyond
  the known allowlisted occurrences; committed files refer to `<account-name>`.
- **D9** — expert-cache hit rates carry the caveat: include warm-up and attempt-1 units of
  re-run windows; decode-batch only; figure axes fixed in T-009.

Stage 4 rules (docs/decisions.md:1209-1212, 1292-1295):

- **R1** — tuned-64K gets stock's fallback: fewer than 5 clean units after re-run → S2 on
  all units, labelled, recorded as S4(d) deviation.
- **R2** — gate failure only from tuned-64K paging with every flagged unit re-running clean
  → accepted with a recorded "- R2 applied: Stage 4" line; any other gate failure escalates.
- **R3** — Stage 4 runs 13 Nov 2026 or later; only kit scripts (+ CLAUDE.md, .gitignore)
  changed under the frozen paths since the Stage 3 commit; exact check command in the rule.
- **R4** — an S2 failure is reported and escalated, never re-measured automatically.
- **R5** — Stage 4 run 1 (Gen3 x8 link throughout) invalid for S2, marked superseded, never
  deleted, reported as excluded diagnostic; run 2 is the S2 run; R1–R3 apply unchanged.
- **R6** — run 2 is the only re-run; a run-2 S2 failure is a genuine FAIL (escalate under
  R4); no run 3 without a new decision.
- **R7** — every gated GPU session checks the link under load
  (`nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.width.current`); anything other
  than "4, 8" while generating stops and escalates. **Clarified by E-009:** applies to
  sustained generation (power ≥ 50 W or P1); idle downshifts and at most one 0.5 s ramp
  sample don't count; no measured-window sample may be anything but 4, 8.

Escalation decisions (docs/decisions.md:1170-1394; chosen option + one-line substance):

- **E-001 (A)** — R3 code-state check uses the earliest Stage 3 session commit (8096461);
  one code state across the three sessions; Zack widened the permission allowlist himself.
- **E-002 (A)** — scripts/wf.sh recognised as kit provenance for the R3 check (the PLAN.md
  pattern was written too narrowly); no code change or re-measure.
- **E-003 (B)** — CLAUDE.md kit/umbrella merge: two lines changed so a blocked task doesn't
  freeze other lanes and lane choice is asked, not decided by the session.
- **E-004 (B)** — unattended loop lane mechanism: `/lane N` (deterministic headless), not
  piped-yes `/continue`.
- **E-005 (B)** — recompute_ready lane-placeholder diagnosis accepted; fix deferred until
  after Stage 4; exact narrow guard exception meanwhile (fix later landed in T-022).
- **E-006 (A)** — pre-reviews of ready tasks unachievable under the frozen kit; documented
  gap (loop-design.md §11.3), no code change; loop's pre-review branch inert and safe.
- **E-007 (A)** — T-019's "escalate once listing every failure" attaches to the final
  Result; the transient P8 FAIL (another lane's uncommitted work) needed no workaround.
- **E-008 (A)** — Stage 4 run 1 invalid (Gen3 x8); restore + verify Gen4 x8 under load
  (T-020), re-measure as new gated task (T-021 run 2); accepting run 1 or widening the
  tolerance rejected.
- **E-009 (A)** — ratify the under-load reading of R7; run 2 stands as the S2 run; no
  re-measure; kernel/driver confound recorded.
- **E-010 (A, three parts)** — T-009 may ruff-format the preflight doc; A1 split into five
  single-CI acceptance items; evidence entries must be files; run-1 render stays untouched.
- **E-011 (A)** — decision-recording order after a plan amend reset T-009: record E-010,
  re-block, record E-011, re-claim, re-mark S1/S2, resume S3; kit repair for arbitrary
  order (option B) queued after the release.
- **E-012 (A)** — T-011 evidence field becomes files (plan + two drafts + methodology.md);
  directory evidence rejected; rule: every card's evidence entries must be files.
- **E-013 (A)** — T-022 continues with no state change; E-005 guard exception extended for
  T-022 only; the "done AND in lane 2" guard lines were false positives.
- **E-014 (A)** — history-scan allowlist gains exactly one pair, dfcd7d9 × docs/decisions.md
  (the removal side of the WP0 occurrence, under D8); --cc scan kept; rewrite rejected.
- **E-015 (C)** — completion report + write-up approved for delivery with an exact edit list
  (C1–C4, W1–W3), applied in T-014 S4 (commit e42c809); #28619 comment draft retired, not
  filed; rule: status wording checked against kit state at review; per-commit counts cited
  from the scrub report, not prose; non-re-derivable claims worded as recorded.

## 4. Pinned versions (with sources)

**llama.cpp** (data/env/build-info.json): tag `b12208`, commit
`57d04820dfef7a3519aac276d018a6fd71251895`, built 2026-11-08T15:42:22Z, CUDA
`-DCMAKE_CUDA_ARCHITECTURES=120` (CMake rewrote to 120a), Release, GGML_NATIVE=ON.
llama-server binary SHA-256 `c6b14a4bb904b323d927254ba8b092296d57a4eaddffa38f2e88f21865144e0b`.
Upstream at close-out (completion report §8, re-check 2026-11-15): newest release v1.0.0
(2026-11-13, build b12359), newest b-tag b12415 — the pin stands for the release.

**Model** (configs/model.toml): `ornith-ai/Ornith-1.5-35B-A3B-GGUF`, revision
`f60452672689e0040be350560267a614cc172a18`, file `Ornith-1.5-35B-Q4_K_M.gguf`,
21,713,463,040 bytes, SHA-256
`42739874cc2ccfdb8523b23fbe52e29b2a7555c8176737ca9ca0b5d59859d41f` (WP4 recomputed).
Base repo `ornith-ai/Ornith-1.5-35B-A3B` rev `10fbf86fed7ecee4a061f8b499a618f46001cac1`.
The embedded chat template is a modified variant and is used in every stage (WP5 decision).
Sampling (model card): temperature 0.6, top_p 0.95, top_k 20.

**MTP head**: embedded in the GGUF — no separate file. `qwen35moe.nextn_predict_layers` = 1,
head block 40, tensor screen **PASS** (no known broken-head signature;
data/health/model-check.json). The screen cannot prove the head is trained; WP5's
acceptance/equivalence tests did: acceptance 0.771 at 64K, draft length 1
(data/analysis/stage3/headline.md). Draft length 1 bit-identical to MTP off is the plan's
recorded greedy-check finding, not re-derivable from the committed sanity files (E-015 W3).

**Harnesses** (configs/harness.toml): OpenCode `opencode-ai` **1.19.5** (published
2026-10-28, npm latest at install and at the 2026-11-15 re-check); dsh `@deepseek-ai/dsh`
**0.2.1-rc.5** (published 2026-10-29; npm latest had moved to 0.2.2-rc.1, rejected by the
7-day rule; 295 plugin packages at the same version). Runtime pin: node 26.13.0, npm
12.2.1. Install: repo-local prefix `third_party/node`, `npm ci --ignore-scripts` from
configs/harness/package-lock.json (SHA-256 d21af6e8f2daea1e6903e42b81268f4fde9385fbade49e78eec7d190e79ccb77),
inside a bubblewrap sandbox (read-only FS, empty /home and /tmp, repo-local HOME/npm cache,
--no-net install scripts); full lockfile age check: 643 name@version pairs, 0 too new.
Nothing on PATH. Configuration: `smallpc.harness` renders configs/harness/opencode.json.tmpl
and dsh.cordis.patch.yml.tmpl, reading the context from the server's
`GET /props: default_generation_settings.n_ctx`; output limit = min(16384, per-slot ctx // 4).
Binaries (configs/harness.toml [binaries], repo-relative):
`third_party/node/node_modules/opencode-ai/bin/opencode.exe` and
`third_party/node/node_modules/@deepseek-ai/dsh/lib/bin.js` (run with node).

**Kernel / driver / CUDA**: Stage 3 and Stage 4 run 1 ran on kernel 7.3.1-1-cachyos,
NVIDIA driver 615.78.08; run 2 and the current machine are on 7.3.4-1-cachyos / 620.70.06
(completion report §3 E-009; docs/stage4-run2-conditions.md). CUDA 13.4, V13.4.92
(data/env/build-info.json; live nvcc agrees). The kernel/driver change is a recorded
confound on the S2 comparison; no re-measure (E-009).

**PCIe link** (docs/recon/pcie-link.md): negotiated ceiling Gen4 x8 (host max Gen4, GPU max
Gen5, width 8). The link downshifts at idle (Gen1/Gen2 in P8) — an idle reading is not
evidence. Stage 3: every measured-cell telemetry row Gen4 x8. Run 1: Gen3 x8 throughout
(the negotiated max itself was Gen3) → superseded (R5). Run 2: every measured-window row
Gen4 x8; T-012's clean-shell walkthrough: all 45 under-load samples "4, 8"
(data/health/readme-walkthrough.log). Live idle reading at this close-out (no GPU work
allowed this session):

```text
nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.width.current,pcie.link.gen.max,pcie.link.width.max --format=csv,noheader
1, 8, 4, 8        (live reading, 2026-11-15, idle: current Gen1 x8, max Gen4 x8)
```

## 5. Headline Step 0 results

Sources: docs/step-0-completion-report.md §2, reports/baseline-report.md (§Stage 2 config
table, §Stage 3, VRAM breakdown), data/analysis/stage3/headline.md.

**Chosen tuned config per context** (baseline report, Stage 2 final-selection table; all
carry `--cache-ram 2048`, `-fa on`, `-np 1`, batch/ubatch 4096; placement P6 = `-cmoe`,
all experts host-side with a probed max-fit VRAM expert cache):

| context | MTP draft | KV type | expert cache (MiB) | sanity |
|---|---|---|---|---|
| 32K | off | 8-bit (default) | 11,520 | pass |
| 64K | 1 | FP16 | 9,472 | pass |
| 128K | off | FP16 | 8,704 | pass |

Stock = plan §3.1 defaults (`--fit` placement, -b 2048 -ub 512, FP16 KV, fa auto, default
slots, `--cache-ram 8192`, no MTP).

**T_turn_400 tuned/stock** (Stage 3, quiet machine, 5 paired reps; geometric mean [95% CI];
headline.md; 128K on all units per D1):

| context | ratio [95% CI] | stock → tuned (s) | basis |
|---|---|---|---|
| 32K | 0.705 [0.672, 0.739] | 8.339 → 5.882 | clean units, n=5 |
| 64K | 0.690 [0.649, 0.734] | 9.288 → 6.413 | clean units, n=5 |
| 128K | 0.706 [0.679, 0.735] | 11.191 → 7.910 | all units (1 flagged stock window), n=5 |

128K clean-units figure beside it: 0.711 [0.673, 0.750] (n=4); same sign, interval excludes
1.0 in both versions. About 30% less time per turn (derived, completion report §2).

**Prefill / decode** (headline.md, tuned/stock ratios at the measured depths): pp_fresh
2.686 / 2.664 / 2.621 at 8K/16K/24K (32K context); 2.488 / 2.399 / 2.304 at 16K/32K/48K
(64K); 2.926 / 2.701 / 2.487 at 32K/64K/96K (128K) — roughly 2.3–2.9× faster. tg: 1.173 /
1.142 / 1.089 (32K), 1.225 / 1.239 / 1.213 (64K), 1.143 / 1.136 / 1.125 (128K) — roughly
1.1–1.2× faster; the 32K decode gain is small and not robust to excluding swap-active units
(D3). Prefix re-read takes 0.378 / 0.423 / 0.382 of stock's time (completion report §2).

**VRAM breakdown** (baseline report, from reports/stage3/report.md; MiB):

| context | cell | model | KV | recurrent | compute | expert cache | other | peak used | min free | CPU layers |
|---|---|---|---|---|---|---|---|---|---|---|
| 32K | stock | 13,468 | 640 (f16) | 251 | 299 | 0 | 268 | 14,926 | 1,385 | 15 |
| 32K | tuned | 1,303 | 340 (q8_0) | 63 | 1,348 | 11,520 | 359 | 14,932 | 1,379 | - |
| 64K | stock | 12,825 | 1,280 (f16) | 251 | 331 | 0 | 269 | 14,956 | 1,355 | 16 |
| 64K | tuned | 1,326 | 1,408 (f16) | 126 | 2,436 | 9,471 | 523 | 15,290 | 1,021 | - |
| 128K | stock | 11,463 | 2,560 (f16) | 251 | 396 | 0 | 272 | 14,942 | 1,369 | 19 |
| 128K | tuned | 1,303 | 2,560 (f16) | 63 | 2,116 | 8,701 | 358 | 15,100 | 1,211 | - |

Expert-cache decode-batch hit rates 97.0% / 94.3% / 93.9% (D9 caveats: warm-up + attempt-1
units included, decode batches only, public-code workloads). Unexplained residual:
512–532 MiB "other" on MTP cells vs 337–363 MiB without (completion report §4 item 3).

**MTP findings** (completion report §§2, 4; baseline report Stage 2 section): draft length 1
at 64K only, acceptance 0.771; helped about 2 to 5% per turn (2.4% at 64K draft 1); costs
9 to 16% of prefill speed and 0.75 to 1.5 GiB VRAM; draft length 2 fails output sanity
deterministically (8-gram repeat 8 vs reference 2) on four configs — excluded, upstream
draft written, not filed; at 128K no MTP cell had the VRAM margin. MTP works with `-np 2`
(both slots draft) on the pinned build.

**Reproducibility (S2)**: Stage 4 run 2 (2026-11-14) PASS 6/6 rows, every row on clean
units (data/analysis/stage4/s2-summary.md); run 1 superseded (R5); kernel/driver confound
(E-009). Clean-shell walkthrough (T-012): 6/6 configs launch with only the README commands,
all 45 under-load link samples "4, 8".

**S1–S5 status** (completion report §7, after E-015):

| criterion | verdict |
|---|---|
| S1 Coverage | met — Stages 1–4 measured, raw JSONL committed |
| S2 Reproducibility | met — 6/6 rows run 2 + clean-shell walkthrough 6/6 (T-012) |
| S3 Decisions | met — six configs, tuned by the §3.3 rule, all launch via launch-server.sh |
| S4 Health checks | met, deviations recorded (D1 128K headline; Stages 1–2 apps-open) |
| S5 Release | **pending T-015/T-016** — scrub and release checks already pass (T-013) |

## 6. How to start a new plan in this kit (import investigation)

Read from scripts/_wf.py and scripts/wf-plan-import.sh (a thin wrapper: `exec wf.sh
plan-import "$@"`), then tested in **throwaway clones** under
/tmp/local-ai-research-closeout-test/ (clone-a, clone-b) with a minimal one-card plan
(T-101, phase P1, lane 1, light, review none). Nothing was imported or amended in the real
repo. Line numbers are at snapshot HEAD.

### Code facts

- `cmd_plan_import` (scripts/_wf.py:1171-1200): with existing state, a fresh import is
  **always refused** — "refusing to import over in-progress work" if any task is
  claimed/in-progress/awaiting-gate (ACTIVE_STATUSES, line 52), otherwise "state already
  exists; use --amend to re-issue a plan" (line 1191). A fresh state is created only when
  `.workflow/state.json` does not exist (lines 1192-1197).
- `_fresh_state` (1203-1234): builds tasks from the new plan only; **events, escalations,
  review_cycles, review_dispositions all start empty**; title and plan_file come from the
  new plan.
- `_amend_state` (1244-1280): identical plan hash → "plan unchanged" die. New cards added
  as todo. **Byte-identical cards keep their status** (card_sha256 compare, 1256-1257).
  Changed cards: refused while active/in-review/changes-requested (1259-1263); otherwise
  **reset to todo with plan_changed: true and steps_done wiped** (1264-1269) — even for
  done/accepted tasks (the resurrection bug). Cards absent from the new plan are **deleted
  from state** (1270-1273; a plan-removed event only for non-terminal ones — and "done" is
  NOT in TERMINAL_STATUSES, line 53: accepted/superseded/cancelled). Phases are replaced;
  **title and plan_file are NOT updated by amend** (1274-1276). Escalations, events and
  review_cycles survive an amend.
- `next_escalation_id` (2127-2130): max E-number **in state** + 1. `cmd_escalate` writes
  `escalations/E-NNN.md` with `open(out, "w")` (2167-2170) — it would **overwrite** an
  existing brief file.
- `validate_plan` (1133-1135): every depends_on must exist in the same plan — keeping an
  old card drags in its whole dependency closure.
- There is **no archive command** (subcommand list: init-from-plan, plan-import, …,
  restore-status, … — nothing archival).

### Test results (throwaway clones, 2026-11-15)

1. **Fresh import over existing state, no --amend** (clone-a): refused, exit 1 —
   `wf: state already exists; use --amend to re-issue a plan` (T-015 ready / T-016 todo are
   not "active", and it still refuses).
2. **--amend with a T-101-only plan** (clone-a): exit 0. All 22 Step 0 tasks **deleted from
   live state**, including parked T-015/T-016 and every done/accepted task; T-101 ready.
   Escalations (15), events (486 after) and review_cycles kept. **title/plan_file stayed
   "Step 0, remaining work… / PLAN.md"**; phases became [P1]. PROGRESS.md re-rendered with
   only T-101.
3. **E numbering after that amend**: `next_escalation_id` → **E-016** (continues).
4. **--amend with the full Step 0 plan + T-101 appended** (23 cards, clone-a): exit 0.
   Every status preserved (10 done, 10 accepted, T-015 ready, T-016 todo); T-101 ready.
   **Task ids continue (T-101…) without clashing** — ids are plain dict keys, any T-\d+ works.
5. **--amend with one changed done card** (T-001 estimate 60m→99m, clone-a): T-001
   **done → ready, steps_done wiped**, plan-changed event. Resurrection confirmed. (First
   attempt changed only the `### T-001` heading — no effect: the card's explicit `title:`
   field overrides the heading, so the card hash was unchanged.)
6. **Fresh import with state.json removed** (clone-b only — never do this in the real
   repo): exit 0, fresh state with only T-101, empty escalations/events/review_cycles,
   title/plan_file from the new plan. `next_escalation_id` → **E-001 while
   escalations/E-001.md already exists on disk** — the next escalation would overwrite the
   old brief. docs/decisions.md and all escalations/ files survive as files, but the live
   E-numbering collides with them.

### Answers

- **(a) New plan over existing state:** a fresh import is impossible without deleting
  state (forbidden hand-edit). `--amend` with a Step-1-only plan deletes every Step 0 task
  from live state (parked T-015/T-016 included), keeps escalations/events/review_cycles,
  keeps the stale Step 0 title/plan_file, and replaces phases. The decisions list
  (docs/decisions.md) and escalations/ files are untouched files in every path. E-numbering
  continues after an amend (E-016 next) but restarts at E-001 after a fresh import,
  colliding with the existing brief files.
- **(b) T-101… ids:** yes — test 4 added T-101 beside T-001…T-022 with no clash.
- **(c) --amend vs fresh import:** amend preserves unchanged cards' statuses and the
  escalation history; fresh import wipes all state (and restarts E-numbering). Amend's
  dangers: changed done/accepted cards resurrect (test 5), removed cards vanish, title
  stays stale. Fresh import's dangers: total state loss from the live kit + E-file
  overwrite collision; in the real repo it additionally requires a forbidden hand-edit.
- **(d) Archive Step 0, keep state:** no kit command. The archive mechanism is git itself:
  a local tag (or branch) at the close-out HEAD preserves PLAN.md, .workflow/state.json,
  PROGRESS.md, the progress log, decisions and every acceptance record. The live state can
  then move on via amend; the archived state stays readable at the tag.

### Options for importing a Step 1 plan, with risks

- **A. Grow the plan:** append Step 1 cards to PLAN.md, keep every Step 0 card
  byte-identical, amend. Everything stays tracked. Risks: any accidental edit to a finished
  card resurrects it (test 5); the plan and state grow forever; the dependency closure
  makes dropping old cards impossible piecemeal.
- **B. Clean break by amend (recommended):** archive first (git tag), then replace PLAN.md
  with a Step 1 plan (new title, cards T-101+), amend. Live state becomes Step 1 only;
  Step 0 lives in the tag + progress log + decisions + escalations files; E-numbering
  continues. Risks: parked T-015/T-016 leave kit tracking (re-card them as new T-1xx cards
  with the same gate text if the release should stay tracked — keeping the old cards
  verbatim is impossible without their dependency closure); state title/plan_file stay
  stale (cosmetic, only a fresh import sets them); PROGRESS.md re-renders (old version in
  history).
- **C. Fresh import in a new repo/clone:** cleanest state, but the Step 0 kit state is left
  behind in the old repo; E-numbering restarts and would overwrite existing escalation
  briefs if the files are copied across; two repos to keep straight. Only sensible if
  Step 1 deliberately starts a new umbrella repo.
- **D. Fresh import in the same repo:** requires deleting .workflow/state.json — a
  forbidden hand-edit, plus the E-collision. Not an option without a new planning decision.

### Safest exact sequence (option B — for the planning chat to approve, NOT run this session)

```bash
# 0. Zack decides T-015/T-016: run them first, or re-card them into Step 1 (gate text verbatim).
# 1. Archive Step 0 (local tag only; no remote, no push):
git tag step-0-closeout 7cb32538c9ffdf2d1811da88151a6a0f65b420e1   # or the later v0.1.0 HEAD
# 2. Write the Step 1 plan to PLAN.md (old PLAN.md is preserved at the tag):
#    '# <title>', '## Shared rules', '## Assumption register' (- A-N: … — checked by T-1xx),
#    '## Phases' (- P1: …), cards '### T-101 — …' with all required fields;
#    evidence entries must be FILES (E-012 rule).
# 3. Import:
bash scripts/wf.sh plan-import PLAN.md --amend
# 4. Verify:
bash scripts/wf.sh status && bash scripts/wf.sh ready && bash scripts/wf-guard.sh
#    expect: only Step 1 tasks; E-numbering continues at E-016; no old card reset
#    (all old cards removed, none changed).
```

## 7. Known kit bugs (file:line at snapshot HEAD) and review-note status

1. **`_amend_state` reset/resurrection** — scripts/_wf.py:1264-1269. A changed card in
   done/accepted state is reset to todo, steps_done wiped (test 5 above). **Open**; the fix
   is E-011 option B, queued after the release. Not fixed by T-022.
2. **wf-loop stops on the reviewer's uncommitted files** — scripts/wf-loop.sh:413-424
   (`dirty_tree` excludes only PROGRESS.md and .workflow/), stop at 556-559. Review
   artifacts (reviews/T-xxx/*.md) left uncommitted by a review session stop the loop.
   **Open.**
3. **Final review cycle treated as exhausted** — scripts/wf-loop.sh:226-230: the
   address/inflight/post branches all require `cycles < max_cycles` (2); a task left
   in-review/changes-requested at cycle == max falls into `exhausted` (line 230) and the
   loop stops (264-265) instead of finishing the last review. **Open** (T-017 r2 F-5
   recorded the ordering note; the kit escalates if a cycle cannot reach a verdict).
4. **No resume after a gate** — scripts/wf-loop.sh:266-269 (any open gate → stop) and
   281-289 (stranded in-progress → "resume manually"). `gate-release` leaves the task
   in-progress (scripts/_wf.py:1643-1645) and /continue only picks ready tasks, so after
   Zack's go a human must run `wf.sh resume`. **Open.**
5. **`machine_lock_free` ignores a dead holder** — scripts/_wf.py:794-806: reports the lock
   taken without any pid-alive check; a crashed holder blocks heavy work until a manual
   `wf.sh machine-release`. **Open.** (The guard does clean stale *lane* locks — it removed
   one at this session's start — but not the machine lock.)
6. **`gate-wait` does not release the machine lock** — scripts/_wf.py:1630-1640: mutates to
   awaiting-gate only; a task that took the machine lock keeps it while waiting for Zack.
   **Open.** (`cmd_done` releases it, scripts/_wf.py:1879.)
7. **`wf-decision` refuses non-blocked-decision tasks** — scripts/_wf.py:2219-2224. This is
   T-018's deliberate pre-check (compute the unblock target before writing anything), but
   it creates the E-011 ordering trap: after a plan amend resets a task, its open decision
   cannot be recorded until the task is re-blocked. **Open as an ordering issue** (E-011
   option B queued).
8. **`recompute_ready` placeholder promotion** — scripts/_wf.py:454-465. **Fixed by T-022
   S4(5)**: the main state now skips tasks owned by a lane mirror (E-005), with regression
   tests.
9. **Review commands do not commit their own artifacts** — scripts/_wf.py:1914
   (review-open), 1952 (review-verdict), 1983 (review-disposition): they write reviews/
   files and state but never git commit; the session must. **Open** (feeds bug 2).

**Fixed by T-022** (docs/recon/T-022-kit-fixes.md, all red/green verified): the lane fold
overwriting advanced main statuses (S2, the fold at scripts/_wf.py:2318 now keeps main's
accepted/in-review/changes-requested/superseded/cancelled); the `restore-status` repair
command (S3, guarded by verdict-seq evidence — used for T-005/T-018 at 4e5ba57); the
review-verdict parser's missing parenthetical (S4); stale lane-worktree refresh (S4, merges
main when behind); bug 8 above (S4). **T-018 earlier** added the blocked_from return target
for blocked-decision verdicts and the escalate-side preserve (scripts/_wf.py:2183-2186)
plus the wf-decision pre-check (bug 7).

**Review-note resolution** (verified against current files today; T-022 recon §5 was the
prior check):

- **T-005 r2 F-1** (MINOR, FIX-DOC): **open.** §8's sources line
  (reports/baseline-report.md:589) still names only the plan, s2-summary.md and caveats.md,
  while the S4 row cites MTP acceptance 0.771, which lives in headline.md /
  docs/stage2-summary.md. Attribution gap survives.
- **T-005 r2 F-2** (NOTE, optional): **open** (not applied; the GiB derivation itself is
  properly marked at reports/baseline-report.md:181-182).
- **T-005 r2 F-3** (NOTE, no action): **closed by design** — the checker's documented limits
  (integers exempt, whole-file source matching) stand.
- **T-005 r2 F-4** (NOTE, T-010 scope): **resolved** — no "Stage 4 pending"/TODO-T010 in the
  report; the S2 row records run 2 PASS 6/6 (status wording refreshed again in de20fcf).
- **T-005 r2 F-5** (NOTE, three optional): **open** (all three unapplied: stock-128K
  all-units header parenthetical; probed-vs-server-reported cache reconciliation note;
  "point estimates" qualifier on the decode range).
- **T-018 r1 F-2** (NOTE, FIX-CODE, future kit card): **open, both edges.** (a) cmd_decision
  validates status and restore target but not lane ownership (scripts/_wf.py:2215-2232);
  (b) cmd_review_verdict still sets blocked_from unconditionally for a blocked-decision
  verdict (scripts/_wf.py:1969-1970).
- **T-019 r1 F-3**: **resolved** — docs/runbook-stage3.md:146 now reads 1,577 s (T-022 S6).
  Residual recorded observation: line 149's grand total still uses the 1,578 addend
  (5,432 vs 5,431 s; the 90 min estimate unchanged) — left for a future docs card.

## 8. What already exists for Step 1 (the benchmark)

**Repo layout (two levels, live reading 2026-11-15; gitignored data/logs, data/raw detail,
caches and venvs omitted):**

```text
build/tools/                  llama.cpp build tree (b12208)
configs/
  harness.toml, machine.toml, model.toml, quiet-check.toml
  harness/                    package.json, package-lock.json, opencode.json.tmpl, dsh.cordis.patch.yml.tmpl
  model/                      chat_template.jinja
  server/                     six released configs {stock,tuned}-{32k,64k,128k}.toml (+ workload-check)
  sweeps/                     TOML sweep specs (Stages 1–4)
  workloads/                  recipe.toml, manifest.json (recipes only, no source text)
data/
  analysis/ cache/ env/ harness/ health/ loadmode/ microbench/ probes/ raw/ sanity/ workloads/
  (raw/ append-only per-request JSONL + snapshots + telemetry; logs/ gitignored job dirs)
docs/
  plans/ (project-plan.md, step-0-baseline.md v1.9), recon/, upstream/ (two drafts)
  decisions.md, progress-log.md, methodology.md, environment.md, WORKFLOW.md,
  runbook-stage{1,2,3}.md, stage{1,2,3,4}-conditions.md, stage4-run2-conditions.md,
  stage2-summary.md, step-0-completion-report.md
escalations/                  E-001.md … E-015.md (all decided)
models/                       Ornith-1.5-35B-Q4_K_M.gguf (gitignored, SHA-256 pinned)
reports/
  baseline-report.md, writeup.md, stage1/ stage2/ stage3/ stage4/ stage4-run2/
  functional-test/ preflight/
reviews/                      T-005 T-007 T-008 T-010 T-013 T-017 T-018 T-019 T-021 T-022
scripts/                      launch-server.sh, stop-server.sh, run-detached.sh, wf*.sh, _wf.py,
                              build-llama.sh, install-harnesses.sh, _sandbox.sh, healthcheck.sh,
                              check-quiet.sh, inventory.sh, isolation-check.sh, job-status.sh, …
src/smallpc/                  the measurement package (below)
tests/                        pytest suite (1103 passed, 2 gpu-marked deselected)
third_party/                  llama.cpp (pinned clone), node/ (harness install), harness-state/,
                              npm-cache/, workload-sources/ (pinned public-code clones)
tools/                        check_doc_numbers.py, scrub helpers, stage diagnostics, pcie_bw.cu, stream
workflow-kit/                 the kit's own source + tests (sync.sh installs into scripts/)
PLAN.md  PROGRESS.md  CLAUDE.md  README.md  CHANGELOG.md  LICENSE  LICENSE-DATA.md
pyproject.toml  uv.lock  .workflow/  .claude/
```

**src/smallpc modules** (one line each, from the module docstrings):

- `analysis.py` — sweep-session analysis: units, attempts, exclusion rules, §5.3 derived metrics.
- `config.py` — pydantic schemas + TOML loaders (machine, model, server, sweep configs).
- `envsnap.py` — environment snapshots and per-cell preconditions.
- `flags.py` — §5.6 flag detectors (pure functions).
- `gguf_check.py` — MTP (nextn) head screen for broken-head signatures.
- `harness.py` — renders OpenCode/dsh configs from templates, context read from the server.
- `health.py` — WP5 health suite (endpoints/behaviours of the pinned server).
- `hostcache.py` — host prompt cache size and per-window memory figures.
- `labels.py` — report data labels. `livecheck.py` — 60 s live telemetry CSV.
- `lockage.py` — npm lockfile age check (7-day pinning rule).
- `microbench.py` — PCIe, STREAM RAM bandwidth, NVMe sequential read.
- `neartie.py` — greedy-equivalence / near-tie divergence analysis.
- `netbridge.py` / `netproxy.py` — loopback forwarding into the network-less sandbox; logging deny-by-default HTTP(S) proxy (WP7).
- `paging_analysis.py` — paging investigation of a session.
- `parsers.py` — llama-server log parsers (pinned b12208). `render.py` — config → llama-server argv.
- `report.py` — render/coverage/repro reports. `requests.py` — per-request pattern from server logs.
- `sanity.py` / `sanity_runner.py` — output sanity check + greedy 512-token runner.
- `scrub.py` — account/hostname/home-path scrubbing. `select.py` — §3.3 eligibility/selection.
- `sizes.py` — exact GGUF sizes (bytes/expert, KV bytes/token, recurrent state).
- `smoke.py` — harness smoke-test helpers. `stats.py` — §5.5 statistics (wider of bootstrap/t).
- `telemetry.py` — 2 Hz GPU/CPU/process/memory sampler.
- `sweep/` — the resumable sweep runner: spec expansion, server lifecycle via launch-server.sh,
  client (/completion), instance protocol, probe (max-fit), provenance, append-only records, session/canaries, status.
- `workloads/` — exact-token-length real-source prompts: recipe, packing, builder, manifest
  (recipes only), tokenizer HTTP client, verify, live check, cache.
- `stage2/` — spec generator, declared-rule decision tool, gate, eligibility, llama-bench
  cross-check wrapper (labelled Stage 2e only), smoke.
- `stage3/` — headline tables (§5.4 rules), gate, S2 repro check with all-units fallback,
  quiet-machine check, markdown render, plan-rule reader.

**Runner / harness / container code:** the sweep runner (`python -m smallpc.sweep`),
workload CLI (`python -m smallpc.workloads`), stage2/stage3 CLIs, launch-server.sh /
stop-server.sh (TOML-rendered argv, GPU lock, /health wait), run-detached.sh (long jobs),
harness.py + smoke.py + netbridge/netproxy for the OpenCode/dsh smoke runs,
third_party/harness-state for sandboxed harness state. **No container code exists** (the
only docker/podman mentions are inventory.sh's tool probes, scripts/inventory.sh:140-141).

**Containers:** neither docker nor podman is installed — `command not found` for both
(live reading 2026-11-15). Nothing to run without sudo; a Step 1 container plan needs an
install (sudo — Zack's call) or another isolation path. **bubblewrap IS installed**
(/usr/bin/bwrap, version in the tooling block below) and already used by scripts/_sandbox.sh
for the harness sandbox.

**Disk / RAM / swap** (live readings, 2026-11-15):

```text
df -h:  /mnt/data (model SSD, btrfs)  239G total, 95G used, 143G avail (41%)
        /        (OS drive)          80G total, 40G used,  36G avail (53%)
        /home                        382G total, 241G used, 138G avail (64%)
free -h: Mem 30Gi total, 6.6Gi used, 23Gi available; Swap 30Gi total, 1.2Gi used
swapon:  /dev/zram0, 30.5G, prio 100;  vm.swappiness = 150
nproc:   16 (Ryzen 7 9700X, 8 cores / 16 threads)
```

The zram/swappiness-150 behaviour is a recorded Step 0 finding: the kernel swaps cold
llama-server pages even with ~20 GiB available (completion report §4 item 5) — Step 1 on
this PC will see the same.

**Harnesses runnable** (version commands only, live readings 2026-11-15; repo-local, not
on PATH):

```text
third_party/node/node_modules/opencode-ai/bin/opencode.exe --version   → 1.19.5
node third_party/node/node_modules/@deepseek-ai/dsh/lib/bin.js --version → 0.2.1-rc.5
node --version → v26.13.1   npm --version → 12.2.2   (system; pin is 26.13.0 / 12.2.1)
```

**Tooling present** (live readings, 2026-11-15):

```text
uv --version          → uv 0.13.8 (3d97a6aad 2026-11-12 x86_64-unknown-linux-gnu)
gh --version          → gh version 2.104.0 (2026-11-12)
shellcheck --version  → 0.11.0
bwrap --version       → bubblewrap 0.13.1
nvcc --version        → Cuda compilation tools, release 13.4, V13.4.92
nvidia-smi            → 620.70.06, NVIDIA GeForce RTX 5060 Ti, 16311 MiB
```

`gh auth status` was NOT checked (no GitHub work this session) — it is T-015's first
precondition.

## 9. Tool permissions (.claude/settings.json, summarised)

**Allowed:** all kit commands (`bash scripts/wf*.sh`, `python3 scripts/_wf.py`,
`bash scripts/*`, `./scripts/*`); read-only git (status/diff/log/show/rev-parse/cat-file/
rev-list/branch/worktree list) plus `git add`, `git commit`, `git apply`; `uv run` /
`uv sync` (pytest, ruff, …); shellcheck; sha256sum; cat/ls/test; nvidia-smi, pgrep, ps;
systemd-inhibit, flock, setsid, nohup, sleep, date; `Read(./**)`.

**Denied:** sudo; `rm -rf` / `rm -fr`; force push (`git push --force/-f`);
`git reset --hard`; `git clean`; Edit outside the repo (/tmp, /home, /dev/shm); reading
~/.ssh and ~/.config.

Notes from the file's own comment: deny rules match command text — a guardrail, not a
security boundary; working-directory confinement does the rest;
`blockWritesOutsideWorkingDirectories` is deliberately NOT set (it would disable the lane
worktree tools). There is no `git push` allow rule at all — pushes happen only under
T-015/T-016's explicit gates.

## 10. Uncertain / not checked

- **System node/npm drifted a patch** from the harness pin (live versions in §8's harness
  block vs the node/npm pin in configs/harness.toml). The install happened under the pin;
  both harnesses' --version works on the current node. Whether Step 1 re-pins is a planning
  call.
- **No under-load PCIe check this session** (no GPU work allowed): the live idle reading is
  Gen1 x8, which is the normal idle downshift; the under-load evidence is T-012/T-021's.
- **E-015 C4:** the cut-off table rows the planning chat saw were NOT present in the repo
  file (all named rows verified whole); the truncation happened in the copy it read —
  cause unknown, nothing restored.
- **gh auth status unchecked** (T-015 precondition; no GitHub work this session).
- **wf-loop bugs 2–4** are located by code reading at this HEAD; the loop was not run this
  session. Bug 3's exact trigger (a review session dying mid-final-cycle) is inferred from
  the branch filters, not re-reproduced.
- **Throwaway clones left in /tmp** (`/tmp/local-ai-research-closeout-test/clone-a`,
  `clone-b`, plus the test plans): scratch, safe to delete; clone-a's state.json was
  restored between tests but its last test left T-001 reset — it is a throwaway, not the
  real repo. The real repo's state was never imported/amended.
- **docker/podman absence** verified via PATH only (`command not found`); no exotic
  install location was searched.
- The runbook grand-total addend (docs/runbook-stage3.md:149, 1,578 vs 1,577) is a known
  1 s cosmetic residue, deliberately left for a future docs card (T-022 recon §4).
