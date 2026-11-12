#!/usr/bin/env bash
# workflow-kit: wrapper for wf.sh decision.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/wf.sh" decision "$@"
