"""WP10 part A: the paging investigation, on synthetic telemetry (no GPU, no real session)."""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import pytest

from smallpc import flags, telemetry
from smallpc import paging_analysis as pa

MIB = 1024


def rows(vmswap, *, maj=None, pswpin=None, mem=None, t0=1000.0, extra=None, no_swap_col=False):
    """Telemetry rows at 2 Hz from per-sample VmSwap values (MiB)."""
    out = []
    for i, v in enumerate(vmswap):
        r = {
            "t_epoch": t0 + i * 0.5,
            "majflt": (maj[i] if maj else 10),
            "pswpin": (pswpin[i] if pswpin else 5),
            "memavailable_kib": (mem[i] if mem else 20_000_000),
            "server_rss_kib": 20_000_000,
        }
        if not no_swap_col:
            r["server_vmswap_kib"] = None if v is None else v * MIB
        r.update(extra or {})
        out.append(r)
    return out


def verdict(rs):
    st = pa.segment_stats(rs)
    return st, pa.evaluate_rules(st)


def test_flat_swap_state_is_flagged_by_r0_only():
    st, rule = verdict(rows([500] * 20))  # 500 MiB already swapped, nothing moving
    assert st["nature"] == "state" and st["vmswap_start_kib"] == 500 * MIB
    assert st["vmswap_growth_kib"] == 0 and st["vmswap_abs_change_kib"] == 0
    assert rule == {"R0": True, "R1": False, "R2": False}


def test_growth_is_flagged_by_all_three_rules():
    st, rule = verdict(rows([0, 0, 20, 70, 140, 140]))
    assert st["nature"] == "activity"
    assert st["vmswap_growth_kib"] == 140 * MIB and st["vmswap_net_change_kib"] == 140 * MIB
    assert rule == {"R0": True, "R1": True, "R2": True}


def test_small_growth_below_64_mib_is_not_flagged_by_r1_and_r2():
    st, rule = verdict(rows([0, 10, 40, 64, 64]))
    assert st["vmswap_growth_kib"] == 64 * MIB  # exactly 64 MiB is not "more than 64"
    assert rule == {"R0": True, "R1": False, "R2": False}
    assert verdict(rows([0, 10, 40, 65, 65]))[1] == {"R0": True, "R1": True, "R2": True}


def test_shrinkage_is_flagged_by_r2_but_not_r1():
    st, rule = verdict(rows([800, 700, 500, 300, 300]))  # the server's pages are swapped back in
    assert st["nature"] == "state" and st["vmswap_net_change_kib"] == -500 * MIB
    assert st["vmswap_growth_kib"] == 0 and st["vmswap_abs_change_kib"] == 500 * MIB
    assert rule == {"R0": True, "R1": False, "R2": True}


def test_net_zero_swap_out_and_in_counts_for_r2_and_r1_growth():
    st, rule = verdict(rows([100, 300, 100]))
    assert st["vmswap_net_change_kib"] == 0 and st["vmswap_abs_change_kib"] == 200 * MIB
    assert st["nature"] == "state+activity"
    assert rule == {"R0": True, "R1": True, "R2": True}


def test_no_swap_at_all_flags_nothing():
    st, rule = verdict(rows([0] * 10))
    assert st["nature"] == "none" and rule == {"R0": False, "R1": False, "R2": False}


def test_major_faults_flag_every_rule_with_a_strict_threshold():
    exactly = rows([0] * 4, maj=[0, 400, 800, 1000])
    assert verdict(exactly)[1] == {"R0": False, "R1": False, "R2": False}  # 1,000 is not "more"
    over = rows([0] * 4, maj=[0, 400, 800, 1001])
    st, rule = verdict(over)
    assert st["majflt_change"] == 1001 and rule == {"R0": True, "R1": True, "R2": True}


def test_missing_vmswap_column_is_judged_on_faults_only():
    rs = rows([0] * 4, maj=[0, 10, 20, 30], no_swap_col=True)
    st, rule = verdict(rs)
    assert st["vmswap_recorded"] is False and st["nature"] == "not recorded"
    assert "vmswap_start_kib" not in st and rule == {"R0": False, "R1": False, "R2": False}
    rs = rows([0] * 4, maj=[0, 10, 20, 2000], no_swap_col=True)
    assert verdict(rs)[1]["R0"] is True


def test_samples_without_a_value_are_skipped_and_empty_windows_are_safe():
    st = pa.segment_stats(rows([None, 0, 80, None]))
    assert st["vmswap_start_kib"] == 0 and st["vmswap_growth_kib"] == 80 * MIB
    empty = pa.segment_stats([])
    assert empty == {"n_samples": 0, "vmswap_recorded": False}
    assert pa.evaluate_rules(empty) == {"R0": False, "R1": False, "R2": False}


def test_r0_is_the_v13_rule_and_flags_paging_is_now_its_fault_part():
    """R0 is the historical v1.3 rule (faults above 1,000, or VmSwap above zero). Since plan v1.4
    ``flags.paging`` keeps only the faults: it equals R0 on every case without VmSwap and is
    stricter than R0 where VmSwap is above zero."""
    cases = [rows([0] * 5), rows([5] * 5), rows([0, 0, 1]), rows([0] * 3, maj=[0, 500, 1500])]
    for rs in cases:
        r0 = pa.evaluate_rules(pa.segment_stats(rs))["R0"]
        v14 = flags.paging(rs)["flag"] == "paging"
        faults = flags.paging(rs)["major_faults"] > flags.MAJFLT_LIMIT
        max_vm = flags.paging(rs)["server_vmswap_max_kib"]
        assert v14 == faults
        assert r0 == (faults or max_vm > 0)


def test_other_columns_pswpin_memavailable_rss_split():
    rs = rows(
        [0, 0, 0],
        pswpin=[100, 150, 400],
        mem=[9_000_000, 7_000_000, 8_000_000],
        extra={"pswpout": 7, "server_rss_anon_kib": 111, "server_rss_file_kib": 222},
    )
    st = pa.segment_stats(rs)
    assert st["pswpin_change"] == 300 and st["memavailable_min_kib"] == 7_000_000
    assert st["pswpout_change"] == 0 and st["rss_anon_start_kib"] == 111
    assert st["rss_file_end_kib"] == 222 and st["rss_shmem_start_kib"] is None  # not in the rows


def _req(pos, kind, depth, t0, t1):
    return {
        "position": pos,
        "kind": kind,
        "depth": depth,
        "client": {"t_start_epoch": t0, "t_end_epoch": t1},
        "prompt_per_second": 900.0,
        "predicted_per_second": 80.0,
    }


def test_attribution_shares_counters_out_by_time_and_adds_up():
    # samples at 1000.0 ... 1004.5; request 0 runs 1000.0-1002.0, request 1 runs 1003.0-1004.5
    maj = [0, 0, 0, 0, 0, 0, 0, 100, 400, 700]
    vm = [0, 0, 0, 0, 50, 50, 50, 50, 50, 50]
    rs = rows(vm, maj=maj)
    reqs = [_req(0, "A", 8192, 1000.0, 1002.0), _req(1, "B", 8192, 1003.0, 1004.5)]
    att = pa.attribute_requests(rs, reqs)
    assert [a["during_majflt"] + a["gap_majflt"] for a in att] == [0, 700]
    assert sum(a["during_majflt"] + a["gap_majflt"] for a in att) == 700  # the window's change
    assert att[0]["during_vmswap_kib"] + att[0]["gap_vmswap_kib"] == 50 * MIB
    assert att[1]["during_majflt"] == 700 and att[0]["gap_majflt"] == 0
    assert att[0]["speed"] == 900.0 and att[1]["speed"] == 80.0  # A: prefill, B: decode
    assert pa.attribute_requests([], reqs)[0]["during_majflt"] == 0


# ----------------------------------------------------------------- a small session on disk


def _write_session(tmp: Path, *, with_vmswap: bool, sid: str = "s1") -> Path:
    sess = tmp / sid
    (sess / "cells").mkdir(parents=True)
    (sess / "telemetry").mkdir()
    (sess / "session.json").write_text(json.dumps({"session_id": sid}))
    cols = ["t_epoch", "majflt", "pswpin", "memavailable_kib", "server_rss_kib"]
    if with_vmswap:
        cols.append("server_vmswap_kib")
    vm = [0] * 6 + [100] + [400] * 5  # grows inside the window (rows 4 to 10)
    with gzip.open(sess / "telemetry/c-i0.csv.gz", "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for i in range(12):
            row = [1000 + i * 0.5, 5 + i * 100, 100 + i, 20_000_000, 20_000_000]
            if with_vmswap:
                row.append(vm[i] * MIB)
            w.writerow(row)
    base = {
        "schema": 1,
        "session_id": sid,
        "cell": "c",
        "config_hash": "0" * 16,
        "attempt": 1,
        "server_run_id": "run0",
        "server_instance": 0,
        "code_commit": "x",
        "utc": "t",
        "batch_id": "b",
        "batch_size": 1,
        "batch_index": 0,
        "record_type": "request",
    }
    reqs = []
    for pos, (role, kind, t0, t1) in enumerate(
        [("warmup", "warmup", 1000.0, 1001.0), ("measured", "A", 1002.0, 1004.0)]
    ):
        reqs.append(
            base
            | {
                "role": role,
                "kind": kind,
                "workload_id": f"w{pos}",
                "repetition": 0,
                "position": pos,
                "depth": 16384,
                "window_id": None if role == "warmup" else "c-r0-a1",
                "prompt_per_second": 900.0,
                "predicted_per_second": 80.0,
                "client": {"t_start_epoch": t0, "t_end_epoch": t1},
                "batch_id": f"b{pos}",
            }
        )
    with open(sess / "records.jsonl", "w") as fh:
        for r in reqs:
            fh.write(json.dumps(r) + "\n")
    inst = {
        "instance": 0,
        "run_id": "run0",
        "telemetry": {"file": "telemetry/c-i0.csv.gz"},
        "snapshot_state": {"memory": {"swap_used_kib": 1, "vmstat": {"pswpin": 90, "pswpout": 7}}},
        "windows": [
            {
                "window_id": "c-r0-a1",
                "repetition": 0,
                "attempt": 1,
                "t0_epoch": 1002.0,
                "t1_epoch": 1005.0,
                "flags": ["paging"],
            }
        ],
    }
    cell = {"cell": "c", "role": "measured", "config_hash": "0" * 16, "instances": [inst]}
    (sess / "cells/c-00000000.json").write_text(json.dumps(cell))
    return sess


def test_analyse_session_end_to_end(tmp_path):
    sess = _write_session(tmp_path, with_vmswap=True)
    res = pa.analyse_session(sess, attribute=["c:0"])
    kinds = [s["segment"] for s in res["segments"]]
    assert kinds == ["server_start", "warmup", "window"]
    win = res["segments"][2]
    assert win["vmswap_start_kib"] == 0 and win["vmswap_max_kib"] == 400 * MIB
    assert win["rules"] == {"R0": True, "R1": True, "R2": True}
    assert res["segments"][0]["pswpin_since_snapshot"] == 10  # first sample 100 minus snapshot 90
    assert res["r0_matches_recorded_flag"] == {"agree": 1, "windows": 1}
    assert res["attribution"][0]["requests"][0]["kind"] == "A"
    assert "_rows" not in json.dumps(res)  # the private row lists never reach the output
    md = pa.render_markdown(res)
    assert "| c | window r0 |" in md and "What the data cannot show" in md


def test_analyse_session_with_an_old_csv_without_vmswap(tmp_path):
    sess = _write_session(tmp_path, with_vmswap=False)
    res = pa.analyse_session(sess, attribute=[])
    win = res["segments"][2]
    assert win["vmswap_recorded"] is False and win["nature"] == "not recorded"
    assert win["rules"] == {"R0": False, "R1": False, "R2": False}  # 600 faults in the window
    assert pa.render_markdown(res)  # renders with the missing column


def test_cli_writes_json_and_markdown(tmp_path, monkeypatch):
    sess = _write_session(tmp_path, with_vmswap=True)
    out = tmp_path / "out"
    assert pa.main([str(sess), "--out-dir", str(out), "--attribute", "c:0"]) == 0
    assert json.loads((out / "paging-s1.json").read_text())["session_id"] == "s1"
    assert (out / "paging-s1.md").read_text().startswith("# Paging analysis of `s1`")


@pytest.mark.parametrize("col", ["server_rss_anon_kib", "server_rss_file_kib", "pswpout"])
def test_new_telemetry_columns_are_known_to_the_reader(col):
    assert col in telemetry.COLUMNS and col in telemetry._FLOAT_COLS


# ------------------------------------------------------------------ the data label (WP12)


@pytest.mark.parametrize(
    ("sid", "label"),
    [
        ("stage1-64K", "screening"),
        ("stage1-128K", "screening"),
        ("stage2f-128K", "screening"),
        ("mini-20261109", "functional-test"),
        ("ft-2f-cram", "functional-test"),
        ("preflight-20261109", "functional-test"),
    ],
)
def test_default_label_follows_the_session_name(sid, label):
    assert pa.default_label(sid) == label


@pytest.mark.parametrize(
    ("label", "needle", "absent"),
    [
        ("functional-test", "FUNCTIONAL-TEST DATA", "SCREENING DATA"),
        ("screening", "SCREENING DATA", "FUNCTIONAL-TEST DATA"),
        ("results", "RESULTS.", "FUNCTIONAL-TEST DATA"),
    ],
)
def test_the_banner_and_note_follow_the_label(tmp_path, label, needle, absent):
    sess = _write_session(tmp_path, with_vmswap=True, sid="stage1-x")
    res = pa.analyse_session(sess, attribute=[], label=label)
    md = pa.render_markdown(res)
    assert res["label"] == label and needle in res["note"]
    assert needle in md and absent not in md and absent not in res["note"]
    assert "WP9 mini-sweep" not in md and "WP9 mini-sweep" not in res["note"]


def test_the_cli_label_default_and_override(tmp_path):
    stage = _write_session(tmp_path, with_vmswap=True, sid="stage1-x")
    mini = _write_session(tmp_path, with_vmswap=True, sid="mini-x")
    out = tmp_path / "out"
    assert pa.main([str(stage), "--out-dir", str(out)]) == 0
    assert pa.main([str(mini), "--out-dir", str(out)]) == 0
    assert pa.main([str(stage), "--out-dir", str(out / "o"), "--label", "functional-test"]) == 0
    assert json.loads((out / "paging-stage1-x.json").read_text())["label"] == "screening"
    assert "SCREENING DATA" in (out / "paging-stage1-x.md").read_text()
    assert json.loads((out / "paging-mini-x.json").read_text())["label"] == "functional-test"
    assert "FUNCTIONAL-TEST DATA" in (out / "paging-mini-x.md").read_text()
    assert json.loads((out / "o/paging-stage1-x.json").read_text())["label"] == "functional-test"
