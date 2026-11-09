#!/usr/bin/env bash
# Start a sweep detached, under the GPU lock and systemd-inhibit (step plan 5.7, WP9).
#
#   scripts/run-sweep.sh <spec.toml> [options]
#
# Options:
#   --resume                  continue the latest unfinished session of this spec (and --only filter)
#   --rerun-flagged <sid>     re-run, once, the repetitions flagged in session <sid> (attempt 2)
#   --only axis=value         run part of the spec as its own session; axes: context, batch
#                             (repeatable, e.g. --only context=32K --only batch=b2048)
#   --session-id ID           session id for a new session (default <spec>[-filters]-<UTC stamp>),
#                             or the session to resume
#   --allow-dirty             start a new session although src/, configs/ or scripts/ have
#                             uncommitted changes (recorded in session.json)
#
# Checks the spec first (`python -m smallpc.sweep check`), refuses a dirty tree for a new session,
# and tests that systemd-inhibit works: if it is refused this stops and reports, it never runs
# unprotected. Then it hands over to scripts/run-detached.sh --gpu, so the runner survives this
# shell, holds the GPU lock for the whole session and is wrapped in
# `systemd-inhibit --what=sleep:idle`. Prints the session id and the job directory.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }

spec="" resume=0 rerun="" sid="" allow_dirty=0
only=()
while [ $# -gt 0 ]; do
  case "$1" in
    --resume) resume=1 ;;
    --rerun-flagged) rerun="${2:?--rerun-flagged needs a session id}"; shift ;;
    --only) only+=("${2:?--only needs axis=value}"); shift ;;
    --session-id) sid="${2:?--session-id needs a value}"; shift ;;
    --allow-dirty) allow_dirty=1 ;;
    -h | --help) usage; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) [ -z "$spec" ] || die "more than one spec given"; spec="$1" ;;
  esac
  shift
done
[ -n "$spec" ] || { usage >&2; exit 2; }
[ -f "$spec" ] || die "no such spec: $spec"
[ "$resume" = 0 ] || [ -z "$rerun" ] || die "--resume and --rerun-flagged are exclusive"

cd "$SMALLPC_REPO"
sweep() { uv run --frozen --quiet python -m smallpc.sweep "$@"; }
only_args=()
for o in "${only[@]+"${only[@]}"}"; do only_args+=(--only "$o"); done

sweep check "$spec" >/dev/null || die "the spec does not check out (see above)"

if [ "$resume" = 0 ] && [ -z "$rerun" ] && [ "$allow_dirty" = 0 ]; then
  dirty="$(git status --porcelain -- src configs scripts)"
  if [ -n "$dirty" ]; then
    echo "$dirty" >&2
    die "uncommitted changes in src/, configs/ or scripts/: commit them, or pass --allow-dirty"
  fi
fi

if [ -n "$rerun" ]; then
  sid="$rerun"
  [ -d "data/raw/$sid" ] || die "no such session: data/raw/$sid"
elif [ "$resume" = 1 ]; then
  if [ -z "$sid" ]; then
    sid="$(sweep latest "$spec" "${only_args[@]+"${only_args[@]}"}")" || die "no unfinished session to resume"
  fi
  [ -d "data/raw/$sid" ] || die "no such session: data/raw/$sid"
else
  if [ -z "$sid" ]; then
    name="$(basename "$spec" .toml)"
    for o in "${only[@]+"${only[@]}"}"; do name="$name-${o//[^A-Za-z0-9]/}"; done
    sid="$name-$(date -u +%Y%m%dT%H%M%SZ)"
  fi
  [ ! -e "data/raw/$sid" ] || die "session already exists: data/raw/$sid (use --resume)"
fi

tag="smallpc-sweep-$sid-$(date +%s)"
if ! systemd-inhibit --what=sleep:idle --who="local-ai-research sweep" --why="$tag (test)" \
  --mode=block true; then
  die "systemd-inhibit was refused: stopping rather than running unprotected"
fi

run_args=(run "$spec" --session-id "$sid" --inhibit-tag "$tag")
[ "$resume" = 0 ] || run_args+=(--resume)
[ -z "$rerun" ] || run_args+=(--rerun-flagged)
[ "$allow_dirty" = 0 ] || run_args+=(--allow-dirty)
run_args+=("${only_args[@]+"${only_args[@]}"}")

mode="sweep"
[ "$resume" = 0 ] || mode="resume"
[ -z "$rerun" ] || mode="rerun"
if [ -n "${SMALLPC_SWEEP_DRY_RUN:-}" ]; then # test hook: print instead of starting a GPU job
  echo "DRY RUN: mode=$mode session=$sid tag=$tag args=${run_args[*]}"
  exit 0
fi
jobdir="$("$here/run-detached.sh" --gpu "$mode-$sid" -- \
  systemd-inhibit --what=sleep:idle --who="local-ai-research sweep" --why="$tag" --mode=block \
  uv run --frozen python -m smallpc.sweep "${run_args[@]}")"
echo "session: $sid"
echo "session dir: data/raw/$sid"
echo "job dir: $jobdir"
echo "status: scripts/sweep-status.sh $sid"
