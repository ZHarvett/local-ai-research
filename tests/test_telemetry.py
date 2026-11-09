from __future__ import annotations

import os
import stat
import textwrap
from pathlib import Path

import pytest

from smallpc import telemetry as tm

FIX = Path(__file__).parent / "fixtures/telemetry"


def fixture_rows():
    lines = (FIX / "nvidia-smi.csv").read_text().splitlines()
    return lines[0], [tm.parse_nvsmi_row(line) for line in lines[1:]]


def test_header_matches_the_requested_fields():
    header, _ = fixture_rows()
    names = [h.split(" [")[0].strip() for h in header.split(",")]
    assert names == [f for f, _, _ in tm.GPU_FIELDS]
    assert tm.parse_nvsmi_row(header) is None
    assert tm.parse_nvsmi_row("") is None and tm.parse_nvsmi_row("1, 2, 3") is None


def test_vmswap_is_parsed_from_proc_status():
    base = (FIX / "proc_status.txt").read_text()
    assert tm.parse_status_vmswap_kib(base) is None  # the older excerpt has no VmSwap line
    assert tm.parse_status_vmswap_kib(base + "VmSwap:\t       0 kB\n") == 0
    assert tm.parse_status_vmswap_kib(base + "VmSwap:\t  204800 kB\n") == 204800
    assert tm.parse_status_vmswap_kib("VmSwap:\tgarbage\n") is None
    assert "server_vmswap_kib" in tm.COLUMNS and "server_vmswap_kib" in tm._FLOAT_COLS


def test_every_clock_event_reason_is_collected():
    cols = {c for _, c, _ in tm.GPU_FIELDS}
    for need in (
        "reason_hw_slowdown",
        "reason_hw_thermal_slowdown",
        "reason_sw_thermal_slowdown",
        "reason_sw_power_cap",
        "reason_hw_power_brake_slowdown",
        "reason_gpu_idle",
        "reason_applications_clocks",
        "reason_sync_boost",
        "reason_board_limit",
        "reason_reliability",
    ):
        assert need in cols
    assert tm.COLUMNS[:3] == ["t_epoch", "t_utc", "t_rel_s"]


def test_parse_loaded_idle_and_na_rows():
    _, (load, idle, na) = fixture_rows()
    assert load["gpu_util_pct"] == 93.0 and load["gpu_mem_used_mib"] == 14972.0
    assert load["gpu_power_w"] == 150.23 and load["gpu_pstate"] == "P0"
    assert (load["pcie_gen"], load["pcie_width"]) == (4.0, 8.0)
    assert load["reason_sw_power_cap"] is True and load["reason_hw_slowdown"] is False
    assert idle["pcie_gen"] == 1.0 and idle["reason_gpu_idle"] is True
    assert na["gpu_util_pct"] is None and na["gpu_power_w"] is None
    assert na["reason_hw_slowdown"] is True and na["reason_hw_thermal_slowdown"] is True


def test_hwmon_tctl_found_by_name_and_label():
    d = FIX / "hwmon"
    assert tm.find_k10temp(str(d)) == d / "hwmon3"
    assert tm.tctl_input_path(d / "hwmon3") == d / "hwmon3/temp1_input"
    assert tm.find_k10temp(str(d / "hwmon0")) is None
    assert tm.tctl_input_path(None) is None
    files = {p.name: p.read_text() for p in (d / "hwmon3").iterdir()}
    assert tm.parse_hwmon_temp(files["name"], files) == 44.25
    assert tm.parse_hwmon_temp("nvme", files) is None
    del files["temp1_label"]
    assert tm.parse_hwmon_temp("k10temp", files) is None


def test_hwmon_number_does_not_matter(tmp_path):
    root = tmp_path / "hwmon"
    for n, (name, lab, val) in {
        17: ("nvme", "Composite", 30000),
        2: ("k10temp", "Tctl", 61500),
    }.items():
        d = root / f"hwmon{n}"
        d.mkdir(parents=True)
        (d / "name").write_text(name + "\n")
        (d / "temp1_label").write_text(lab + "\n")
        (d / "temp1_input").write_text(f"{val}\n")
    d = tm.find_k10temp(str(root))
    assert d.name == "hwmon2"
    assert int((tm.tctl_input_path(d)).read_text()) == 61500


def test_proc_parsers():
    stat_txt = (FIX / "proc_stat_llama.txt").read_text()  # comm contains spaces and parentheses
    assert tm.parse_proc_stat_majflt(stat_txt) == 2047
    assert tm.parse_proc_stat_cpu_ticks(stat_txt) == 5300
    assert tm.parse_proc_stat_majflt("garbage") is None
    assert tm.parse_status_rss_kib((FIX / "proc_status.txt").read_text()) == 6710886
    assert tm.parse_status_rss_kib("Name: x\n") is None
    vm = (FIX / "vmstat.txt").read_text()
    assert tm.parse_vmstat(vm) == 75641 and tm.parse_vmstat(vm, "pgmajfault") == 90777
    assert tm.parse_vmstat(vm, "nope") is None
    assert tm.parse_meminfo_kib((FIX / "meminfo.txt").read_text()) == 27316840


def test_read_pid_from_arg_or_pidfile(tmp_path):
    pf = tmp_path / "server.pid"
    assert tm.read_pid(None, pf) is None
    pf.write_text("1234\n")
    assert tm.read_pid(None, pf) == 1234
    assert tm.read_pid(99, pf) == 99


def test_nvidia_smi_command_is_one_long_running_process():
    cmd = tm.nvidia_smi_cmd()
    assert cmd[0] == "nvidia-smi" and cmd[-2:] == ["-lms", "500"]
    assert "--format=csv,nounits" in cmd
    assert any(a.startswith("--query-gpu=utilization.gpu,") for a in cmd)


FAKE_SMI = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    cat <<'EOF'
    {header}
    EOF
    for i in 1 2 3 4 5 6; do
      echo "{row}"
      sleep 0.1
    done
    sleep 30
    """
)


def test_sampler_with_fake_nvidia_smi(tmp_path, monkeypatch):
    header = (FIX / "nvidia-smi.csv").read_text().splitlines()
    fake = tmp_path / "bin/nvidia-smi"
    fake.parent.mkdir()
    fake.write_text(FAKE_SMI.format(header=header[0], row=header[1]))
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{fake.parent}:{os.environ['PATH']}")
    pidfile = tmp_path / "pid"
    pidfile.write_text(str(os.getpid()))
    out = tmp_path / "s.csv"
    import time

    with tm.Sampler(out, pidfile=pidfile) as s:
        time.sleep(1.0)
    assert len(s.rows) == 6
    rows = tm.read_csv(out)
    assert len(rows) == 6 and list(rows[0].keys()) == tm.COLUMNS
    assert rows[0]["gpu_util_pct"] == 93.0 and rows[0]["reason_sw_power_cap"] is True
    assert rows[0]["server_rss_kib"] > 0 and rows[0]["majflt"] is not None
    assert rows[0]["memavailable_kib"] > 0
    assert rows[0]["server_vmswap_kib"] is not None  # VmSwap is sampled from /proc/<pid>/status
    assert rows[-1]["t_epoch"] > rows[0]["t_epoch"]
    oh = s.overhead()
    assert oh["n_rows"] == 6 and oh["python_core_fraction"] < 0.5
    assert s._proc is None


def test_csv_roundtrip_window_and_evaluate(tmp_path):
    rows = []
    for i in range(10):
        r = dict.fromkeys(tm.COLUMNS)
        r.update(t_epoch=100.0 + i * 0.5, gpu_util_pct=90.0, pcie_gen=4.0, pcie_width=8.0)
        r.update(reason_hw_thermal_slowdown=i < 5, tctl_c=70.0, majflt=float(i), pswpin=5.0)
        rows.append(r)
    path = tmp_path / "x.csv"
    import csv

    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=tm.COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    back = tm.read_csv(path)
    assert (
        back[0]["reason_hw_thermal_slowdown"] is True
        and back[9]["reason_hw_thermal_slowdown"] is False
    )
    assert len(tm.window(back, 100.0, 102.0)) == 5
    ev = tm.evaluate(back)
    assert ev["thermal"]["flag"] == "thermal" and ev["paging"]["flag"] is None
    assert tm.link_under_load(back)["all_samples"] == {"gen4x8": 10}


@pytest.mark.gpu
def test_live_sampler_reads_the_gpu(tmp_path):
    import time

    with tm.Sampler(tmp_path / "live.csv") as s:
        time.sleep(1.6)
    assert len(s.rows) >= 2 and s.rows[0]["gpu_mem_used_mib"] is not None


def test_detectors_on_a_real_sampler_excerpt():
    """20 rows of the WP6 live check (llama-server answering real requests)."""
    from smallpc import flags

    rows = tm.read_csv(FIX / "sampler-sample.csv")
    # the excerpt was recorded in WP6, before VmSwap was added to the sampler (plan v1.3)
    assert len(rows) == 20 and list(rows[0]) == [c for c in tm.COLUMNS if c != "server_vmswap_kib"]
    assert all(r["pcie_gen"] == 4 and r["pcie_width"] == 8 for r in rows)
    assert all(r["server_rss_kib"] > 1e6 for r in rows)  # the server pid was found via the pidfile
    ev = tm.evaluate(rows)
    assert ev["thermal"]["flag"] is None and ev["thermal"]["max_tctl_c"] < 95
    assert ev["paging"]["major_faults"] == 0
    # the same data with a thermal slowdown injected into 1 of 20 samples (5%) is flagged
    hot = [dict(r) for r in rows]
    hot[3]["reason_hw_thermal_slowdown"] = True
    assert flags.thermal(hot)["flag"] == "thermal"
    # ... and with 1,001 extra major faults
    hot = [dict(r) for r in rows]
    hot[-1]["majflt"] = rows[0]["majflt"] + 1001
    assert flags.paging(hot)["flag"] == "paging"
