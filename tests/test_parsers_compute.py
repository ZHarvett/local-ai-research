"""Resident compute buffers in the load log (WP13): an MTP cell's log lists four CUDA0 compute
buffers for two llama_contexts; only the last reservation of each context is resident.

The fixtures are the buffer lines of the real server logs of Stage 2 cells (an MTP and a non-MTP
P6 cell, an MTP P6 cell at 64K, an MTP `--fit` cell at 128K), scrubbed; `vram-measured.json` holds
the measured peak of the same cells from their cell summaries in data/raw.
"""

from __future__ import annotations

import json

import pytest

from conftest import REPO
from smallpc import analysis, parsers

LOGS = REPO / "tests" / "fixtures" / "logs"
MEASURED = json.loads((LOGS / "vram-measured.json").read_text())["cells"]
MTP = [k for k, v in MEASURED.items() if v["mtp"]]
NO_MTP = [k for k, v in MEASURED.items() if not v["mtp"]]


def cuda0(items):
    return sum(i["mib"] for i in items if i["device"] == "CUDA0")


def parts(fixture: str) -> dict:
    p = parsers.parse_fit_placement((LOGS / fixture).read_text())
    m = MEASURED[fixture]
    d = {
        "model": p["model_buffers"]["CUDA0"]["mib"],
        "kv": cuda0(p["kv_buffers"]),
        "rs": cuda0(p["recurrent_state_buffers"]),
        "compute": cuda0(p["compute_buffers"]),
        "cache": m["expert_cache_mib"],
    }
    d["parsed"] = sum(d.values())
    d["other"] = m["peak_used_mib"] - d["parsed"]
    d["all_lines"] = cuda0([b for blk in p["compute_buffer_reservations"] for b in blk["buffers"]])
    return d


@pytest.mark.parametrize("fixture", list(MEASURED))
def test_parsed_parts_do_not_exceed_the_measured_peak(fixture):
    d = parts(fixture)
    assert d["parsed"] <= MEASURED[fixture]["peak_used_mib"]
    assert d["other"] >= 0


def test_mtp_cell_counts_target_and_draft_once_each():
    p = parsers.parse_fit_placement((LOGS / "vram-mtp-p6-32k-mtp1.txt").read_text())
    blocks = p["compute_buffer_reservations"]
    assert [b["context"] for b in blocks] == [0, 1, 1, 0]  # target, draft, draft, target
    assert [b["nodes"] for b in blocks] == [4066, 86, 92, 4058]
    assert [cuda0(b["buffers"]) for b in blocks] == [1348.03, 638.28, 638.28, 1348.03]
    assert cuda0(p["compute_buffers"]) == pytest.approx(1348.03 + 638.28)
    # the host compute buffers follow the same rule (they are not VRAM, analysis ignores them)
    host = [b["mib"] for b in p["compute_buffers"] if b["device"] == "CUDA_Host"]
    assert host == pytest.approx([384.19, 320.14])
    # before the fix the parser listed all four lines
    assert parts("vram-mtp-p6-32k-mtp1.txt")["all_lines"] == pytest.approx(3972.62)


def test_fit_placement_mtp_cell_uses_the_re_reserved_target_size():
    # the target's second reservation is smaller than its first (2034 -> 1872): the later one counts
    p = parsers.parse_fit_placement((LOGS / "vram-mtp-p2-128k-mtp1-fit.txt").read_text())
    assert cuda0(p["compute_buffers"]) == pytest.approx(1344.12 + 1872.16)


def test_non_mtp_cell_is_unchanged():
    p = parsers.parse_fit_placement((LOGS / "vram-nomtp-p6-32k-mtp0.txt").read_text())
    assert [b["context"] for b in p["compute_buffer_reservations"]] == [0]
    assert p["compute_buffers"] == [
        {"device": "CUDA0", "mib": 1348.03},
        {"device": "CUDA_Host", "mib": 384.19},
    ]


def test_other_is_of_similar_size_with_and_without_mtp():
    """`other` (CUDA context and similar) is 337 to 363 MiB without MTP and 512 to 532 MiB with
    MTP on the Stage 2 cells. The remaining ~170 MiB is a fixed amount per cell, the same at 32K, 64K
    and 128K (it does not grow with the compute buffers), which fits a per-context overhead that
    the load log does not show; this test does not claim to know what it is."""
    other_no = [parts(f)["other"] for f in NO_MTP]
    other_mtp = [parts(f)["other"] for f in MTP]
    assert all(300 <= o <= 400 for o in other_no)
    assert all(450 <= o <= 600 for o in other_mtp)
    assert max(other_mtp) - min(other_no) <= 256
    assert max(other_mtp) - min(other_mtp) <= 20  # the same at every context size


def test_ownership_by_graph_size_when_a_context_reserves_again_out_of_order():
    def blk(nodes, mib):
        return (
            "I sched_reserve: reserving ...\n"
            f"I sched_reserve:      CUDA0 compute buffer size =   {mib} MiB\n"
            f"I sched_reserve: graph (pp bs=1, tg bs=1): nodes = {nodes} / {nodes}, splits = 1\n"
        )

    c = "I llama_context: constructing llama_context\n"
    log = c + blk(4000, 100.0) + c + blk(80, 10.0) + blk(90, 11.0) + blk(90, 12.0)
    p = parsers.parse_fit_placement(log)
    assert [b["context"] for b in p["compute_buffer_reservations"]] == [0, 1, 1, 1]
    assert cuda0(p["compute_buffers"]) == pytest.approx(100.0 + 12.0)  # last draft block only


def test_a_log_without_context_lines_keeps_every_line():
    log = "I sched_reserve:      CUDA0 compute buffer size =   5.0 MiB\n" * 2
    p = parsers.parse_fit_placement(log)
    assert cuda0(p["compute_buffers"]) == 10.0


def cell(*mibs):
    out = []
    for m in mibs:
        out += [{"device": "CUDA0", "mib": m}, {"device": "CUDA_Host", "mib": 99.0}]
    return out


def test_stored_lists_of_older_cell_summaries():
    old = {"compute_buffers": cell(1348.03, 638.28, 638.28, 1348.03)}
    assert cuda0(parsers.resident_compute_buffers(old)) == pytest.approx(1986.31)
    assert len(parsers.resident_compute_buffers(old)) == 4  # host entries travel with their block
    one = {"compute_buffers": cell(1348.03)}
    assert parsers.resident_compute_buffers(one) == one["compute_buffers"]
    odd = {"compute_buffers": cell(1.0, 2.0, 3.0)}  # an unknown pattern is not guessed
    assert parsers.resident_compute_buffers(odd) == odd["compute_buffers"]
    assert parsers.resident_compute_buffers({}) == []
    new = {"compute_buffers": cell(1348.03, 638.28), "compute_buffer_reservations": [{}]}
    assert parsers.resident_compute_buffers(new) == new["compute_buffers"]


def test_old_stored_list_and_new_parse_give_the_same_analysis_figure():
    """`analysis._vram_parts` on a summary written before the fix (all four lines) equals the figure
    of the fixed parser on the same log."""
    log = (LOGS / "vram-mtp-p6-32k-mtp1.txt").read_text()
    new = parsers.parse_fit_placement(log)
    old = {k: v for k, v in new.items() if k != "compute_buffer_reservations"}
    old["compute_buffers"] = [
        b for blk in new["compute_buffer_reservations"] for b in blk["buffers"]
    ]
    assert cuda0(old["compute_buffers"]) == pytest.approx(3972.62)
    vram = {"total_mib": 16311.0, "peak_used_mib": 15116.0, "min_free_mib": 1195.0}
    a = analysis._vram_parts({"parsed": {"placement": new}, "vram": vram})
    b = analysis._vram_parts({"parsed": {"placement": old}, "vram": vram})
    assert a["compute_mib"] == b["compute_mib"] == pytest.approx(1986.31)
