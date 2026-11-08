#!/usr/bin/env bash
# Install the pinned harness CLIs (OpenCode, dsh) into third_party/node from the committed lockfile.
#
#   scripts/install-harnesses.sh            npm ci --ignore-scripts (integrity hashes are checked)
#   scripts/install-harnesses.sh --rebuild  run `npm rebuild` for the packages listed in
#                                           configs/harness.toml [rebuild] (install scripts)
#   scripts/install-harnesses.sh --lock [--before TIMESTAMP]
#                                           maintainer mode: resolve with `npm install
#                                           --ignore-scripts --before=TIMESTAMP` (default: exactly
#                                           7 days ago, UTC) and write configs/harness/package-lock.json
#   scripts/install-harnesses.sh --resolve  print the dist-tags and publish times the pinning
#                                           rule uses (metadata only; installs nothing)
#   scripts/install-harnesses.sh --check    check the Node/npm versions only
#
# Everything runs through scripts/_sandbox.sh (bubblewrap, repo-local npm cache and state, empty
# npm user/global config). Nothing is put on PATH and nothing is installed globally.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

node_bin=/usr/bin/node
npm_bin=/usr/bin/npm
prefix="$SMALLPC_REPO/third_party/node"
cfg="$SMALLPC_REPO/configs/harness"
mode="install"
before=""
while [ $# -gt 0 ]; do
  case "$1" in
    --rebuild) mode="rebuild" ;;
    --lock) mode="lock" ;;
    --resolve) mode="resolve" ;;
    --check) mode="check" ;;
    --before) before="${2:?--before needs a value}"; shift ;;
    -h | --help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

npm_sandbox() {
  "$here/_sandbox.sh" --kind npm --npm --rw "$prefix" --cwd "$prefix" "${NPM_SANDBOX_FLAGS[@]}" -- "$@"
}
NPM_SANDBOX_FLAGS=()

# ---- Node >= 22 (dsh declares >= 24.9.0) ----
node_version="$("$node_bin" --version)"
node_version="${node_version#v}"
ver_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]; }
ver_ge "$node_version" 22.0.0 || die "Node $node_version is older than 22"
ver_ge "$node_version" 24.9.0 || die "Node $node_version is older than 24.9.0, which dsh requires"
echo "node $node_version, npm $("$npm_bin" --version)"
[ "$mode" != "check" ] || exit 0

mkdir -p "$prefix"
case "$mode" in
  resolve)
    for pkg in opencode-ai @deepseek-ai/dsh; do
      echo "== $pkg"
      npm_sandbox "$npm_bin" view "$pkg" deprecated dist-tags
      npm_sandbox "$npm_bin" view "$pkg" time --json |
        "$SMALLPC_REPO/.venv/bin/python" -I -c '
import json, sys
d = json.load(sys.stdin)
t = d[-1] if isinstance(d, list) else d
t = t.get("time", t)
for v, ts in sorted(((v, ts) for v, ts in t.items() if v[:1].isdigit()), key=lambda x: x[1])[-6:]:
    print("  ", v, ts)'
    done
    ;;
  lock)
    if [ -z "$before" ]; then before="$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ)"; fi
    echo "resolving with --before=$before"
    cp "$cfg/package.json" "$prefix/package.json"
    rm -f "$prefix/package-lock.json"
    npm_sandbox "$npm_bin" install --ignore-scripts "--before=$before" --prefix "$prefix"
    cp "$prefix/package-lock.json" "$cfg/package-lock.json"
    cp "$prefix/package.json" "$cfg/package.json"
    echo "wrote $cfg/package-lock.json"
    ;;
  install)
    [ -f "$cfg/package-lock.json" ] || die "no lockfile: run with --lock first"
    cp "$cfg/package.json" "$cfg/package-lock.json" "$prefix/"
    npm_sandbox "$npm_bin" ci --ignore-scripts --prefix "$prefix"
    ;;
  rebuild)
    mapfile -t pkgs < <("$SMALLPC_REPO/.venv/bin/python" -I -c '
import sys, tomllib
with open(sys.argv[1], "rb") as f:
    for p in tomllib.load(f).get("rebuild", {}).get("packages", []):
        print(p["name"])' "$SMALLPC_REPO/configs/harness.toml")
    [ "${#pkgs[@]}" -gt 0 ] || { echo "nothing to rebuild"; exit 0; }
    # No network for install scripts: the packages they need are already in node_modules.
    NPM_SANDBOX_FLAGS=(--no-net)
    for p in "${pkgs[@]}"; do
      echo "== npm rebuild $p"
      npm_sandbox "$npm_bin" rebuild "$p" --prefix "$prefix"
    done
    ;;
esac
