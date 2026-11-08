#!/usr/bin/env bash
# List (path and modification time only, never contents) the personal harness directories, so a
# listing taken before the first install can be compared with one taken after the last smoke run.
#
#   scripts/isolation-check.sh list OUTFILE        write the listing (home paths shown as ~)
#   scripts/isolation-check.sh compare A B         exit 0 if the two listings are identical
#   scripts/isolation-check.sh report BEFORE AFTER write the combined report to stdout
#
# Read-only: uses `find -printf` and `test -e`, no file is opened.
set -euo pipefail

paths=(
  "$HOME/.config/opencode"
  "$HOME/.dsh"
  "$HOME/.local/share/opencode"
  "$HOME/.local/state/opencode"
  "$HOME/.cache/opencode"
  "$HOME/.npm"
)

list() {
  local p
  for p in "${paths[@]}"; do
    if [ -e "$p" ] || [ -L "$p" ]; then
      echo "## $p"
      find "$p" -printf '%p\t%T+\n' | LC_ALL=C sort
    else
      echo "## $p"
      echo "DOES NOT EXIST"
    fi
  done | sed "s|$HOME|~|g"
}

case "${1:-}" in
  list)
    [ $# -eq 2 ] || { echo "usage: $0 list OUTFILE" >&2; exit 2; }
    list >"$2"
    echo "wrote $2 ($(wc -l <"$2") lines)"
    ;;
  compare)
    [ $# -eq 3 ] || { echo "usage: $0 compare A B" >&2; exit 2; }
    cmp -s "$2" "$3"
    ;;
  report)
    [ $# -eq 3 ] || { echo "usage: $0 report BEFORE AFTER" >&2; exit 2; }
    echo "# Isolation check: names and modification times only (home paths shown as ~)"
    echo "# Paths: ~/.config/opencode ~/.dsh ~/.local/share/opencode ~/.local/state/opencode"
    echo "#        ~/.cache/opencode ~/.npm"
    echo
    echo "===== BEFORE (taken before the first install or harness execution) ====="
    cat "$2"
    echo
    echo "===== AFTER (taken after the last smoke run) ====="
    cat "$3"
    echo
    if cmp -s "$2" "$3"; then
      echo "===== RESULT: IDENTICAL (before == after, byte for byte) ====="
    else
      echo "===== RESULT: DIFFERENT ====="
      diff "$2" "$3" || true
    fi
    ;;
  *)
    echo "usage: $0 list OUTFILE | compare A B | report BEFORE AFTER" >&2
    exit 2
    ;;
esac
