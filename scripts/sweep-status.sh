#!/usr/bin/env bash
# Show the state of a sweep session: cells done and remaining, the current cell and phase, an
# estimated time to finish, the flags so far and the last error.
#
#   scripts/sweep-status.sh [session-id | --latest] [--json]
#
# Without a session id the most recently started session is shown. Read-only.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$here/_common.sh"

case "${1:-}" in
  -h | --help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

cd "$SMALLPC_REPO"
exec uv run --frozen --quiet python -m smallpc.sweep status "$@"
