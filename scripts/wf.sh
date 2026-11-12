#!/usr/bin/env bash
# workflow-kit dispatcher: wf.sh <subcommand> [args...]
# Installed by bootstrap.sh as scripts/wf.sh beside _wf.py.
# Run `wf.sh --help` (or `wf.sh` with no subcommand) for the subcommand list.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/_wf.py" "$@"
