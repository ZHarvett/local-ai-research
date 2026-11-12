#!/usr/bin/env bash
# workflow-kit bootstrap: install the kit into a target repo.
# Usage: bootstrap.sh <target-repo> [--dry-run] [--force] [--with-hook]
# Never silently overwrites an existing file: differences are reported (diff)
# and skipped unless --force. settings.json is NEVER overwritten (a suggested
# diff is printed). CLAUDE.md is merged via the workflow-kit markers.
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(sed -n 's/^KIT_VERSION = "\(.*\)"$/\1/p' "$KIT_DIR/scripts/_wf.py")"

TARGET=""
DRY_RUN=0
FORCE=0
WITH_HOOK=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
    --with-hook) WITH_HOOK=1 ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) if [ -n "$TARGET" ]; then echo "bootstrap: unexpected argument $arg" >&2; exit 1;
       else TARGET="$arg"; fi ;;
  esac
done
[ -n "$TARGET" ] || { echo "usage: bootstrap.sh <target-repo> [--dry-run] [--force] [--with-hook]" >&2; exit 1; }
[ -d "$TARGET" ] || { echo "bootstrap: no such directory: $TARGET" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"

say() { echo "bootstrap: $*"; }
diff_report() { # <kit-file> <target-file>
  echo "--- diff of $2 against $1 (NOT applied) ---"
  diff -u "$2" "$1" | sed 's/^/| /' || true
  echo "--- end diff ---"
}

# install_file <kit-source> <dest> — copies unless the destination differs
install_file() {
  local src="$1" dest="$2" mode="${3:-644}"
  if [ -e "$dest" ]; then
    if cmp -s "$src" "$dest"; then
      say "skip (identical): ${dest#"$TARGET"/}"
      return 0
    fi
    if [ "$FORCE" -eq 1 ]; then
      say "OVERWRITE (--force): ${dest#"$TARGET"/}"
    else
      say "CONFLICT (exists, differs; not applied — re-run with --force): ${dest#"$TARGET"/}"
      diff_report "$src" "$dest"
      return 0
    fi
  else
    say "add: ${dest#"$TARGET"/}"
  fi
  if [ "$DRY_RUN" -eq 0 ]; then
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
    chmod "$mode" "$dest"
  fi
}

say "target: $TARGET (kit version $VERSION)"
if [ "$DRY_RUN" -eq 1 ]; then say "DRY RUN: nothing is written"; fi

# --- scripts -----------------------------------------------------------------
for f in _wf.py wf.sh wf-card.sh wf-decision.sh wf-escalate.sh wf-guard.sh \
         wf-merge-lanes.sh wf-plan-import.sh wf-progress.sh; do
  mode=644; case "$f" in *.sh|_wf.py) mode=755 ;; esac
  install_file "$KIT_DIR/scripts/$f" "$TARGET/scripts/$f" "$mode"
done

# --- slash commands -----------------------------------------------------------
for f in "$KIT_DIR"/.claude/commands/*.md; do
  install_file "$f" "$TARGET/.claude/commands/$(basename "$f")"
done

# --- docs and workflow templates ----------------------------------------------
install_file "$KIT_DIR/templates/WORKFLOW.md.template" "$TARGET/docs/WORKFLOW.md"
install_file "$KIT_DIR/templates/escalation-brief.md.template" \
  "$TARGET/.workflow/templates/escalation-brief.md"
install_file "$KIT_DIR/templates/review-report.md.template" \
  "$TARGET/.workflow/templates/review-report.md"

# --- config --------------------------------------------------------------------
install_file "$KIT_DIR/config.toml" "$TARGET/.workflow/config.toml"

# --- settings.json (never overwritten) -----------------------------------------
SETTINGS="$TARGET/.claude/settings.json"
if [ -e "$SETTINGS" ]; then
  say "skip settings.json (exists; never overwritten) — suggested additions:"
  diff_report "$KIT_DIR/templates/settings.json.tmpl" "$SETTINGS"
else
  install_file "$KIT_DIR/templates/settings.json.tmpl" "$SETTINGS"
fi

# --- CLAUDE.md marker merge -----------------------------------------------------
CLAUDE="$TARGET/CLAUDE.md"
BLOCK="$KIT_DIR/templates/CLAUDE.md.template"
if [ ! -f "$CLAUDE" ]; then
  say "add: CLAUDE.md (fresh, with workflow-kit markers)"
  [ "$DRY_RUN" -eq 0 ] && cp "$BLOCK" "$CLAUDE"
elif grep -q '<!-- workflow-kit:begin -->' "$CLAUDE"; then
  if python3 - "$CLAUDE" "$BLOCK" <<'PYEOF'
import sys, re
target, block = sys.argv[1], sys.argv[2]
text = open(target, encoding="utf-8").read()
new_block = open(block, encoding="utf-8").read()
merged = re.sub(
    r"<!-- workflow-kit:begin -->.*?<!-- workflow-kit:end -->",
    new_block.strip(), text, flags=re.S)
sys.exit(0 if merged != text else 1)
PYEOF
  then
    if [ "$FORCE" -eq 1 ]; then
      say "CLAUDE.md: marker block replaced (--force)"
      [ "$DRY_RUN" -eq 0 ] && python3 - "$CLAUDE" "$BLOCK" <<'PYEOF'
import sys, re
target, block = sys.argv[1], sys.argv[2]
text = open(target, encoding="utf-8").read()
new_block = open(block, encoding="utf-8").read()
merged = re.sub(
    r"<!-- workflow-kit:begin -->.*?<!-- workflow-kit:end -->",
    new_block.strip(), text, flags=re.S)
open(target, "w", encoding="utf-8").write(merged)
PYEOF
    else
      say "CLAUDE.md: marker block differs from the kit (NOT applied; --force replaces it)"
    fi
  else
    say "CLAUDE.md: marker block already up to date"
  fi
else
  say "CLAUDE.md: no markers — the kit block is APPENDED (the existing content is kept)"
  [ "$DRY_RUN" -eq 0 ] && { printf '\n' >> "$CLAUDE"; cat "$BLOCK" >> "$CLAUDE"; }
fi

# --- CLAUDE.md conflicts (reported, never applied) ------------------------------
if [ -f "$CLAUDE" ] && ! grep -q '<!-- workflow-kit:begin -->' "$CLAUDE" 2>/dev/null; then :; fi
if [ -f "$CLAUDE" ]; then
  echo ""
  echo "== CLAUDE.md conflicts (existing lines that overlap the kit protocol) =="
  echo "The proposed resolution is the marker block appended above; nothing is applied here."
  python3 - "$CLAUDE" <<'PYEOF' || true
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
keywords = [
    (r"session start|every session starts", "session start protocol"),
    (r"progress[- ]log", "progress logging"),
    (r"standard report|§12", "report format"),
    (r"acceptance criterion", "acceptance criteria"),
    (r"escalat", "escalation handling"),
    (r"review", "review protocol"),
    (r"commit message|git commit", "commit conventions"),
    (r"gpu lock|one gpu", "GPU lock rule"),
    (r"sudo", "hard rules (sudo)"),
]
seen = set()
for i, line in enumerate(text.splitlines(), 1):
    for pattern, label in keywords:
        if re.search(pattern, line, re.I) and (i, label) not in seen:
            seen.add((i, label))
            print(f"  line {i:>3} [{label}]: {line.strip()[:90]}")
            break
if not seen:
    print("  (no overlapping lines found)")
PYEOF
fi

# --- .gitignore -------------------------------------------------------------------
GI="$TARGET/.gitignore"
if [ -f "$GI" ] && ! grep -q '^\.workflow/worktrees/' "$GI"; then
  say "gitignore: append '.workflow/worktrees/'"
  [ "$DRY_RUN" -eq 0 ] && printf '\n# workflow-kit lane worktrees\n.workflow/worktrees/\n' >> "$GI"
fi

# --- pre-commit hook (opt-in) -------------------------------------------------------
if [ "$WITH_HOOK" -eq 1 ]; then
  HOOK="$TARGET/.git/hooks/pre-commit"
  if [ -e "$HOOK" ] && ! grep -q wf-guard "$HOOK"; then
    say "skip pre-commit hook (a hook exists without wf-guard; not overwritten)"
  else
    say "add: .git/hooks/pre-commit (runs wf-guard.sh)"
    if [ "$DRY_RUN" -eq 0 ]; then
      mkdir -p "$TARGET/.git/hooks"
      # shellcheck disable=SC2016  # the hook must contain a literal $0
      printf '#!/bin/sh\nexec bash "$(dirname "$0")/../../scripts/wf-guard.sh"\n' > "$HOOK"
      chmod 755 "$HOOK"
    fi
  fi
fi

# --- version + manifest ---------------------------------------------------------------
MANIFEST="$TARGET/.workflow-kit-manifest.json"
if [ "$DRY_RUN" -eq 0 ]; then
  printf 'workflow-kit %s\n' "$VERSION" > "$TARGET/.workflow-kit-version"
  python3 - "$TARGET" "$KIT_DIR" "$VERSION" "$MANIFEST" <<'PYEOF'
import hashlib, json, sys
from pathlib import Path
target, kit = (Path(p) for p in sys.argv[1:3])
version, manifest = sys.argv[3], Path(sys.argv[4])
files = {}
for src, dests in [
    (kit / "scripts", ["scripts/_wf.py", "scripts/wf.sh", "scripts/wf-card.sh",
                       "scripts/wf-decision.sh", "scripts/wf-escalate.sh",
                       "scripts/wf-guard.sh", "scripts/wf-merge-lanes.sh",
                       "scripts/wf-plan-import.sh", "scripts/wf-progress.sh"]),
]:
    for name in dests:
        source = kit / "scripts" / Path(name).name
        files[name] = hashlib.sha256(source.read_bytes()).hexdigest()
for name in sorted((kit / ".claude/commands").glob("*.md")):
    files[f".claude/commands/{name.name}"] = hashlib.sha256(name.read_bytes()).hexdigest()
files["docs/WORKFLOW.md"] = hashlib.sha256((kit / "templates/WORKFLOW.md.template").read_bytes()).hexdigest()
files[".workflow/config.toml"] = hashlib.sha256((kit / "config.toml").read_bytes()).hexdigest()
for t in ("escalation-brief.md", "review-report.md"):
    files[f".workflow/templates/{t}"] = hashlib.sha256(
        (kit / "templates" / f"{t}.template").read_bytes()).hexdigest()
block = (kit / "templates/CLAUDE.md.template").read_bytes()
data = {"version": version, "files": files,
        "claude_block_sha256": hashlib.sha256(block).hexdigest()}
manifest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
PYEOF
  say "wrote .workflow-kit-version and .workflow-kit-manifest.json"
else
  say "would write .workflow-kit-version and .workflow-kit-manifest.json"
fi

say "done"
if [ "$DRY_RUN" -eq 1 ]; then say "(dry run: nothing was written)"; fi
