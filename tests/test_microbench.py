from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from smallpc import microbench as mb

STREAM_OUT = """\
STREAM version $Revision: 5.10 $
Function    Best Rate MB/s  Avg time     Min time     Max time
Copy:           61234.5     0.026115     0.026130     0.026140
Scale:          60111.2     0.026650     0.026620     0.026700
Add:            62500.0     0.038500     0.038400     0.038600
Triad:          62400.9     0.038450     0.038460     0.038480
Solution Validates: avg error less than 1.000000e-13 on all three arrays
"""


def test_parse_stream():
    r = mb.parse_stream(STREAM_OUT)
    assert r["validated"]
    assert r["best_mb_s"] == {"Copy": 61234.5, "Scale": 60111.2, "Add": 62500.0, "Triad": 62400.9}
    assert not mb.parse_stream(STREAM_OUT.replace("Validates", "Fails"))["validated"]


def test_parse_dd():
    txt = (
        "512+0 records in\n512+0 records out\n"
        "8589934592 bytes (8.6 GB, 8.0 GiB) copied, 3.21 s, 2.7 GB/s\n"
    )
    assert mb.parse_dd(txt) == (8589934592, 3.21)
    with pytest.raises(mb.Aborted):
        mb.parse_dd("dd: failed")


def test_stream_source_hash_is_verified(tmp_path, monkeypatch):
    src, man = mb.verify_stream_source()  # the committed file matches its manifest
    assert man["commit"] == "6703f7504a38a8da96b353cadafa64d3c2d7a2d3"
    assert hashlib.sha256(src.read_bytes()).hexdigest() == man["sha256"]
    fake = tmp_path / "tools/stream"
    fake.mkdir(parents=True)
    shutil.copy(src.parent / "MANIFEST.json", fake / "MANIFEST.json")
    (fake / "stream.c").write_text(src.read_text() + "\n// tampered\n")
    monkeypatch.setattr(mb, "ROOT", tmp_path)
    with pytest.raises(mb.Aborted, match="hash mismatch"):
        mb.verify_stream_source()


def test_stream_manifest_records_license_and_source():
    man = json.loads((mb.ROOT / "tools/stream/MANIFEST.json").read_text())
    assert man["source"].endswith("jeffhammond/STREAM") and len(man["sha256"]) == 64
    assert "Run Rules" in man["license"]


def test_theoretical_peak_and_sizes():
    assert mb.DDR5_6000_DUAL_PEAK_GBPS == 96.0
    assert mb.STREAM_ARRAY >= 80_000_000 and mb.STREAM_NTIMES >= 20
    assert mb.NVME_BYTES == 8 * 1024**3
    assert set(mb.STREAM_THREADS) == {8, 16}
    assert all("OMP_PROC_BIND" in v for v in mb.STREAM_THREADS.values())


def test_link_hist():
    rows = [{"pcie_gen": 4.0, "pcie_width": 8.0}] * 3 + [{"pcie_gen": 1.0, "pcie_width": 8.0}]
    assert mb.link_hist(rows) == {"gen4x8": 3, "gen1x8": 1}
    assert mb.link_hist([{"pcie_gen": None, "pcie_width": None}]) == {}


def test_precondition_wait_only_for_load(monkeypatch):
    seq = [
        {"ok": False, "aborts": ["1-minute load average 1.8 is not below 1.5"], "warnings": []},
        {"ok": True, "aborts": [], "warnings": []},
    ]
    monkeypatch.setattr(mb.envsnap, "preconditions", lambda: dict(seq.pop(0)))
    slept = []
    monkeypatch.setattr(mb.time, "sleep", slept.append)
    r = mb.require_preconditions("t")
    assert r["ok"] and slept == [10]
    # any other abort reason is not waited for
    monkeypatch.setattr(
        mb.envsnap,
        "preconditions",
        lambda: {"ok": False, "aborts": ["other GPU compute processes: x"], "warnings": []},
    )
    with pytest.raises(mb.Aborted):
        mb.require_preconditions("t")
    assert slept == [10]
