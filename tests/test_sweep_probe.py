"""Probing (max-fit and N_fit): the search algorithms against a fake VRAM model, the cache key,
and the run-time resolution of placement tokens against the mock server."""

from __future__ import annotations

import json
import random
import time

import pytest

from smallpc.config import load_sweep
from smallpc.sweep import probe as pr
from smallpc.sweep import records as rec
from smallpc.sweep.session import Session
from sweep_fakes import events, make_env, read_records, write_spec

TOTAL = 16311


def fake_vram(base, slope, lm=0):
    """used = base + slope * cache + a longest-request allowance; returns evaluate()."""

    def evaluate(c):
        free = TOTAL - (base + slope * c + lm)
        return pr.StepResult(free >= pr.MARGIN_MIB, free)

    return evaluate


# ------------------------------------------------------------------ the search algorithms


@pytest.mark.parametrize("seed", range(12))
def test_max_fit_finds_the_largest_passing_multiple_of_256(seed):
    rng = random.Random(seed)
    for _ in range(40):
        ev = fake_vram(rng.randint(3000, 9000), rng.uniform(0.95, 1.05), rng.randint(100, 900))
        res = pr.search_max_fit(ev, cap_mib=TOTAL)
        brute = max((c for c in range(256, TOTAL + 1, 256) if ev(c).ok), default=None)
        assert res.value == brute
        assert res.value is None or res.value % 256 == 0
        assert len(res.steps) <= 7
        if res.value:
            assert res.verified
            vals = {s["value"]: s["ok"] for s in res.steps}
            assert vals[res.value] is True
            assert vals.get(res.value + 256, False) is False  # a verified pair (or the cap)


def test_max_fit_is_typically_three_steps_and_never_exceeds_the_bound():
    rng = random.Random(11)
    n = [len(pr.search_max_fit(fake_vram(rng.randint(3000, 9000), 1.0, 300), cap_mib=TOTAL).steps)
         for _ in range(200)]  # fmt: skip
    assert sum(n) / len(n) < 4.0 and max(n) <= 6


def test_max_fit_edge_cases():
    # nothing fits: even 256 MiB leaves less than the margin
    none = pr.search_max_fit(lambda c: pr.StepResult(False, 100.0), cap_mib=TOTAL)
    assert none.value is None and not none.verified
    # everything fits: the answer is the cap, snapped to 256
    allok = pr.search_max_fit(lambda c: pr.StepResult(True, 5000.0), cap_mib=10_000)
    assert allok.value == 9984
    # startup failures carry no free-VRAM number: plain bisection takes over
    res = pr.search_max_fit(lambda c: pr.StepResult(c <= 6144, None, None if c <= 6144 else "oom_at_load"),
                            cap_mib=TOTAL)  # fmt: skip
    assert res.value == 6144 and len(res.steps) <= 8
    # a cap below one step
    assert pr.search_max_fit(lambda c: pr.StepResult(True, 9e3), cap_mib=100).value is None


def test_max_fit_never_probes_a_value_twice():
    seen = []

    def ev(c):
        seen.append(c)
        return fake_vram(5000, 1.0, 300)(c)

    pr.search_max_fit(ev, cap_mib=TOTAL)
    assert len(seen) == len(set(seen))


@pytest.mark.parametrize("smallest", [0, 1, 5, 17, 39, 40])
def test_n_fit_bisection_finds_the_smallest_passing_n(smallest):
    res = pr.search_n_fit(lambda n: pr.StepResult(n >= smallest, 1000.0 + n), n_layer=40)
    assert res.value == smallest and res.verified and len(res.steps) <= 6
    assert pr.search_n_fit(lambda n: pr.StepResult(False, 0.0), n_layer=40).value is None


# ------------------------------------------------------------------ the cache


BASE = dict(context=32768, ubatch=2048, batch=2048, cache_type_k="q8_0", cache_type_v="q8_0",
            flash_attn="on", parallel=1, cpu_moe=True)  # fmt: skip


def key(kind="max_fit", fields=None, **kw):
    args = dict(d_max=24576, llama_commit="c" * 40, model_sha256="b" * 64, gpu_total_mib=16311.0)
    return pr.probe_key(kind, fields or BASE, **{**args, **kw})


def test_probe_key_depends_on_what_changes_the_vram_picture():
    k = key()
    assert k == key()  # stable
    assert key(fields={**BASE, "context": 65536}) != k
    assert key(fields={**BASE, "ubatch": 4096}) != k
    assert key(fields={**BASE, "cache_type_k": "f16"}) != k
    assert key(fields={**BASE, "spec_type": "draft-mtp", "spec_draft_n_max": 2}) != k  # MTP on
    assert key(fields={**BASE, "spec_type": "none"}) == key(fields={**BASE, "spec_type": None})
    # WP12: with MTP on, the draft length is part of the key (the draft context costs VRAM)
    mtp = {**BASE, "spec_type": "draft-mtp"}
    ks = {n: key(fields={**mtp, "spec_draft_n_max": n}) for n in (1, 2, 3)}
    assert len(set(ks.values()) | {k}) == 4
    assert ks[2] == key(fields={**mtp, "spec_draft_n_max": 2})  # stable
    off = {**BASE, "spec_type": None, "spec_draft_n_max": None}
    assert (
        key(fields={**BASE, "spec_type": "none", "spec_draft_n_max": None}) == key(fields=off) == k
    )
    assert key("n_fit") != k and key(d_max=49152) != k
    assert key(llama_commit="d" * 40) != k and key(model_sha256="e" * 64) != k
    assert key(gpu_total_mib=8000.0) != k
    # the searched quantities are not part of the key
    assert key(fields={**BASE, "moe_cache_mib": 1024}) == k
    assert key(fields={**BASE, "n_cpu_moe": 5}) == k


def test_max_fit_differs_with_the_draft_length_in_a_fake_vram_model():
    """WP12: the MTP head and its draft context take VRAM that grows with the draft length, so the
    largest cache that passes is smaller (and a different cache entry) for a longer draft."""

    def with_draft(n):
        return fake_vram(base=6655 + 350 * n, slope=1.0, lm=0)

    found = {n: pr.search_max_fit(with_draft(n), cap_mib=TOTAL).value for n in (0, 1, 2, 3)}
    assert len(set(found.values())) == 4 and found[0] > found[1] > found[2] > found[3]
    assert all(v % pr.STEP_MIB == 0 for v in found.values())
    keys = {
        n: key(fields={**BASE, "spec_type": "draft-mtp", "spec_draft_n_max": n}) for n in (1, 2, 3)
    }
    cache = {k: found[n] for n, k in keys.items()}
    assert len(cache) == 3 and sorted(cache.values(), reverse=True) == [
        found[1],
        found[2],
        found[3],
    ]


def test_cache_is_append_only_and_the_latest_entry_wins(tmp_path):
    c = pr.ProbeCache(tmp_path / "p/cache.jsonl")
    assert c.get("k1") is None
    c.put("k1", {"value": 1})
    c.put("k2", {"value": 2})
    c.put("k1", {"value": 3})
    assert c.get("k1")["value"] == 3 and c.get("k2")["value"] == 2
    assert len((tmp_path / "p/cache.jsonl").read_text().splitlines()) == 3


# ------------------------------------------------------------------ resolution against the mock

SPEC = """
name = "probe"
repetitions = 1
shuffle_seed = 3
max_restarts = 0
[defaults]
metrics = true
log_verbosity = 4
[axes.context]
"32K" = { context = 32768 }
[axes.placement]
P1 = { fit = "on" }
P6 = { cpu_moe = true, moe_cache_mib = "@max_fit" }
P7 = { cpu_moe = true, moe_cache_mib = "@max_fit-2048" }
P8 = { fit = "off", n_cpu_moe = "@n_fit(P1)" }
P9 = { fit = "off", n_cpu_moe = "@n_fit(P1)-2" }
[[cells]]
name = "{placement}-{context}"
profile = "candidate"
product = { placement = ["P1", "P6", "P7", "P8", "P9"], context = ["32K"] }
"""
# the mock card: 16,000 MiB, 6,000 base, 655 for the 32K context, so cache <= 9,345 - 512
BEHAVIOR = {"vram_base_mib": 6000.0, "vram_total_mib": 16000.0, "vram_per_layer_mib": 100.0}
MAX_FIT = 8704  # largest multiple of 256 with 6,655 + c + 512 <= 16,000


def probe_env(tmp_path, port, behavior=None):
    env = make_env(tmp_path, port, {**BEHAVIOR, **(behavior or {})}, total_mib=16000.0)
    env.settle_s = 0.12  # the 20 Hz fake sampler needs a moment to see the end of the request
    # make_env's sleep only records; the probe reads the sampler's rows right after the
    # settle, so without a real wait the rows race the sampler thread (A13). Record AND wait.
    sleeps: list[float] = []

    def sleep(s):
        sleeps.append(s)
        time.sleep(s)

    env.sleep = sleep
    return env


def run_probe_session(tmp_path, port, sid="p1", behavior=None, spec=SPEC, env=None):
    env = env or probe_env(tmp_path, port, behavior)
    sp = write_spec(tmp_path, spec)
    sess = Session(env, load_sweep(sp), sp, sid)
    return sess, sess.run(), env


def resolutions(sess):
    return {json.loads(x)["cell"]: json.loads(x) for x in
            (sess.dir / "resolutions.jsonl").read_text().splitlines()}  # fmt: skip


def test_tokens_are_resolved_at_run_time_and_recorded(tmp_path, free_port):
    sess, code, env = run_probe_session(tmp_path, free_port)
    assert code == 0
    res = resolutions(sess)
    p6, p7 = res["P6-32K"], res["P7-32K"]
    assert (
        p6["fields"]["moe_cache_mib"] == MAX_FIT and p7["fields"]["moe_cache_mib"] == MAX_FIT - 2048
    )
    # the cell order is shuffled: whichever of P6 and P7 comes first probes, the other reuses it
    infos = [p6["resolution"]["moe_cache_mib"], p7["resolution"]["moe_cache_mib"]]
    assert sorted(i["source"] for i in infos) == ["binary_search", "probe_cache"]
    searched = next(i for i in infos if i["source"] == "binary_search")
    assert 2 <= searched["n_steps"] <= 6 and searched["verified"] is True
    # N_fit comes from P1's log (17 expert layers on the CPU), with its provenance
    p8, p9 = res["P8-32K"], res["P9-32K"]
    assert p8["fields"]["n_cpu_moe"] == 17 and p9["fields"]["n_cpu_moe"] == 15
    info = p8["resolution"]["n_cpu_moe"]
    assert info["source"] == "p1_log" and info["source_cell"] == "P1-32K"
    assert (
        info["p1_expert_layers_on_cpu"] == 17 and info["p1_first_partial_layer_overflow"] == "MOE"
    )
    assert "p1_realized_peak_used_mib" in info and "p1_realized_min_free_mib" in info
    assert (
        p9["resolution"]["n_cpu_moe"]["base"] == 17 and p9["resolution"]["n_cpu_moe"]["value"] == 15
    )
    # the cell summaries carry the resolution; the resolved TOML carries the value
    summ = json.loads(next((sess.dir / "cells").glob("P8-32K-*.json")).read_text())
    assert summ["resolution"]["n_cpu_moe"]["p1_expert_layers_on_cpu"] == 17
    assert "n_cpu_moe = 17" in (sess.dir / "resolved/P8-32K.toml").read_text()
    assert "moe_cache_mib = 8704" in (sess.dir / "resolved/P6-32K.toml").read_text()
    # every probing step is recorded, with its free VRAM
    steps = [json.loads(x) for x in (sess.dir / "probes.jsonl").read_text().splitlines()]
    assert len(steps) == searched["n_steps"]
    assert all(s["kind"] == "max_fit" for s in steps)
    ok = {s["value"]: s["ok"] for s in steps}
    assert ok[MAX_FIT] is True and ok.get(MAX_FIT + 256) is False
    assert next(s for s in steps if s["value"] == MAX_FIT)["free_mib"] >= 512
    # the probing cache got the entry; a second session reuses it without a single step
    cache = [json.loads(x) for x in env.probe_cache.read_text().splitlines()]
    assert len(cache) == 1 and cache[0]["value"] == MAX_FIT and cache[0]["kind"] == "max_fit"
    sess2, code2, _ = run_probe_session(tmp_path, free_port, sid="p2", env=env)
    assert code2 == 0 and not (sess2.dir / "probes.jsonl").exists()
    assert resolutions(sess2)["P6-32K"]["resolution"]["moe_cache_mib"]["source"] == "probe_cache"


def test_the_hash_of_a_resolved_cell_is_stable_across_a_resume(tmp_path, free_port):
    sess, _, env = run_probe_session(tmp_path, free_port)
    reqs, _ = read_records(sess)
    h = {r["cell"]: r["config_hash"] for r in reqs}
    # wipe the cache: a re-probe could differ, but the session's own resolution is reused
    env.probe_cache.unlink()
    sp = tmp_path / "spec.toml"
    s2 = Session(env, load_sweep(sp), sp, "p1")
    assert s2.run(resume=True) == 0
    reqs2, _ = read_records(s2)
    assert {r["cell"]: r["config_hash"] for r in reqs2} == h and len(reqs2) == len(reqs)
    assert not (s2.dir / "probes.jsonl").read_text().count("\n") > len(
        sess.dir.joinpath("probes.jsonl").read_text().splitlines()
    )  # no new probing steps


def test_fit_that_changes_an_explicit_placement_fails_the_probe(tmp_path, free_port):
    sess, code, _ = run_probe_session(tmp_path, free_port, behavior={"fit_intervene": True})
    assert code == 0
    _, cells = read_records(sess)
    by = {c["cell"]: c for c in cells if c["final"]}
    assert by["P6-32K"]["status"] == "not_applicable" and by["P7-32K"]["status"] == "not_applicable"
    steps = [json.loads(x) for x in (sess.dir / "probes.jsonl").read_text().splitlines()]
    assert steps and {s["reason"] for s in steps} == {"fit_intervened"}


def test_n_fit_minus_two_below_zero_is_not_applicable(tmp_path, free_port):
    sess, _, _ = run_probe_session(tmp_path, free_port, behavior={"n_part": 1})
    res = resolutions(sess)
    assert res["P8-32K"]["fields"]["n_cpu_moe"] == 1
    assert res["P9-32K"]["fields"] is None and "not applicable" in res["P9-32K"]["not_applicable"]
    _, cells = read_records(sess)
    assert next(c for c in cells if c["cell"] == "P9-32K")["status"] == "not_applicable"


def test_n_fit_falls_back_to_bisection_when_p1_did_not_run(tmp_path, free_port):
    # P1 did not run, so there is no log to read; the mock card needs N >= 11 layers on the CPU:
    # used = 6000 + 655 + (40 - N) * 300, free = 16000 - used >= 512  ->  N >= 11
    env = probe_env(tmp_path, free_port, {"vram_per_layer_mib": 300.0})
    sess = Session(env, load_sweep(write_spec(tmp_path, SPEC)), tmp_path / "spec.toml", "p1")
    sess.open(resume=False)
    cell = next(c for c in sess.cells if c.name == "P8-32K")
    value, info = sess.n_fit(
        cell, "P1-32K", {"fit": "off", "context": 32768, "metrics": True, "log_verbosity": 4}
    )
    assert info["source"] == "binary_search" and value == 11 and info["verified"]
    assert 4 <= info["n_steps"] <= 7


def test_probe_steps_use_the_longest_request_and_do_not_wait_for_idle(tmp_path, free_port):
    seen = []
    env = probe_env(tmp_path, free_port)
    real = env.preconditions_fn
    env.preconditions_fn = lambda idle: (seen.append(idle), real(idle))[1]
    run_probe_session(tmp_path, free_port, env=env)
    assert False in seen and True in seen  # probes skip the idle wait, cells do not
    calls = env.provider.calls
    assert ("pair", 3000, 0) in calls  # the deepest depth of the context


def test_cell_records_for_probe_free_sessions_still_validate(tmp_path, free_port):
    sess, _, _ = run_probe_session(tmp_path, free_port)
    reqs, cells = read_records(sess)
    assert all(rec.RequestRecord.model_validate(r) for r in reqs)
    assert all(rec.CellRecord.model_validate(c) for c in cells)
    assert events(sess)


MTP_SPEC = (
    SPEC.split("[[cells]]")[0].replace(
        "[axes.context]",
        """[axes.mtp]
mtp0 = {}
mtp1 = { spec_type = "draft-mtp", spec_draft_n_max = 1 }
mtp3 = { spec_type = "draft-mtp", spec_draft_n_max = 3 }
[axes.context]""",
    )
    + """[[cells]]
name = "{placement}-{context}-{mtp}"
profile = "candidate"
product = { placement = ["P6"], context = ["32K"], mtp = ["mtp0", "mtp1", "mtp3"] }
"""
)


def test_max_fit_is_probed_per_draft_length_for_mtp_cells(tmp_path, free_port):
    """WP12: P6 cells with MTP on probe their own max-fit (the draft context costs VRAM in the mock),
    each under its own cache key, and a second session reuses all three."""
    behavior = {"vram_per_draft_mib": 400.0}
    env = probe_env(tmp_path, free_port, behavior)
    sess, code, _ = run_probe_session(tmp_path, free_port, spec=MTP_SPEC, env=env)
    assert code == 0
    res = resolutions(sess)
    got = {n: res[f"P6-32K-mtp{n}"]["fields"]["moe_cache_mib"] for n in (0, 1, 3)}
    # 6,655 + 400 n + cache + 512 <= 16,000, in steps of 256
    assert got == {0: 8704, 1: 8192, 3: 7424}
    assert {res[f"P6-32K-mtp{n}"]["resolution"]["moe_cache_mib"]["source"] for n in (0, 1, 3)} == {
        "binary_search"
    }
    keys = {res[f"P6-32K-mtp{n}"]["resolution"]["moe_cache_mib"]["probe_key"] for n in (0, 1, 3)}
    assert len(keys) == 3 and len(env.probe_cache.read_text().splitlines()) == 3
    for n in (1, 3):  # the resolved config carries the MTP flags the probe ran with
        toml = (sess.dir / f"resolved/P6-32K-mtp{n}.toml").read_text()
        assert 'spec_type = "draft-mtp"' in toml and f"spec_draft_n_max = {n}" in toml
    sess2, code2, _ = run_probe_session(tmp_path, free_port, sid="p2", spec=MTP_SPEC, env=env)
    assert code2 == 0 and not (sess2.dir / "probes.jsonl").exists()
    assert {
        n: resolutions(sess2)[f"P6-32K-mtp{n}"]["fields"]["moe_cache_mib"] for n in (0, 1, 3)
    } == got
