"""tools/stage2_vram_check.py: the resident compute-buffer estimate and the table (WP12 part 2g)."""

from __future__ import annotations

import importlib.util

from conftest import REPO

spec = importlib.util.spec_from_file_location(
    "stage2_vram_check", REPO / "tools" / "stage2_vram_check.py"
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def lines(*mibs, host=True):
    out = [{"device": "CUDA0", "mib": m} for m in mibs]
    return out + ([{"device": "CUDA_Host", "mib": 99.0}] if host else [])


def test_four_mtp_lines_count_the_last_two_and_others_are_summed():
    assert tool.resident_cuda_sum(lines(1348.0, 638.0, 638.0, 1348.0)) == 638.0 + 1348.0
    # a fit placement: the re-reserved target buffer is smaller than the first one
    assert tool.resident_cuda_sum(lines(2034.0, 1344.0, 1344.0, 1872.0)) == 1344.0 + 1872.0
    assert tool.resident_cuda_sum(lines(1348.0)) == 1348.0  # one reservation (no MTP)
    assert tool.resident_cuda_sum(lines(1.0, 2.0, 3.0)) == 6.0  # an unknown pattern is not guessed
    assert tool.resident_cuda_sum([]) == 0.0


def test_markdown_counts_cells_above_the_peak():
    def row(name, mtp, plotted, resident):
        return {"cell": name, "mtp": mtp, "compute_lines_mib": [1.0], "compute_parsed": 1.0,
                "compute_resident": 1.0, "peak_used": 15000.0, "other_as_plotted": plotted,
                "other_resident": resident}  # fmt: skip

    md = tool.markdown([row("a", False, 350.0, 350.0), row("b", True, -1400.0, 520.0)])
    assert "cells with parsed parts above the peak: 1 of 2; MTP cells among them: 1" in md
    assert "non-MTP cells among them: 0" in md and "| b | yes |" in md
