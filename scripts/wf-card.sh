#!/usr/bin/env bash
# workflow-kit: print the shared rules block plus ONE task card (wf.sh card).
# Usage: scripts/wf-card.sh T-001
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/wf.sh" card "$@"
