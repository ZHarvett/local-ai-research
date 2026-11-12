"""scripts/check-quiet.sh and smallpc.stage3.quiet on fake `ps` output (WP13): a quiet machine, one
offender, a heavy unlisted process; names only; the CPU idle line."""

from __future__ import annotations

import subprocess

import pytest

from conftest import REPO
from smallpc.stage3 import quiet

SCRIPT = REPO / "scripts/check-quiet.sh"
CFG = REPO / "configs/quiet-check.toml"

CLEAN = """\
systemd 18000
cosmic-comp 410000
zsh 9000
claude 650000
llama-server 21000000
Xwayland 80000
kworker/R-btrfs-cache 0
"""
ONE_OFFENDER = CLEAN + "chrome 520000\nchrome 310000\n"
HEAVY = CLEAN + "blender 3400000\npostgres 90000\n"


def run_script(tmp_path, ps_text, *extra):
    f = tmp_path / "ps.txt"
    f.write_text(ps_text)
    return subprocess.run(
        [SCRIPT, "--ps-file", f, "--no-cpu", *extra], capture_output=True, text=True, check=False
    )


def test_a_quiet_machine_exits_zero(tmp_path):
    r = run_script(tmp_path, CLEAN)
    assert r.returncode == 0, r.stderr
    assert "no blocklisted app is running" in r.stdout and "RESULT: QUIET" in r.stdout
    assert "warning" not in r.stdout  # llama-server and claude are exempt from the memory warning


def test_a_blocklisted_app_exits_one_and_is_listed_with_its_count(tmp_path):
    r = run_script(tmp_path, ONE_OFFENDER)
    assert r.returncode == 1
    assert (
        "NOT QUIET" in r.stdout
        and "chrome  x2" in r.stdout
        and "RESULT: NOT QUIET (exit 1)" in r.stdout
    )


def test_a_heavy_unlisted_process_warns_but_does_not_fail(tmp_path):
    r = run_script(tmp_path, HEAVY)
    assert r.returncode == 0
    assert "processes above 1.5 GiB resident" in r.stdout and "blender  3320 MiB" in r.stdout
    assert "postgres" not in r.stdout and "cosmic-comp" not in r.stdout


def test_every_blocklist_entry_is_caught_and_names_are_compared_at_ps_width():
    cfg = quiet.load_config(CFG)
    for name in [
        "chrome",
        "chromium",
        "firefox",
        "antigravity-ide",
        "kilo",
        "spotify",
        "missioncenter",
        "discord",
        "slack",
        "steam",
        "virt-manager",
        "obsidian",
        "code",
    ]:
        assert not quiet.check([(name, 1)], cfg)["quiet"], name
    # ps shows only 15 characters of "qemu-system-x86_64"
    ((name, _),) = quiet.parse_ps("qemu-system-x86 100\n")
    assert name == "qemu-system-x86" and not quiet.check([(name, 100)], cfg)["quiet"]
    assert quiet.check([("codex-helper", 1), ("vscode-server", 1)], cfg)[
        "quiet"
    ]  # not exact matches


def test_names_with_spaces_and_junk_lines_are_parsed_without_echoing_anything_else():
    procs = quiet.parse_ps("Web Content 120000\n\nnot a size line\nzsh 5\n")
    assert procs == [("Web Content", 120000), ("zsh", 5)]


def test_the_script_asks_ps_for_names_and_sizes_only():
    text = SCRIPT.read_text()
    assert "ps -eo comm=,rss=" in text
    code = [ln for ln in text.splitlines() if "ps -" in ln and not ln.lstrip().startswith("#")]
    assert code == ["  ps -eo comm=,rss= | run"]
    for field in ("args", "cmd", "command", "wchan", "euser"):
        assert f"{field}" not in " ".join(code)


def test_the_cpu_idle_line_is_informational(tmp_path):
    cfg = quiet.load_config(CFG)
    stats = iter(["cpu 100 0 100 700 100 0 0 0 0 0\n", "cpu 150 0 150 1300 100 0 0 0 0 0\n"])
    ps = tmp_path / "p.txt"
    ps.write_text(CLEAN)
    out: list[str] = []
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = quiet.main(["--ps-file", str(ps)], read_stat=lambda: next(stats), sleep=lambda s: None)
    assert rc == 0
    assert "CPU idle check (informational): busy 14.3% over 10 s" in buf.getvalue()
    assert cfg["cpu_busy_max_pct"] == 10.0  # above the limit still exits 0: information only
    del out


def test_a_missing_process_list_or_a_bad_config_is_a_usage_error(tmp_path, capsys):
    empty = tmp_path / "e.txt"
    empty.write_text("")
    assert quiet.main(["--ps-file", str(empty), "--no-cpu"]) == 2
    bad = tmp_path / "bad.toml"
    bad.write_text("[blocklist]\nnames = []\n")
    ps = tmp_path / "p.txt"
    ps.write_text(CLEAN)
    assert quiet.main(["--config", str(bad), "--ps-file", str(ps), "--no-cpu"]) == 2
    assert "check-quiet" in capsys.readouterr().err


def test_the_json_output_has_no_command_lines(tmp_path):
    r = run_script(tmp_path, ONE_OFFENDER, "--json")
    assert r.returncode == 1 and '"offenders"' in r.stdout and '"chrome": 2' in r.stdout


@pytest.mark.parametrize("opt", ["--bogus"])
def test_unknown_option_fails(opt):
    assert (
        subprocess.run([SCRIPT, opt], capture_output=True, text=True, check=False).returncode == 1
    )
