#!/usr/bin/env bash
# workflow-kit sync: update the kit-owned files in a repo bootstrap installed.
# Usage: sync.sh <target-repo> [--force]
# A kit file that was locally modified after installation is NOT overwritten
# without --force (its recorded manifest hash no longer matches).
# .claude/settings.json and CLAUDE.md outside the marker block are never touched.
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET=""
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) if [ -n "$TARGET" ]; then echo "sync: unexpected argument $arg" >&2; exit 1;
       else TARGET="$arg"; fi ;;
  esac
done
[ -n "$TARGET" ] || { echo "usage: sync.sh <target-repo> [--force]" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"
MANIFEST="$TARGET/.workflow-kit-manifest.json"
[ -f "$MANIFEST" ] || { echo "sync: $TARGET has no .workflow-kit-manifest.json (bootstrap first)" >&2; exit 1; }

say() { echo "sync: $*"; }

python3 - "$TARGET" "$KIT_DIR" "$FORCE" <<'PYEOF'
import hashlib, json, sys
from pathlib import Path

target, kit, force = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] == "1"
manifest = json.loads((target / ".workflow-kit-manifest.json").read_text())
kit_sources = {
    "scripts/_wf.py": kit / "scripts/_wf.py",
    "scripts/wf.sh": kit / "scripts/wf.sh",
    "scripts/wf-card.sh": kit / "scripts/wf-card.sh",
    "scripts/wf-decision.sh": kit / "scripts/wf-decision.sh",
    "scripts/wf-escalate.sh": kit / "scripts/wf-escalate.sh",
    "scripts/wf-guard.sh": kit / "scripts/wf-guard.sh",
    "scripts/wf-merge-lanes.sh": kit / "scripts/wf-merge-lanes.sh",
    "scripts/wf-plan-import.sh": kit / "scripts/wf-plan-import.sh",
    "scripts/wf-progress.sh": kit / "scripts/wf-progress.sh",
    "docs/WORKFLOW.md": kit / "templates/WORKFLOW.md.template",
    ".workflow/config.toml": kit / "config.toml",
    ".workflow/templates/escalation-brief.md": kit / "templates/escalation-brief.md.template",
    ".workflow/templates/review-report.md": kit / "templates/review-report.md.template",
}
for name in sorted((kit / ".claude/commands").glob("*.md")):
    kit_sources[f".claude/commands/{name.name}"] = name


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


problems = 0
written = {}
for dest, source in sorted(kit_sources.items()):
    installed = target / dest
    recorded = manifest["files"].get(dest)
    if recorded is None:
        print(f"sync: {dest} is not in the manifest (kit layout changed?); skipping")
        continue
    if not installed.exists():
        import shutil
        installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, installed)
        if dest.startswith("scripts/"):
            installed.chmod(0o755)
        print(f"sync: added (was missing): {dest}")
        written[dest] = sha(installed)
        continue
    current = sha(installed)
    if current == sha(source):
        print(f"sync: up to date: {dest}")
        continue
    if current != recorded:
        if not force:
            print(
                f"sync: REFUSED (locally modified): {dest} — recorded hash no longer "
                f"matches; re-run with --force to discard local changes"
            )
            problems += 1
            continue
        print(f"sync: --force over locally modified {dest}")
    installed.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copyfile(source, installed)
    if dest.startswith("scripts/"):
        installed.chmod(0o755)
    print(f"sync: updated: {dest}")
    written[dest] = sha(installed)

# CLAUDE.md marker block
block = (kit / "templates/CLAUDE.md.template").read_text(encoding="utf-8").strip()
block_hash = hashlib.sha256(block.encode()).hexdigest()
claude = target / "CLAUDE.md"
if claude.is_file():
    text = claude.read_text(encoding="utf-8")
    if "<!-- workflow-kit:begin -->" not in text:
        print("sync: CLAUDE.md has no markers (bootstrap appends them); skipping")
    else:
        import re
        current_block = re.search(
            r"<!-- workflow-kit:begin -->.*?<!-- workflow-kit:end -->", text, re.S
        )
        if current_block and current_block.group(0).strip() == block:
            print("sync: CLAUDE.md marker block up to date")
        else:
            merged = re.sub(
                r"<!-- workflow-kit:begin -->.*?<!-- workflow-kit:end -->",
                block, text, flags=re.S)
            claude.write_text(merged, encoding="utf-8")
            print("sync: CLAUDE.md marker block updated")
else:
    print("sync: no CLAUDE.md (skipping)")

# refresh the manifest hashes ONLY for files this run actually wrote
manifest["files"] = {**manifest.get("files", {}), **written}
manifest["claude_block_sha256"] = block_hash
(target / ".workflow-kit-manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n")

settings = target / ".claude/settings.json"
if settings.is_file():
    tmpl = kit / "templates/settings.json.tmpl"
    if settings.read_text(encoding="utf-8") != tmpl.read_text(encoding="utf-8"):
        print("sync: settings.json differs from the template (never touched; "
              "compare with templates/settings.json.tmpl yourself)")
sys.exit(1 if problems else 0)
PYEOF
