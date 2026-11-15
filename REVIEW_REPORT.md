# Review T-013 (cycle 1)

## Model

qwen4-max-preview (the config records a single model for executor and reviewer; the same
model executed this work, so everything below was re-derived independently, not trusted).

## Acceptance verdicts

Re-ran `bash scripts/wf.sh accept T-013` myself (recorded as run 2, 0 failures), plus a
direct `bash scripts/release-check.sh` and an independent blob-level history scan that does
not use the script's diff parsing. No archived reports existed (reviews/T-013 absent —
first cycle). Light task, no measurement session in progress; nothing deferred.

| item | verdict | note |
|---|---|---|
| A1 | PASS | exit 0. a) 0 findings in 4,564 files; b) 312 commits, 6 known finding lines, 0 beyond the allowlist, exactly the four named pairs; c) 127 / 795 / 68 numbers verified (README.md, reports/baseline-report.md, reports/writeup.md); d) no TODO-T010 in the four publication docs; e) both licences exist. Counts consistent with the report: 307 commits at run-1 base `4e5ba57`, 310 at run-2 base `4c273b4` (both re-derived with `git rev-list --count`), 312 at HEAD (+2 commits, neither adds findings). |
| A2 | PASS | `shellcheck scripts/release-check.sh` exit 0, no output (accept run 2). |
| A3 | PASS | docs/recon/scrub-report.md exists; sha256 `f794bea664b0…` and scripts/release-check.sh `b7569acca588…` both match the acceptance record and the working tree (unchanged since `158078b`; the done commit `e8395cd` touched only kit state and the progress log). |
| A4 | PASS | Judgement re-derived independently — see below. |

**A4 re-derivation.** Scanned every reachable blob (2,119 blobs, 56.6 MB, via
`git rev-list --objects --all` + `git cat-file --batch`), every commit's full metadata via
`cat-file commit` (312 commits — independent of the script's `git log --format`), and all 15
dangling objects (14 commits + 1 blob, `git fsck --dangling --no-reflogs`, including their
dangling-only blobs), at bytes level with the scrub module's own patterns
(`smallpc.scrub._patterns(Identity.current())`). Result:

- Exactly **2 distinct matched lines** (masked) in the entire reachable object store: the
  WP0 ownership line in docs/decisions.md (2 blob versions — the line persisted unchanged
  across intermediate file versions) and the claude-CLI home-path line in
  docs/recon/loop-states.md (1 blob version). **0 binary-blob findings** (the module's
  binary skip has no actual exposure), **0 commit-metadata findings** (author, committer,
  email, message), **0 findings in the HEAD tree repo-wide** (stronger than check (a)'s
  publication paths — D8's "no committed file" rule holds at HEAD), **0 findings in
  dangling-only blobs or dangling commit metadata**.
- The script's four commit×path pairs are exactly the introduction/removal boundaries of
  these two occurrences, verified by masked `git show` of each: `26faadd` adds the
  ownership line; `dfcd7d9` removes it and adds the literal `<user>:<user>` replacement;
  `3f41e18` adds the home-path line; `bc8e0c3` removes it. The "6 known finding lines" are
  6 kind-hits on 4 physical lines (the loop-states line matches both home-path and
  username), matching the report's per-kind breakdown.
- Allowlist = four full 40-char-hash commit×path pairs (hashes verified with
  `git rev-parse`), each named in a recorded decision: D8 (docs/decisions.md:1206) for
  `26faadd`; E-006 rule 4 follow-up (docs/decisions.md:1264) for `3f41e18` and `bc8e0c3`;
  DECISION E-014 option A (docs/decisions.md:1365–1372) for `dfcd7d9`. No string, pattern,
  whole-path or whole-commit allowance. E-014's scope ("exactly one more pair … any further
  pair … stops T-013") is honoured.
- Script parsing assumptions re-verified: 0 historical paths containing space, quote,
  backslash or " b/"; 0 commit-message lines that could misparse as commit or diff headers.
  The `--cc` merge-coverage argument is sound (every line of every tree appears in the
  introducing commit's diff or an evil-merge combined diff), and the blob scan confirms it
  empirically; merge `6d66103` carries only the already-allowlisted loop-states blob, per
  the E-014 decision.
- The report contains no matched values: the HEAD-tree pattern scan covers it, and its one
  quotation is masked (cosmetic inexactness only — F-1).

The executor's report and my re-run agree on every number re-derived. No mismatch.

## Findings

| id | severity | action | evidence | required action |
|---|---|---|---|---|
| F-1 | NOTE | FIX-DOC | docs/recon/scrub-report.md:51 (same quote in escalations/E-014.md:24, archived) | The masked quote of the removed line drops the four markdown backticks the real line carries. Actual masked line: ``  `/mnt/data` is owned by `<user>:<user>` (mode 755), so no sudo was needed.`` No PII impact; substance (removed line, same path, username kind) correct. Optional one-line quote fix; may ride with T-014's deviations write-up. Leave the archived brief as the historical record. Not gating. |
| F-2 | NOTE | NONE | `git fsck --dangling --no-reflogs` (15 objects); independent scan above | "Every commit" in check (b) means every ref-reachable commit — the card's own example method (`git log -p --all`). 14 dangling commits + 1 dangling blob (kit worktree/merge residue) sit outside `--all`; I scanned them: 0 findings. Push-based publication transfers only reachable objects. If T-015/T-016 ever publish a raw `.git` archive, re-scan dangling objects first. Recorded for the release tail; no T-013 action. |
| F-3 | NOTE | NONE | scripts/release-check.sh:109–120; docs/recon/scrub-report.md:19; PLAN.md:540 | Check (d) is scoped to T-010's acceptance scope (README.md, baseline-report.md, writeup.md) plus CHANGELOG.md. A repo-wide reading of card (d) is self-contradictory: PLAN.md's card text and the append-only progress log legitimately contain the marker. Verified 0 markers in the four publication files; every other occurrence is plan/kit/history/review text. Documented in the script comment and the report. No action. |

## Task verdict

accepted

## What I did not verify

- Case-insensitive or alternate spellings of the identity strings: the scrub module's
  patterns are case-sensitive and are the card-named reference; the capitalized author
  name is public per D8. I did not audit the module's pattern design (frozen code, out of
  T-013's scope).
- The exact run-1 file count (4,563) at `4e5ba57` — not re-derived by checkout; consistent
  with scrub-report.md being the +1 file at run 2 (4,564, re-derived).
- tools/check_doc_numbers.py beyond its exit-code contract (`return 1` on failure
  verified): I re-ran it; its parser and the semantic correctness of the doc numbers are
  T-005/T-010's reviewed scope, not re-audited here.
- Reflog entries themselves (reflog-only objects are reported dangling by
  `fsck --no-reflogs` and were scanned; the reflogs were not enumerated).
- `.workflow/state.json` internals beyond `wf-guard.sh` OK and the accept record;
  kit-managed state, never hand-edited (bookkeeping commits are kit-labelled).
- T-015/T-016's actual publication method (future tasks) — F-2's archive caveat is
  conditional on it.
- The executor's chat reasoning (not available to the reviewer, per protocol).
- No GPU or heavy work was needed or run (light task).
