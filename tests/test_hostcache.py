"""Host prompt cache series and window figures (moved from tools/stage1_diagnostics.py, WP12)."""

from __future__ import annotations

import csv
import gzip

from smallpc import hostcache as hc

MIB = 1024


def log_line(t: float, text: str, level: str = "I") -> str:
    m, s = divmod(t, 60)
    sec = int(s)
    ms = int(round((s - sec) * 1000))
    return f"{int(m)}.{sec:02d}.{ms:03d}.000 {level} {text}"


def write_log(path, timings, states):
    lines = ["0.00.000.000 I srv  llama_server: initializing ..."]
    events = [(t, "timing") for t in timings] + [(t, "state") for t, _, _ in states]
    by_t = {t: (n, mib) for t, n, mib in states}
    for t, kind in sorted(events):
        if kind == "timing":
            lines.append(
                log_line(t, "slot print_timing: id  0 | task 3 |       total time =  900.00 ms")
            )
        else:
            n, mib = by_t[t]
            lines.append(
                log_line(
                    t,
                    f"srv update: - cache state: {n} prompts, {mib:.3f} MiB (limits: 8192.000 MiB, 4096 tokens)",
                )
            )
    path.write_text("\n".join(lines) + "\n")


def reqs(run_id, ends):
    return [{"server_run_id": run_id, "client": {"t_end_epoch": e}} for e in ends]


def test_rel_s():
    assert hc.rel_s(("1", "02", "500", "250")) == 62.50025


def test_cache_series_aligns_log_time_to_the_wall_clock(tmp_path):
    log = tmp_path / "server.log"
    write_log(log, [10.0, 20.0, 30.0], [(15.0, 1, 100.0), (25.0, 2, 250.5)])
    ends = [1010.0, 1020.0, 1030.0]  # wall clock = log time + 1000
    series = hc.cache_series(reqs("r0", ends), "r0", log)
    assert [(round(t), n, m) for t, n, m in series] == [(1015, 1, 100.0), (1025, 2, 250.5)]
    assert hc.cache_series(reqs("other", ends), "r0", log) == []  # no request of this instance


def test_cache_series_is_empty_when_the_alignment_would_be_a_guess(tmp_path):
    log = tmp_path / "server.log"
    write_log(log, [10.0, 20.0], [(15.0, 1, 100.0)])
    assert hc.cache_series(reqs("r0", [1.0, 2.0, 3.0]), "r0", log) == []  # 2 timings, 3 requests
    assert hc.cache_series(reqs("r0", [1.0]), "r0", tmp_path / "missing.log") == []


def write_csv(path, rows, gz=True):
    opener = gzip.open if gz else open
    with opener(path, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t_epoch", "majflt", "memavailable_kib", "server_vmswap_kib",
                    "server_rss_anon_kib", "server_rss_file_kib", "server_rss_shmem_kib"])  # fmt: skip
        w.writerows(rows)


def test_window_figures(tmp_path):
    rows = [
        [
            1000 + i,
            10 + 100 * i,
            (20 - i) * MIB * MIB,
            i * 10 * MIB,
            (1000 + 10 * i) * MIB,
            (8000 - 100 * i) * MIB,
            5 * MIB,
        ]  # fmt: skip
        for i in range(10)
    ]
    write_csv(tmp_path / "t.csv.gz", rows)
    got = hc.telemetry_rows(tmp_path / "t.csv.gz")
    cache = [(1002.0, 2, 500.0), (1008.0, 5, 1200.0), (1020.0, 9, 9999.0)]
    f = hc.window_figures(got, 1001.0, 1009.0, cache)
    assert f["anon"] == (1010.0, 1090.0) and f["file"] == (7900.0, 7100.0)
    assert f["vmswap"] == (10.0, 90.0, 90.0) and f["faults"] == 800
    assert f["memavail_min_gib"] == 11.0
    assert f["cache_first"] == (2, 500.0) and f["cache_last"] == (5, 1200.0)  # 9999 is outside
    assert hc.window_figures(got, 5000.0, 6000.0, cache) is None
    write_csv(tmp_path / "t.csv", rows, gz=False)
    assert hc.telemetry_rows(tmp_path / "t.csv") == got  # plain CSV reads the same


def test_missing_columns_read_as_none(tmp_path):
    p = tmp_path / "old.csv"
    p.write_text("t_epoch,majflt\n1.0,5\n2.0,9\n")
    f = hc.window_figures(hc.telemetry_rows(p), 0, 10, [])
    assert f["faults"] == 4 and f["anon"] == (None, None) and f["vmswap"] == (None, None, None)
