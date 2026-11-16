#!/usr/bin/env bash
# T-013: read-only scrub and release checks. Exit 0 only if ALL checks pass:
#   a) scrub check over the publication paths (SCRUB_CMD, docs/recon/commands.env)
#   b) every commit and every path in the history, with the scrub module's own
#      patterns; findings allowlisted by commit and path only (D8; E-006 rule 4)
#   c) tools/check_doc_numbers.py on README.md, reports/baseline-report.md,
#      reports/writeup.md
#   d) no TODO-T010 placeholders in the publication paths
#   e) LICENSE and LICENSE-DATA.md exist
# Prints locations only, never matched values. Writes nothing.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

fails=0
pass() { printf 'PASS: %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*"; fails=$((fails + 1)); }

# --- a) working-tree scrub check -------------------------------------------
# SCRUB_CMD already carries "--check data reports docs"; the remaining
# publication paths from card T-013 are appended.
# shellcheck source=/dev/null
source docs/recon/commands.env
if eval "$SCRUB_CMD configs README.md CHANGELOG.md CLAUDE.md"; then
    pass "a) scrub check: data reports docs configs README.md CHANGELOG.md CLAUDE.md"
else
    fail "a) scrub check found findings (locations above)"
fi

# --- b) full-history scan ---------------------------------------------------
# git log -p --cc --all: every non-merge commit's full diff plus every merge's
# dense combined diff (content differing from ALL parents), so every line of
# every path in every commit tree is covered; commit metadata (author and
# committer name/email, full message) is scanned via the custom format.
# Binary files show no content, matching the scrub module's binary skip.
# The allowlist is by commit and path, never by the matched string (D8):
#   174edac  WP0 occurrence in docs/decisions.md (D8)
#   326f866  removal side of the WP0 occurrence, same path (D8; E-014 option A)
#   88854e0, 40e8669  docs/recon/loop-states.md introduction and fix
#   (E-006 rule 4 follow-up, recorded in docs/decisions.md)
if hist_out="$(uv run python - <<'PY'
import re
import subprocess
import sys

from smallpc.scrub import Identity, _patterns

ALLOW = {
    ("174edac7563f2bd3e950a514640ca71ee466f28f", "docs/decisions.md"),
    # removal side of the WP0 occurrence (D8; DECISION E-014 option A)
    ("326f866c78f5b47ff796fefc96626c6e4931d92f", "docs/decisions.md"),
    ("88854e03aca554759ae66a32a8b5d7493d85c95f", "docs/recon/loop-states.md"),
    ("40e8669d5f3babf2f5386b310966c01f92109fba", "docs/recon/loop-states.md"),
}

pats = _patterns(Identity.current())
commits = set(
    subprocess.run(["git", "rev-list", "--all"], capture_output=True, text=True, check=True).stdout.split()
)
fmt = "commit %H%nAuthor: %an <%ae>%nCommitter: %cn <%ce>%n%B"
proc = subprocess.run(
    ["git", "log", "-p", "--cc", "--all", "--no-color", f"--format={fmt}"],
    capture_output=True, text=True, check=True,
)
commit, path = None, "<commit-metadata>"
known, extra = {}, {}
for line in proc.stdout.splitlines():
    m = re.fullmatch(r"commit ([0-9a-f]{40})", line)
    if m and m.group(1) in commits:
        commit, path = m.group(1), "<commit-metadata>"
        continue
    if line.startswith("diff --git "):
        # no path in the history contains a space (checked 2026-11-15)
        path = line.split(" b/", 1)[-1]
        continue
    if line.startswith(("diff --cc ", "diff --combined ")):
        path = line.split(" ", 2)[-1]
        continue
    for kind, pat, _ in pats:
        if pat.search(line):
            key = (commit, path, kind)
            bucket = known if (commit, path) in ALLOW else extra
            bucket[key] = bucket.get(key, 0) + 1

print(f"history scan: {len(commits)} commits; known finding lines: {sum(known.values())}; "
      f"beyond allowlist: {sum(extra.values())}")
for (c, p, k), n in sorted(known.items()):
    print(f"known: {c[:7]} {p} kind={k} lines={n}")
for (c, p, k), n in sorted(extra.items()):
    print(f"EXTRA: {c[:7]} {p} kind={k} lines={n}")
sys.exit(1 if extra else 0)
PY
)"; then
    printf '%s\n' "$hist_out"
    pass "b) history scan: nothing beyond the allowlist"
else
    printf '%s\n' "$hist_out"
    fail "b) history scan found findings beyond the allowlist (locations above)"
fi

# --- c) doc number checks ----------------------------------------------------
for doc in README.md reports/baseline-report.md reports/writeup.md; do
    if uv run python tools/check_doc_numbers.py "$doc"; then
        pass "c) doc numbers: $doc"
    else
        fail "c) doc numbers: $doc"
    fi
done

# --- d) TODO-T010 placeholders ----------------------------------------------
# The publication docs only (T-010's acceptance scope, plus CHANGELOG.md):
# PLAN.md, .workflow/ and the append-only docs/progress-log.md mention
# TODO-T010 legitimately as plan text, recorded commands and history.
# git grep exit 1 = no match.
if git grep -nI "TODO-T010" -- README.md CHANGELOG.md reports/baseline-report.md reports/writeup.md; then
    fail "d) TODO-T010 placeholders remain (locations above)"
elif [ "$?" -eq 1 ]; then
    pass "d) no TODO-T010 placeholders in publication paths"
else
    fail "d) git grep errored"
fi

# --- e) licences --------------------------------------------------------------
for f in LICENSE LICENSE-DATA.md; do
    if [ -f "$f" ]; then
        pass "e) $f exists"
    else
        fail "e) $f missing"
    fi
done

if [ "$fails" -eq 0 ]; then
    echo "release-check: all checks PASS"
    exit 0
fi
echo "release-check: $fails check(s) FAILED"
exit 1
