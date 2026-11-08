from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from smallpc import envsnap

FIX = Path(__file__).parent / "fixtures/telemetry"
GIB = 1024 * 1024


def test_parse_processes_xml_and_classes():
    procs = envsnap.parse_processes_xml((FIX / "nvidia-smi-q.xml").read_text())
    assert [(p["pid"], p["type"], p["vram_mib"]) for p in procs] == [
        (1111, "C", 2048.0),
        (2222, "C+G", 36.0),
        (3333, "G", 55.0),
    ]
    cls = envsnap.classify_processes(procs)
    assert [p["pid"] for p in cls["compute"]] == [1111]
    assert [p["pid"] for p in cls["graphics"]] == [2222, 3333]
    assert envsnap.parse_processes_xml("not xml") == []
    assert (
        envsnap.parse_processes_xml("<nvidia_smi_log><gpu><processes/></gpu></nvidia_smi_log>")
        == []
    )


def test_parse_drm_groups_connected_displays_by_gpu():
    rows = [
        dict(connector="card1-DP-1", card="card1", status="disconnected", vendor="0x10de",
             driver="nvidia", pci="0000:01:00.0"),
        dict(connector="card2-DP-5", card="card2", status="connected", vendor="0x1002",
             driver="amdgpu", pci="0000:0e:00.0"),
        dict(connector="card1-HDMI-A-1", card="card1", status="connected", vendor="0x10de",
             driver="nvidia", pci="0000:01:00.0"),
    ]  # fmt: skip
    d = envsnap.parse_drm(rows)
    assert d["connected_on_nvidia"] == ["card1-HDMI-A-1"]
    assert d["connected_on_amdgpu"] == ["card2-DP-5"]
    assert d["connectors"][0]["connector"] == "card1-DP-1" and d["connectors"][0]["gpu"] == "NVIDIA"


def test_read_drm_from_a_fake_sysfs(tmp_path):
    (tmp_path / "card0-DP-1").mkdir()
    (tmp_path / "card0-DP-1/status").write_text("connected\n")
    dev = tmp_path / "card0/device"
    dev.mkdir(parents=True)
    (dev / "vendor").write_text("0x10de\n")
    rows = envsnap.read_drm(str(tmp_path))
    assert rows[0]["connector"] == "card0-DP-1" and rows[0]["vendor"] == "0x10de"
    assert rows[0]["status"] == "connected"


def test_parse_meminfo():
    mi = envsnap.parse_meminfo((FIX / "meminfo.txt").read_text())
    assert mi["MemAvailable"] == 27316840 and mi["SwapTotal"] - mi["SwapFree"] == 1411372


def test_bracket_choice():
    assert envsnap._bracket("always [madvise] never") == "madvise"
    assert envsnap._bracket("unavailable") == "unavailable"


# ---------------------------------------------------------------- snapshot id


def proc(pid, typ, name, vram):
    return {"pid": pid, "type": typ, "name": name, "vram_mib": vram}


def fake_gpu(**over):
    base = {name: "1" for _, name in envsnap.GPU_QUERY} | {"name": "Test GPU"}
    return base | over


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(envsnap, "gpu_processes", lambda: [])
    monkeypatch.setattr(envsnap, "llama_server_pids", lambda: [])
    monkeypatch.setattr(envsnap, "read_drm", lambda root="/sys/class/drm": [])
    monkeypatch.setattr(envsnap, "gpu_lock_state", lambda root: {"held": False, "file": "x"})


def test_snapshot_id_ignores_volatile_fields(monkeypatch, quiet):
    monkeypatch.setattr(
        envsnap, "gpu_query", lambda i=0: fake_gpu(temperature_c="40", memory_used_mib="2")
    )
    a = envsnap.snapshot()
    monkeypatch.setattr(
        envsnap,
        "gpu_query",
        lambda i=0: fake_gpu(temperature_c="71", memory_used_mib="15000", pstate="P0",
                             pcie_gen_current="4", clock_graphics_mhz="2800"),
    )  # fmt: skip
    b = envsnap.snapshot()
    assert a["snapshot_id"] == b["snapshot_id"] and re.fullmatch(r"[0-9a-f]{16}", a["snapshot_id"])
    assert a["state"]["gpu"]["temperature_c"] == "40" and b["state"]["gpu"]["temperature_c"] == "71"
    assert "temperature_c" not in a["identity"]["gpu"]


def test_snapshot_id_changes_with_identity(monkeypatch, quiet):
    monkeypatch.setattr(envsnap, "gpu_query", lambda i=0: fake_gpu())
    a = envsnap.snapshot()
    monkeypatch.setattr(envsnap, "gpu_query", lambda i=0: fake_gpu(driver_version="999.1"))
    assert envsnap.snapshot()["snapshot_id"] != a["snapshot_id"]
    monkeypatch.setattr(envsnap, "gpu_query", lambda i=0: fake_gpu(power_limit_w="150.00"))
    assert envsnap.snapshot()["snapshot_id"] != a["snapshot_id"]
    monkeypatch.setattr(envsnap, "gpu_query", lambda i=0: fake_gpu())
    monkeypatch.setattr(envsnap, "gpu_processes", lambda: [proc(1, "G", "/usr/bin/x", 5.0)])
    assert envsnap.snapshot()["snapshot_id"] != a["snapshot_id"]  # a new process on the card


def test_snapshot_id_ignores_pids_and_vram_of_processes(monkeypatch, quiet):
    monkeypatch.setattr(envsnap, "gpu_query", lambda i=0: fake_gpu())
    one = [proc(1, "G", "/usr/bin/x", 5.0)]
    two = [proc(77, "G", "/usr/bin/x", 90.0)]
    monkeypatch.setattr(envsnap, "gpu_processes", lambda: one)
    a = envsnap.snapshot()
    monkeypatch.setattr(envsnap, "gpu_processes", lambda: two)
    assert envsnap.snapshot()["snapshot_id"] == a["snapshot_id"]


def test_snapshot_records_the_required_sections(monkeypatch, quiet):
    monkeypatch.setattr(envsnap, "gpu_query", lambda i=0: fake_gpu(memory_used_mib="2"))
    s = envsnap.snapshot()
    idn, st = s["identity"], s["state"]
    keys = ("kernel", "driver_version", "cuda", "cpu", "gpu", "memory_tuning", "llama_cpp")
    keys += ("model", "harnesses", "bios_manual_fields", "display", "desktop_gpu_steering")
    for k in keys:
        assert k in idn
    assert idn["llama_cpp"]["tag"] == "b12208" and len(idn["llama_cpp"]["commit"]) == 40
    assert set(idn["llama_cpp"]["binaries_sha256"]) >= {"llama-server"}
    assert idn["model"]["sha256"] and idn["model"]["revision"]
    assert "igpu" in idn["bios_manual_fields"]
    assert idn["harnesses"]["status"] == "unavailable" or "opencode" in json.dumps(idn["harnesses"])
    for k in ("memory", "gpu_processes", "gpu_lock", "loadavg", "desktop_gpu_steering"):
        assert k in st
    assert st["desktop_gpu_steering"]["memory_used_mib_before_any_server"] == "2"
    for k in ("governor", "epp", "amd_pstate_status", "boost"):
        assert k in idn["cpu"]
    for k in ("swappiness", "thp_enabled"):
        assert k in idn["memory_tuning"]
    assert (
        "swap_used_kib" in st["memory"]
        and "zram_bytes_name_disksize_data_compr_total" in st["memory"]
    )
    assert "pcie_gen_current" in st["gpu"] and "pcie_gen_max" in idn["gpu"]


def test_snapshot_marks_a_running_server(monkeypatch, quiet):
    monkeypatch.setattr(envsnap, "gpu_query", lambda i=0: fake_gpu(memory_used_mib="14000"))
    monkeypatch.setattr(envsnap, "llama_server_pids", lambda: [4242])
    st = envsnap.snapshot()["state"]
    assert st["desktop_gpu_steering"]["memory_used_mib_before_any_server"] is None
    assert st["llama_server_pids"] == [4242]


def test_snapshot_is_scrubbed(monkeypatch, quiet):
    from smallpc.scrub import Identity

    ident = Identity("testuser", "testhost-01", "/home/testuser")
    monkeypatch.setattr(Identity, "current", classmethod(lambda cls: ident))
    monkeypatch.setattr(
        envsnap, "gpu_query", lambda i=0: fake_gpu(name="gpu of testuser on testhost-01")
    )
    monkeypatch.setattr(
        envsnap, "gpu_processes", lambda: [proc(1, "G", "/home/testuser/bin/app", 1.0)]
    )
    text = json.dumps(envsnap.snapshot())
    assert "testuser" not in text and "testhost" not in text and "~/bin/app" in text


# ---------------------------------------------------------------- preconditions


@pytest.fixture
def pre(monkeypatch):
    """A healthy machine; individual tests change one thing."""
    state = {"avail_gib": 26.0, "load": "0.20", "lock_held": False, "procs": [], "servers": [],
             "drm": []}  # fmt: skip

    def fake_read(path):
        if str(path) == "/proc/meminfo":
            return f"MemAvailable: {int(state['avail_gib'] * GIB)} kB\n"
        if str(path) == "/proc/loadavg":
            return f"{state['load']} 0.5 0.5 1/100 1\n"
        return "unavailable"

    monkeypatch.delenv("SMALLPC_GPU_LOCK_HELD", raising=False)
    monkeypatch.setattr(envsnap, "_read", fake_read)
    monkeypatch.setattr(envsnap, "gpu_processes", lambda: state["procs"])
    monkeypatch.setattr(envsnap, "llama_server_pids", lambda: state["servers"])
    monkeypatch.setattr(envsnap, "read_drm", lambda root="/sys/class/drm": state["drm"])
    monkeypatch.setattr(
        envsnap, "gpu_lock_state", lambda root: {"held": state["lock_held"], "file": "x"}
    )
    return state


def test_preconditions_ok(pre):
    r = envsnap.preconditions()
    assert r["ok"] and r["aborts"] == [] and r["warnings"] == []
    assert r["values"]["mem_available_gib"] == 26.0


@pytest.mark.parametrize(
    "gib,ok,warn",
    [(24.0, True, False), (23.9, True, True), (20.0, True, True), (19.9, False, False)],
)
def test_memory_thresholds(pre, gib, ok, warn):
    pre["avail_gib"] = gib
    r = envsnap.preconditions()
    assert r["ok"] is ok
    assert bool(r["warnings"]) is warn
    if not ok:
        assert "MemAvailable" in r["aborts"][0]


@pytest.mark.parametrize(
    "load,ok", [("1.49", True), ("1.50", False), ("3.2", False), ("0.0", True)]
)
def test_load_threshold(pre, load, ok):
    pre["load"] = load
    assert envsnap.preconditions()["ok"] is ok


def test_lock_must_be_free_without_the_wrapper(pre):
    pre["lock_held"] = True
    r = envsnap.preconditions()
    assert not r["ok"] and "GPU lock is held" in r["aborts"][0]


def test_lock_must_be_held_under_the_wrapper(pre, monkeypatch):
    monkeypatch.setenv("SMALLPC_GPU_LOCK_HELD", "123")
    pre["lock_held"] = True
    assert envsnap.preconditions()["ok"]
    pre["lock_held"] = False
    r = envsnap.preconditions()
    assert not r["ok"] and "stale" in r["aborts"][0]
    assert envsnap.preconditions(expect_lock_held_by_wrapper=False)["ok"]


def test_other_compute_processes_abort_graphics_clients_warn(pre):
    pre["procs"] = [{"pid": 9, "type": "C", "name": "/usr/bin/python3", "vram_mib": 100.0}]
    r = envsnap.preconditions()
    assert not r["ok"] and "compute processes" in r["aborts"][0]
    assert envsnap.preconditions(ignore_pids=(9,))["ok"]
    pre["procs"] = [{"pid": 10, "type": "C+G", "name": "/usr/bin/app", "vram_mib": 30.0}]
    r = envsnap.preconditions()
    assert r["ok"] and "display/graphics clients" in r["warnings"][0]


def test_connected_display_on_nvidia_warns_only(pre):
    pre["drm"] = [dict(connector="card1-DP-1", card="card1", status="connected", vendor="0x10de",
                       driver="nvidia", pci="x")]  # fmt: skip
    r = envsnap.preconditions()
    assert r["ok"] and r["warnings"] and r["values"]["connected_on_nvidia"] == ["card1-DP-1"]


def test_running_llama_server_aborts(pre):
    pre["servers"] = [555]
    r = envsnap.preconditions()
    assert not r["ok"] and "llama-server" in r["aborts"][0]


def test_real_lock_probe(tmp_path, monkeypatch):
    monkeypatch.setenv("SMALLPC_GPU_LOCK_FILE", str(tmp_path / "gpu.lock"))
    assert envsnap.gpu_lock_state(tmp_path)["held"] is False
    import fcntl
    import os

    fd = os.open(tmp_path / "gpu.lock", os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert envsnap.gpu_lock_state(tmp_path)["held"] is True
    finally:
        os.close(fd)
    assert envsnap.gpu_lock_state(tmp_path)["held"] is False


def test_llama_server_on_the_card_is_not_part_of_the_machine_state(monkeypatch, quiet):
    monkeypatch.setattr(envsnap, "gpu_query", lambda i=0: fake_gpu())
    a = envsnap.snapshot()["snapshot_id"]
    monkeypatch.setattr(
        envsnap, "gpu_processes", lambda: [proc(5, "C", "/opt/x/llama-server", 14000.0)]
    )
    assert envsnap.snapshot()["snapshot_id"] == a
