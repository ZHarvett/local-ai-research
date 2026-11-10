"""The llama-bench cross-check wrapper: flag mapping, parsing, the default cell, a fake binary."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from conftest import FIXTURES, REPO
from smallpc.stage2 import bench, cli

MODEL = "/m/model.gguf"


def mapped(**f):
    base = {"profile": "candidate", "context": 65536, "cache_type_k": "q8_0", "cache_type_v": "q8_0",
            "flash_attn": "on", "parallel": 1, "metrics": True, "log_verbosity": 4}  # fmt: skip
    return bench.map_config({**base, **f}, MODEL)


def flag(m, name):
    a = m["argv"]
    return a[a.index(name) + 1] if name in a else None


def names(entries):
    return [e["field"] for e in entries]


def test_p2_fit_target_is_fully_expressed_with_fitt_and_fitc():
    m = mapped(fit="on", fit_target=256, batch=4096, ubatch=4096)
    assert flag(m, "-fitt") == "256" and flag(m, "-fitc") == "65536" and flag(m, "-m") == MODEL
    assert (flag(m, "-b"), flag(m, "-ub"), flag(m, "-ctk"), flag(m, "-ctv"), flag(m, "-fa")) == (
        "4096", "4096", "q8_0", "q8_0", "on",
    )  # fmt: skip
    assert "-ngl" not in m["argv"]
    assert m["unexpressed"] == [] and names(m["approximated"]) == ["context"]
    assert {"parallel", "fit", "fit_target"} <= set(names(m["expressed"]))
    assert set(names(m["not_inference"])) == {"profile", "metrics", "log_verbosity"}


def test_p1_uses_the_default_fit_margin():
    m = mapped(fit="on")
    assert flag(m, "-fitt") == "1024"


def test_p6_cmoe_with_the_expert_cache_loses_the_cache():
    m = mapped(cpu_moe=True, moe_cache_mib=11008, batch=4096, ubatch=4096)
    assert flag(m, "-ot") == bench.CPU_MOE_PATTERN and flag(m, "-ngl") == "99"
    assert "-fitt" not in m["argv"]
    assert set(names(m["unexpressed"])) == {"moe_cache_mib", "context"}
    assert names(m["approximated"]) == ["cpu_moe"]


def test_p8_n_cpu_moe_is_exact_but_the_context_cannot_be_carried():
    m = mapped(fit="off", n_cpu_moe=17, batch=2048, ubatch=2048)
    assert flag(m, "-ncmoe") == "17" and flag(m, "-ngl") == "99"
    assert names(m["unexpressed"]) == ["context"] and m["approximated"] == []


def test_mtp_cache_ram_load_mode_and_threads():
    m = mapped(fit="on", spec_type="draft-mtp", spec_draft_n_max=2, cache_ram=2048,
               load_mode="none", threads=8, cache_type_k="f16", cache_type_v="f16")  # fmt: skip
    assert set(names(m["unexpressed"])) == {"spec_type", "spec_draft_n_max", "cache_ram"}
    assert flag(m, "-lm") == "none" and flag(m, "-t") == "8" and flag(m, "-ctk") == "f16"


def test_parallel_other_than_one_and_unknown_fields_are_unexpressed():
    m = mapped(fit="on", parallel=4, mystery=3)
    assert set(names(m["unexpressed"])) == {"parallel", "mystery"}


def test_the_two_invocations():
    m = mapped(fit="on", fit_target=256)
    c = bench.commands(m, [16384, 32768, 49152], 5)
    fresh, turn = c[0]["argv"], c[1]["argv"]
    assert fresh[fresh.index("-p") : fresh.index("-p") + 6] == [
        "-p",
        "16384,32768,49152",
        "-n",
        "0",
        "-d",
        "0",
    ]
    assert turn[turn.index("-p") : turn.index("-p") + 6] == [
        "-p",
        "3000",
        "-n",
        "400",
        "-d",
        "16384,32768,49152",
    ]
    assert fresh[-4:] == ["-r", "5", "-o", "json"] == turn[-4:]


ROWS = [
    {"build_commit": "57d0482", "n_prompt": 16384, "n_gen": 0, "n_depth": 0, "avg_ts": 2000.0,
     "samples_ts": [1990.0, 2010.0, 2000.0, 1995.0, 2005.0]},
    {"build_commit": "57d0482", "n_prompt": 0, "n_gen": 400, "n_depth": 16384, "avg_ts": 70.0,
     "samples_ts": [69.0, 71.0, 70.0, 70.5, 69.5]},
]  # fmt: skip


def test_parse_and_summarize_with_log_noise_before_the_json():
    out = "ggml_cuda_init: found 1 CUDA devices\n" + json.dumps(ROWS)
    tests = bench.summarize_rows(bench.parse_rows(out))
    assert [t["kind"] for t in tests] == ["prefill", "decode"]
    assert (
        tests[0]["tokens_per_second"]["n"] == 5 and tests[0]["tokens_per_second"]["mean"] == 2000.0
    )
    assert tests[1]["n_depth"] == 16384 and tests[1]["tokens_per_second"]["ci"] is not None
    with pytest.raises(ValueError):
        bench.parse_rows("no json here")


def test_default_cell_prefers_fewest_inexpressible_then_the_shortlist():
    scores = [
        {"cell": "P8-64K-b4096", "unexpressed": 1, "approximated": 0, "shortlisted": False},
        {"cell": "P2-64K-b4096", "unexpressed": 0, "approximated": 1, "shortlisted": True},
        {"cell": "P1-64K-b4096", "unexpressed": 0, "approximated": 1, "shortlisted": False},
        {"cell": "P6-64K-b4096", "unexpressed": 2, "approximated": 1, "shortlisted": True},
    ]
    assert bench.default_cell(scores)["cell"] == "P2-64K-b4096"
    assert bench.default_cell(scores[:1] + scores[2:3])["cell"] == "P1-64K-b4096"


def test_the_real_stage1_64k_cells_rank_p2_b4096_first():
    scores = bench.expressibility(REPO)
    assert len(scores) == 18
    by = {s["cell"]: s for s in scores}
    assert bench.default_cell(scores)["cell"] == "P2-64K-b4096"
    assert by["P2-64K-b4096"]["unexpressed"] == 0 and by["P2-64K-b4096"]["shortlisted"]
    assert by["P8-64K-b4096"]["unexpressed_fields"] == ["context"]
    assert "moe_cache_mib" in by["P6-64K-b4096"]["unexpressed_fields"]
    text = bench.format_expressibility(scores)
    assert "P2-64K-b4096" in text and "<- default" in text


FAKE = f"""#!{sys.executable}
import json, sys
a = sys.argv[1:]
print("ggml_cuda_init: fake", file=sys.stderr)
rows = []
if "-n" in a and a[a.index("-n") + 1] == "0":
    for d in a[a.index("-p") + 1].split(","):
        rows.append({{"build_commit": "fake", "n_prompt": int(d), "n_gen": 0, "n_depth": 0,
                      "avg_ts": 2000.0, "samples_ts": [2000.0 + i for i in range(int(a[a.index("-r") + 1]))]}})
else:
    for d in a[a.index("-d") + 1].split(","):
        rows.append({{"build_commit": "fake", "n_prompt": 3000, "n_gen": 0, "n_depth": int(d), "avg_ts": 1500.0,
                      "samples_ts": [1500.0] * int(a[a.index("-r") + 1])}})
        rows.append({{"build_commit": "fake", "n_prompt": 0, "n_gen": 400, "n_depth": int(d), "avg_ts": 70.0,
                      "samples_ts": [70.0] * int(a[a.index("-r") + 1])}})
print(json.dumps(rows))
"""


class FakeSampler:
    def __init__(self, path):
        self.rows, self.path = [], path

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_end_to_end_with_a_fake_binary(tmp_path, monkeypatch):
    monkeypatch.setenv("SMALLPC_BENCH_NO_LOCK", "1")
    fake = tmp_path / "llama-bench"
    fake.write_text(FAKE)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "o/bench.json"
    res = bench.run_bench(
        "P2-64K-b4096", out, reps=3, root=REPO, binary=fake, data_label="functional-test",
        preconditions=lambda: {"ok": True}, snapshot=lambda: {"snapshot_id": "snap1"},
        sampler_factory=FakeSampler,
    )  # fmt: skip
    assert out.exists() and json.loads(out.read_text())["label"] == bench.CROSSCHECK_LABEL
    assert res["label"] == "cross-check, random-token prompts, never used for a decision"
    assert res["data_label"] == "functional-test" and res["repetitions"] == 3
    assert res["depths"] == [16384, 32768, 49152] and res["environment"] == {"snapshot_id": "snap1"}
    kinds = [(t["invocation"], t["kind"], t["n_depth"]) for t in res["tests"]]
    assert kinds.count(("fresh_prefill", "prefill", 0)) == 3 and len(kinds) == 3 + 6
    assert all(t["tokens_per_second"]["n"] == 3 for t in res["tests"])
    assert res["unexpressed"] == [] and [e["field"] for e in res["approximated"]] == ["context"]
    assert res["runs"][0]["argv"][0] == "llama-bench" and "-fitt" in res["runs"][0]["argv"]
    assert "never used to choose a configuration" in res["note"]


def test_it_refuses_without_the_gpu_lock_and_reports_a_failing_binary(tmp_path, monkeypatch):
    from smallpc.sanity_runner import SanityError

    monkeypatch.delenv("SMALLPC_GPU_LOCK_HELD", raising=False)
    monkeypatch.delenv("SMALLPC_BENCH_NO_LOCK", raising=False)
    with pytest.raises(SanityError, match="GPU lock is not held"):
        bench.run_bench("P2-64K-b4096", tmp_path / "x.json", root=REPO)
    monkeypatch.setenv("SMALLPC_BENCH_NO_LOCK", "1")
    bad = tmp_path / "llama-bench"
    bad.write_text("#!/bin/sh\necho boom >&2\nexit 3\n")
    bad.chmod(0o755)
    with pytest.raises(RuntimeError, match="failed"):
        bench.run_bench("P2-64K-b4096", tmp_path / "x.json", root=REPO, binary=bad,
                        preconditions=lambda: {"ok": True}, snapshot=lambda: {},
                        sampler_factory=FakeSampler)  # fmt: skip


def test_cli_list_expressibility_and_usage_errors(capsys):
    assert cli.main(["bench-crosscheck", "--list-expressibility"]) == 0
    assert "<- default" in capsys.readouterr().out
    assert cli.main(["bench-crosscheck"]) == 2
    assert FIXTURES.exists()
    assert Path(sys.executable).exists()
