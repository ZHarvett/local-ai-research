# T-013 scrub and release checks — run 1 (2026-11-15)

Script: `scripts/release-check.sh` (read-only, shellcheck-clean). Run from the repo root at
commit `4e5ba57` plus the uncommitted T-013 S1 script. Identity for the scrub patterns is read
live at run time (`smallpc.scrub.Identity.current()`); kinds checked: home-path, username,
hostname. This report records counts and locations only, never matched values.

## Result: exit 1 — one history finding beyond the allowlist (escalated, E-014)

| Check | Result | Evidence |
|---|---|---|
| a) scrub, publication paths | PASS | 0 findings in 4,563 files (`data reports docs configs README.md CHANGELOG.md CLAUDE.md`; SCRUB_CMD from `docs/recon/commands.env` with the extra paths appended) |
| b) full-history scan | FAIL | 307 commits; 5 known finding lines; 1 line beyond the allowlist (below) |
| c) doc numbers | PASS | README.md 127 numbers / 65 sources; reports/baseline-report.md 795 / 57; reports/writeup.md 68 / 7 (`tools/check_doc_numbers.py`, exit 0 each) |
| d) TODO-T010 placeholders | PASS | 0 in README.md, CHANGELOG.md, reports/baseline-report.md, reports/writeup.md (T-010 acceptance scope plus CHANGELOG.md; PLAN.md, `.workflow/` and the append-only progress log mention the marker legitimately as history) |
| e) licences | PASS | LICENSE and LICENSE-DATA.md exist |

## History scan method

`git log -p --cc --all --no-color` with a custom format that also exposes author and committer
name/email and the full commit message, scanned line by line with the scrub module's own
patterns (`smallpc.scrub._patterns`). `--all` covers every ref (main, lane-2, lane-3; 307
commits, no stash). Every non-merge commit's full diff is scanned; for merges the dense
combined diff (`--cc`) shows any content differing from ALL parents, so every line of every
path in every commit tree is covered (content equal to a parent is covered by that parent's
own diff). Binary files show no content, matching the scrub module's binary skip. No path in
the history contains a space (checked), so diff-header path parsing is unambiguous.

## Allowlist (by commit and path, never by string — D8)

| Commit | Path | Authority |
|---|---|---|
| `26faadd` (WP0: bootstrap repository) | docs/decisions.md | D8: the WP0 occurrence |
| `3f41e18` (T-017 S1–S2 recon) | docs/recon/loop-states.md | E-006 rule 4 follow-up, docs/decisions.md |
| `bc8e0c3` (T-017 address review, F-2 fix) | docs/recon/loop-states.md | E-006 rule 4 follow-up, docs/decisions.md |

Known finding lines (5): `26faadd` docs/decisions.md username ×1; `3f41e18`
docs/recon/loop-states.md home-path ×1, username ×1; `bc8e0c3` docs/recon/loop-states.md
home-path ×1, username ×1.

## Finding beyond the allowlist (1 line)

- `dfcd7d9` ("WP3: record desktop GPU steering", 2026-11-08), path `docs/decisions.md`,
  kind=username, 1 line. It is a **removed** line: `dfcd7d9` is the commit that scrubbed the
  WP0 occurrence — it deletes the `/mnt/data` ownership line carrying the raw account name
  (added by `26faadd`) and adds the `<user>:<user>` replacement. Masked, the removed line is:
  `-  /mnt/data is owned by <user>:<user> (mode 755), so no sudo was needed.`
  It is the removal-side counterpart of the allowlisted WP0 occurrence (same string, same
  path), but no decision names `dfcd7d9`: D8 names "the WP0 commit(s)" and the E-006 rule 4
  follow-up names only `3f41e18` and `bc8e0c3`. Escalated under card S3 as E-014; the script's
  allowlist is NOT extended without a recorded decision.

Method note: the lane-3 merge `6d66103` carries the allowlisted loop-states.md content, but a
clean merge shows no combined diff, so it is not flagged — the same behaviour as the card's
plain `git log -p --all` example and the `git log -S` method used by the E-006 rule 4
follow-up. A per-parent merge scan (`-m`) would additionally flag `6d66103` ×
docs/recon/loop-states.md; `--cc` was chosen because it also covers merge-introduced (evil
merge) content while matching the allowlist's commit set.

## Working tree

The current tree is clean: check (a) found 0 findings in 4,563 files. The single history
finding is a removal (a scrub fix), not new exposure; the account name is the one D8 already
accepts as public (it matches the author name on every commit).
