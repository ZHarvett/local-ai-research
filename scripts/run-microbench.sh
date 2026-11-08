#!/usr/bin/env bash
# Run the WP6 microbenchmark suite (PCIe, STREAM, NVMe) detached, under the GPU lock.
#
#   scripts/run-microbench.sh [--only pcie,stream,nvme] [--reps N]
#
# Starts `python -m smallpc.microbench` through scripts/run-detached.sh --gpu and prints the job
# directory; follow it with scripts/job-status.sh <job-dir>. Results go to data/microbench/.
# The suite takes the machine for several minutes: close other GPU and memory-heavy programs.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/.." && pwd)"

case "${1:-}" in
  -h | --help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

cd "$repo"
exec "$here/run-detached.sh" --gpu microbench -- \
  uv run --frozen python -m smallpc.microbench "$@"
