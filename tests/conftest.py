from __future__ import annotations

import re
import socket
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def plan_version_from_header() -> str:
    """The plan version read straight from the plan header, independent of the code under test.

    Tests assert against this instead of a literal so a plan version bump (e.g. T-011's
    v1.9) does not break them (T-009 S3, decision D4).
    """
    line = (REPO / "docs/plans/step-0-baseline.md").read_text().splitlines()[2]
    m = re.match(r"\*Version (\d+\.\d+)\b", line)
    if not m:
        raise AssertionError(f"cannot read the plan version from line 3: {line!r}")
    return m.group(1)


FIXTURES = REPO / "tests/fixtures"
GOLDEN = REPO / "tests/golden"
EXAMPLES = REPO / "configs/server/examples"
EXAMPLE_NAMES = ["stock-64k", "fit-64k-q8", "cmoe-cache-64k", "mtp-64k"]


@pytest.fixture
def free_port() -> int:
    # Hold the reservation for the whole test: closing it before the server binds leaves a
    # TOCTOU window in which the port can be taken (A13). SO_REUSEPORT lets the mock/fake
    # servers bind alongside it; the reservation never listens, so incoming connections and
    # launch-server.sh's busy check (ss -ltn) only ever see the real server.
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.bind(("127.0.0.1", 0))
        yield s.getsockname()[1]


# The toy task contains one deliberately failing test; it is run only by tests/test_toy_task.py,
# in a scratch copy, never by the main suite.
collect_ignore_glob = ["fixtures/toy-task/*"]
