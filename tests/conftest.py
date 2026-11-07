from __future__ import annotations

import socket
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests/fixtures"
GOLDEN = REPO / "tests/golden"
EXAMPLES = REPO / "configs/server/examples"
EXAMPLE_NAMES = ["stock-64k", "fit-64k-q8", "cmoe-cache-64k", "mtp-64k"]


@pytest.fixture
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
