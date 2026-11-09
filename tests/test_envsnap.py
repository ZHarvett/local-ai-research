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
    h = idn["harnesses"]
    assert h.get("status") != "unavailable"  # configs/harness.toml exists since WP7
    assert h["opencode"]["pinned_version"] and h["dsh"]["pinned_version"]
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

REAL_WAIT_FOR_IDLE = envsnap.wait_for_idle  # the fixture below stubs the module attribute


@pytest.fixture
def pre(monkeypatch):
    """A healthy machine; individual tests change one thing."""
    state = {"avail_gib": 26.0, "load": "0.20", "lock_held": False, "procs": [], "servers": [],
             "drm": [], "idle_calls": 0, "idle": {"ok": True, "busy_pct": 2.0, "waited_s": 0.0,
             "threshold_busy_pct": 10.0, "loadavg_1m": 0.2}}  # fmt: skip

    def fake_idle():
        state["idle_calls"] += 1
        return dict(state["idle"])

    def fake_read(path):
        if str(path) == "/proc/meminfo":
            return f"MemAvailable: {int(state['avail_gib'] * GIB)} kB\n"
        if str(path) == "/proc/loadavg":
            return f"{state['load']} 0.5 0.5 1/100 1\n"
        return "unavailable"

    monkeypatch.delenv("SMALLPC_GPU_LOCK_HELD", raising=False)
    monkeypatch.setattr(envsnap, "_read", fake_read)
    monkeypatch.setattr(envsnap, "wait_for_idle", fake_idle)
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


def test_load_average_is_recorded_but_is_not_a_gate(pre):
    pre["load"] = "7.5"  # a heavy run just ended: the 1-minute average lags
    r = envsnap.preconditions()
    assert r["ok"] and r["values"]["loadavg_1m"] == 0.2  # the value the idle check recorded


def test_idle_failure_aborts_and_is_recorded(pre):
    pre["idle"] = {"ok": False, "busy_pct": 41.5, "waited_s": 600.0, "threshold_busy_pct": 10.0,
                   "loadavg_1m": 3.0, "error": None}  # fmt: skip
    r = envsnap.preconditions()
    assert not r["ok"]
    assert r["aborts"] == ["CPU not idle: busy 41.5% (limit 10.0%) after waiting 600.0 s"]
    assert r["values"]["idle"]["waited_s"] == 600.0


def test_idle_wait_is_skipped_when_another_check_already_aborted(pre):
    pre["servers"] = [555]
    r = envsnap.preconditions()
    assert not r["ok"] and pre["idle_calls"] == 0
    assert r["values"]["idle"]["skipped"]


# ---------------------------------------------------------------- idle check (plan v1.3)

# /proc/stat "cpu" line: user nice system idle iowait irq softirq steal guest guest_nice
STAT = "cpu  {user} 0 {system} {idle} {iowait} 0 0 {steal} 0 0\ncpu0 1 2 3 4 5 6 7 8 9 10\n"


class FakeMachine:
    """A fake clock plus a fake /proc/stat whose counters advance with the fake time.

    ``busy_by_time`` maps a time range to the busy fraction of that period (100 ticks/s x 8 CPUs
    = 800 jiffies per second in total).
    """

    def __init__(self, schedule):
        self.t = 0.0
        self.schedule = schedule  # list of (until_t, busy_fraction)
        self.reads = 0

    def clock(self):
        return self.t

    def sleep(self, s):
        self.t += s

    def busy_fraction(self, t):
        for until, frac in self.schedule:
            if t < until:
                return frac
        return self.schedule[-1][1]

    def read_stat(self):
        self.reads += 1
        # counters are integrals of the schedule up to now (coarse: 1 s steps are exact enough)
        busy = total = 0.0
        t = 0.0
        while t < self.t:
            dt_ = min(1.0, self.t - t)
            total += 800 * dt_
            busy += 800 * dt_ * self.busy_fraction(t)
            t += dt_
        return STAT.format(
            user=int(busy * 0.8), system=int(busy * 0.2), idle=int((total - busy) * 0.7),
            iowait=int((total - busy) * 0.3), steal=0,
        )  # fmt: skip


def test_parse_cpu_times_counts_idle_and_iowait_as_idle():
    assert envsnap.parse_cpu_times("cpu  100 10 20 700 50 5 6 9 99 99\ncpu0 1 2 3 4\n") == (
        150,
        900,
    )
    assert envsnap.parse_cpu_times("cpu0 1 2 3 4 5 6 7 8\n") is None  # per-CPU lines are not it
    assert envsnap.parse_cpu_times("cpu  1 2 x 4\n") is None
    assert envsnap.parse_cpu_times("") is None
    # old kernels print only four columns
    assert envsnap.parse_cpu_times("cpu 10 0 10 80\n") == (20, 100)


def test_idle_passes_at_once_on_an_idle_machine(monkeypatch):
    m = FakeMachine([(1e9, 0.03)])
    r = envsnap.wait_for_idle(m.read_stat, m.sleep, m.clock)
    assert r["ok"] and r["attempts"] == 1 and r["waited_s"] == 0.0 and r["elapsed_s"] == 10.0
    assert r["busy_pct"] == pytest.approx(3.0, abs=0.1) and r["error"] is None


@pytest.mark.parametrize("frac,ok", [(0.099, True), (0.10, False), (0.15, False)])
def test_idle_threshold_is_below_ten_percent(frac, ok):
    m = FakeMachine([(1e9, frac)])
    r = envsnap.wait_for_idle(m.read_stat, m.sleep, m.clock, max_wait_s=10.0)
    assert r["ok"] is ok


def test_idle_waits_in_ten_second_windows_until_the_cpu_settles():
    m = FakeMachine([(45.0, 0.60), (1e9, 0.02)])  # busy for the first 45 s, then idle
    r = envsnap.wait_for_idle(m.read_stat, m.sleep, m.clock)
    assert r["ok"] and r["attempts"] == 6  # windows 0-10 ... 40-50 (the last one is mostly idle)
    assert r["busy_pct_history"][:4] == [60.0, 60.0, 60.0, 60.0]
    assert r["busy_pct_history"][-1] < 10.0
    assert r["elapsed_s"] == 60.0 and r["waited_s"] == 50.0
    assert m.t == 60.0


def test_idle_gives_up_after_ten_minutes_and_records_the_wait():
    m = FakeMachine([(1e9, 0.50)])
    r = envsnap.wait_for_idle(m.read_stat, m.sleep, m.clock)
    assert not r["ok"] and r["busy_pct"] == pytest.approx(50.0, abs=0.1)
    assert r["elapsed_s"] == 600.0 and r["waited_s"] == 590.0 and r["attempts"] == 60
    assert r["max_wait_s"] == 600.0


def test_idle_aborts_at_once_if_proc_stat_is_unreadable():
    slept = []
    r = envsnap.wait_for_idle(lambda: "unavailable", slept.append, lambda: 0.0)
    assert not r["ok"] and r["attempts"] == 1 and r["error"] and slept == [10.0]


def test_preconditions_runs_the_real_idle_wait_with_fake_time(pre):
    m = FakeMachine([(25.0, 0.80), (1e9, 0.01)])
    r = envsnap.preconditions(idle_check=lambda: REAL_WAIT_FOR_IDLE(m.read_stat, m.sleep, m.clock))
    assert r["ok"] and r["values"]["idle"]["attempts"] == 4
    assert r["values"]["idle"]["waited_s"] == 30.0 and r["values"]["loadavg_1m"] == 0.2
    never = FakeMachine([(1e9, 0.90)])
    r = envsnap.preconditions(
        idle_check=lambda: REAL_WAIT_FOR_IDLE(never.read_stat, never.sleep, never.clock)
    )
    assert not r["ok"] and r["aborts"][0].startswith("CPU not idle: busy 90.0%")
    assert r["values"]["idle"]["waited_s"] == 590.0


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


# ------------------------------------------------------------------ harness versions (WP7)


def _harness_root(tmp_path, installed: dict[str, str]):
    """A fake repo root with a minimal configs/harness.toml and the given installed packages."""
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/harness.toml").write_text(
        """
schema_version = 1
[runtime]
node = "26.13.0"
npm = "12.2.1"
[install]
prefix = "third_party/node"
lockfile_sha256 = "ab"
[plugins]
version = "0.2.1-rc.5"
count = 295
[age_check]
cutoff_utc = "2026-11-01T18:25:11Z"
packages_checked = 643
too_new = 0
[[packages]]
name = "opencode-ai"
version = "1.19.5"
published_utc = "2026-10-28T06:17:11.100Z"
integrity = "sha512-aaa"
[[packages]]
name = "@deepseek-ai/dsh"
version = "0.2.1-rc.5"
published_utc = "2026-10-29T14:15:23.355Z"
integrity = "sha512-bbb"
"""
    )
    for name, version in installed.items():
        d = tmp_path / "third_party/node/node_modules" / name
        d.mkdir(parents=True)
        (d / "package.json").write_text(json.dumps({"name": name, "version": version}))
    return tmp_path


def test_harness_info_reports_pinned_and_installed_versions(tmp_path):
    root = _harness_root(tmp_path, {"opencode-ai": "1.19.5", "@deepseek-ai/dsh": "0.2.1-rc.5"})
    h = envsnap.harness_info(root)
    assert h["node"] == "26.13.0" and h["npm"] == "12.2.1"
    assert h["opencode"]["pinned_version"] == h["opencode"]["installed_version"] == "1.19.5"
    assert h["dsh"]["pinned_version"] == h["dsh"]["installed_version"] == "0.2.1-rc.5"
    assert h["plugins_version"] == "0.2.1-rc.5" and h["age_check"]["too_new"] == 0


def test_harness_info_says_unavailable_not_a_guess(tmp_path):
    assert envsnap.harness_info(tmp_path)["status"] == "unavailable"  # no harness.toml
    root = _harness_root(tmp_path, {"opencode-ai": "1.19.4"})  # dsh missing, opencode drifted
    h = envsnap.harness_info(root)
    assert h["dsh"]["installed_version"] == "unavailable"
    assert h["opencode"]["installed_version"] == "1.19.4" != h["opencode"]["pinned_version"]


def test_harness_info_incomplete_toml_is_unavailable(tmp_path):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/harness.toml").write_text("[runtime]\nnode = '1'\n")
    assert envsnap.harness_info(tmp_path)["status"] == "unavailable"
