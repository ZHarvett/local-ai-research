"""The sweep runner against the mock llama-server: protocol, flags, failure paths, resume, the
precondition retries and the re-run mode. No GPU: the real launch and stop scripts start a mock."""

from __future__ import annotations

import json
import time

import pytest

from smallpc.config import load_sweep
from smallpc.sweep import provenance
from smallpc.sweep import records as rec
from smallpc.sweep.core import HardAbort, ProvenanceError, TransientAbort
from smallpc.sweep.session import Session
from sweep_fakes import GOOD_PRE, events, make_env, mini_spec, read_records


def run_session(tmp_path, port, behavior=None, *, reps=2, restarts=2, canary=False, sid="s1",
                resume=False, env=None, **env_kw):  # fmt: skip
    env = env or make_env(tmp_path, port, behavior, **env_kw)
    sp = mini_spec(tmp_path, reps=reps, restarts=restarts, canary=canary)
    sess = Session(env, load_sweep(sp), sp, sid)
    code = sess.run(resume=resume)
    return sess, code, env


def measured(reqs, cell=None, kind=None):
    return [r for r in reqs if r["role"] == "measured" and (cell is None or r["cell"] == cell)
            and (kind is None or r["kind"] == kind)]  # fmt: skip


# ------------------------------------------------------------------ the protocol


def test_protocol_records_and_summaries(tmp_path, free_port):
    sess, code, _ = run_session(tmp_path, free_port, canary=True)
    assert code == 0
    reqs, cells = read_records(sess)
    # 3 cells x 2 reps x (short + 3 x (A + B)) measured requests, 2 warm-ups per server start
    for cell in ("Pa-32K", "Pb-32K", "stock-32K"):
        assert len(measured(reqs, cell, "short")) == 2
        assert len(measured(reqs, cell, "A")) == 6 and len(measured(reqs, cell, "B")) == 6
        assert sum(r["warmup"] and r["cell"] == cell for r in reqs) == 2
    assert not rec.find_duplicates(reqs)
    assert all(rec.RequestRecord.model_validate(r) for r in reqs)  # every line validates
    assert [c["status"] for c in cells if c["cell"] != "canary-start"][0] == "complete"
    # the final cell record names the server instance that ran the last repetitions
    for c in (c for c in cells if c["final"] and c["status"] == "complete"):
        last_req = [r for r in reqs if r["cell"] == c["cell"] and not r["warmup"]][-1]
        assert c["server_instance"] == last_req["server_instance"] == 0
    # the repetition order: short point first, then A before its B, all depths once
    for cell, rep in {(r["cell"], r["repetition"]) for r in measured(reqs)}:
        rr = sorted((r for r in measured(reqs, cell) if r["repetition"] == rep),
                    key=lambda r: r["position"])  # fmt: skip
        assert [r["kind"] for r in rr] == ["short", "A", "B", "A", "B", "A", "B"]
        assert [r["depth"] for r in rr[1::2]] == rr[0]["depth_order"]
        assert sorted(rr[0]["depth_order"]) == [1000, 2000, 3000]
    a = measured(reqs, "Pa-32K", "A")[0]
    b = measured(reqs, "Pa-32K", "B")[0]
    assert a["n_predict"] == 0 and a["stream"] is False and a["predicted_n"] == 1
    assert b["n_predict"] == 400 and b["stream"] is True and b["client"]["ttft_s"] is not None
    assert a["client"]["ttft_s"] is None and a["cache_n"] == 0 and a["prompt_n"] == a["depth"]
    assert b["cache_n"] == b["depth"] and b["prompt_n"] == 300 and b["id_slot"] == 0
    assert a["code_commit"] == "a" * 10 and b["snapshot_id"] == "snap0000test0000"
    assert b["telemetry"]["file"].startswith("telemetry/") and b["telemetry"]["file"].endswith(
        ".gz"
    )
    assert (sess.dir / b["telemetry"]["file"]).exists()
    assert not list((sess.dir / "telemetry").glob("*.csv"))  # all gzipped when the cell finished
    # cell summary: props, parsed log, windows, phase timings, vram
    summ = json.loads((sess.dir / "cells" / f"Pa-32K-{a['config_hash'][:8]}.json").read_text())
    inst = summ["instances"][0]
    assert inst["props"]["total_slots"] == 1 and inst["props"]["n_ctx_per_slot"] == 32768
    assert inst["props"]["kv_unified"] is False
    assert inst["parsed"]["placement"]["expert_layers_on_cpu"] == 17
    assert len(inst["windows"]) == 2 and inst["windows"][0]["flags"] == []
    assert {"preconditions", "launch", "warmup", "shutdown", "parse"} <= set(inst["phases_s"])
    assert inst["stop"]["method"] == "sigint" and inst["startup_excerpt"]
    assert "-lv" in summ["argv"] and summ["argv"][summ["argv"].index("-lv") + 1] == "4"
    assert (sess.dir / "snapshots/snap0000test0000.json").exists()


def test_stock_cell_uses_four_unified_slots_and_records_id_slot(tmp_path, free_port):
    sess, code, _ = run_session(tmp_path, free_port)
    reqs, _ = read_records(sess)
    stock = measured(reqs, "stock-32K")
    summ = next((sess.dir / "cells").glob("stock-32K-*.json"))
    props = json.loads(summ.read_text())["instances"][0]["props"]
    assert props["total_slots"] == 4 and props["kv_unified"] is True
    assert props["n_ctx_per_slot"] == 32768
    assert all(isinstance(r["id_slot"], int) for r in stock)
    assert not any(r["flags"] for r in stock)  # B finds A's slot by prefix


def test_id_slot_is_null_when_the_response_has_none(tmp_path, free_port):
    sess, _, _ = run_session(tmp_path, free_port, {"no_id_slot": True}, reps=1)
    reqs, _ = read_records(sess)
    assert all(r["id_slot"] is None for r in reqs)


def test_resolved_toml_renders_the_same_argv_and_hash(tmp_path, free_port):
    from smallpc.config import load_server
    from smallpc.render import render_argv

    sess, _, env = run_session(tmp_path, free_port, reps=1)
    reqs, _ = read_records(sess)
    for cell in ("Pa-32K", "stock-32K"):
        r = measured(reqs, cell)[0]
        summ = json.loads(next((sess.dir / "cells").glob(f"{cell}-*.json")).read_text())
        cfg = load_server(sess.dir / summ["resolved_config"])
        argv = render_argv(cfg, env.machine, env.model)
        # the summary is scrubbed (the temp path holds the user name), so compare by hash
        assert provenance.config_hash(argv, "b" * 64, "c" * 40) == r["config_hash"]
        assert len(argv) == len(summ["argv"])


# ------------------------------------------------------------------ flags


def flagged(reqs, flag):
    return [r for r in measured(reqs) if flag in r["flags"]]


def test_warm_prefill_on_request_a(tmp_path, free_port):
    # A requests are counted per server: index 0 of cell 1's first repetition
    sess, _, _ = run_session(tmp_path, free_port, {"warm_prefill_A": {"on": [0], "cache_n": 100}},
                             reps=1)  # fmt: skip
    reqs, _ = read_records(sess)
    hit = flagged(reqs, "warm_prefill")
    assert len(hit) == 3 and {r["kind"] for r in hit} == {"A"}  # first A of each of the 3 cells
    assert all(r["cache_n"] == 100 and "accounting" not in r["flags"] for r in hit)
    assert not flagged(reqs, "cache_miss")


def test_cache_miss_on_request_b(tmp_path, free_port):
    sess, _, _ = run_session(tmp_path, free_port, {"cache_miss_B": {"on": [1]}}, reps=1)
    reqs, _ = read_records(sess)
    hit = flagged(reqs, "cache_miss")
    assert len(hit) == 3 and {r["kind"] for r in hit} == {"B"}
    assert all(r["cache_n"] == 0 and r["prompt_n"] == r["depth"] + 300 for r in hit)
    assert not flagged(reqs, "accounting")  # a miss keeps prompt_n + cache_n = d + append


def test_short_gen_on_request_b(tmp_path, free_port):
    sess, _, _ = run_session(tmp_path, free_port, {"short_gen_B": {"on": [0], "value": 50}}, reps=1)
    reqs, _ = read_records(sess)
    hit = flagged(reqs, "short_gen")
    assert len(hit) == 3 and all(r["predicted_n"] == 50 and r["stop_type"] == "eos" for r in hit)


def test_accounting_flag_on_a_wrong_total(tmp_path, free_port):
    sess, _, _ = run_session(tmp_path, free_port, {"wrong_accounting": {"on": [0], "value": 7, "cls": "A"}},
                             reps=1)  # fmt: skip
    reqs, _ = read_records(sess)
    hit = flagged(reqs, "accounting")
    assert len(hit) == 3 and {r["kind"] for r in hit} == {"A"}


def test_thermal_and_paging_flags_attach_to_the_repetition_window(tmp_path, free_port):
    state = {"on": False}

    def hook(row):
        if state["on"]:
            row["reason_hw_thermal_slowdown"] = True
            row["server_vmswap_kib"] = 512.0

    env = make_env(tmp_path, free_port, hook=hook)
    sp = mini_spec(tmp_path, reps=2)
    sess = Session(env, load_sweep(sp), sp, "s1")
    # slow the mock slightly so the 20 Hz sampler gets rows inside every window
    env.provider.get  # noqa: B018
    orig = env.server_factory

    def factory():
        srv = orig()
        srv.env["MOCK_BEHAVIOR"] = json.dumps(
            {"vram_file": str(tmp_path / "vram.txt"), "slow_s": 0.06}
        )
        return srv

    env.server_factory = factory
    state["on"] = True
    assert sess.run() == 0
    reqs, _ = read_records(sess)
    m = measured(reqs)
    assert m and all({"thermal", "paging"} <= set(r["flags"]) for r in m)
    assert all(r["flag_detail"]["window_flags"] == ["thermal", "paging"] for r in m)
    summ = json.loads(next((sess.dir / "cells").glob("Pa-32K-*.json")).read_text())
    w = summ["instances"][0]["windows"][0]
    assert w["thermal"]["flag"] == "thermal" and w["paging"]["server_vmswap_max_kib"] == 512.0
    # warm-ups carry no window flags
    assert not any("thermal" in r["flags"] for r in reqs if r["role"] == "warmup")


# ------------------------------------------------------------------ failure paths


def test_oom_at_start_is_did_not_fit_with_a_reason(tmp_path, free_port):
    sess, code, _ = run_session(tmp_path, free_port, {"oom_at_start": True}, reps=1)
    assert code == 0  # the session goes on: every cell is recorded
    reqs, cells = read_records(sess)
    assert not measured(reqs)
    final = [c for c in cells if c["role"] == "measured"]
    assert len(final) == 3 and all(c["status"] == "did_not_fit" and c["final"] for c in final)
    assert all(c["reason"] == "oom_at_load" and c["flags"] == ["did_not_fit"] for c in final)
    assert all(c["exit_code"] == 1 for c in final)
    summ = json.loads((sess.dir / final[0]["summary_file"]).read_text())
    assert "out of memory" in summ["instances"][0]["launch"]["output"] or summ["instances"][0][
        "startup_excerpt"] is not None  # fmt: skip


def test_startup_failure_without_an_oom_pattern(tmp_path, free_port):
    env = make_env(tmp_path, free_port)
    orig = env.server_factory

    def factory():
        srv = orig()
        srv.env["MOCK_BEHAVIOR"] = json.dumps({"vram_total_mib": -1})  # fails like an OOM
        return srv

    env.server_factory = factory
    sess, _, _ = run_session(tmp_path, free_port, env=env, reps=1)
    _, cells = read_records(sess)
    assert {c["reason"] for c in cells if c["role"] == "measured"} == {"oom_at_load"}


def test_context_too_small_is_did_not_fit_context(tmp_path, free_port):
    env = make_env(tmp_path, free_port)
    env.provider.d = [40000]  # 40,000 + 300 + 400 does not fit a 32K slot
    sess, _, _ = run_session(tmp_path, free_port, env=env, reps=1)
    reqs, cells = read_records(sess)
    assert not measured(reqs)
    assert {c["reason"] for c in cells if c["role"] == "measured"} == {"context"}
    summ = json.loads(next((sess.dir / "cells").glob("Pa-32K-*.json")).read_text())
    assert summ["instances"][0]["context_check"]["depths_fit"] == {"40000": False}


def test_stock_with_split_context_does_not_fit(tmp_path, free_port):
    # candidate cells use -np 1; a non-unified 4-slot server has C/4 per slot
    env = make_env(tmp_path, free_port)
    env.provider.d = [9000]  # fits 32768 but not 32768 // 4 = 8192
    spec = mini_spec(tmp_path).read_text().replace(
        '[[cells]]\nname = "stock-{context}"',
        '[[cells]]\nname = "np4-{context}"\nprofile = "candidate"\nproduct = { context = ["32K"] }\n'
        "[cells.set]\nparallel = 4\n[[cells]]\nname = \"stock-{context}\"")  # fmt: skip
    sp = tmp_path / "np4.toml"
    sp.write_text(spec)
    sess = Session(env, load_sweep(sp), sp, "s1")
    sess.run()
    _, cells = read_records(sess)
    by = {c["cell"]: c for c in cells}
    assert by["np4-32K"]["reason"] == "context" and by["stock-32K"]["status"] == "complete"


def test_server_crash_mid_cell_restarts_and_runs_only_missing_repetitions(tmp_path, free_port):
    marker = tmp_path / "crashed"
    # warm-up = 2 completions, repetition 0 = 7; crash on the 12th (inside repetition 1)
    sess, code, _ = run_session(tmp_path, free_port,
                                {"crash_after": 12, "crash_marker": str(marker)}, reps=2)  # fmt: skip
    assert code == 0 and marker.exists()
    reqs, cells = read_records(sess)
    first = next(c for c in cells if c["cell"] == "canary-start" or c["status"] != "complete")
    assert not rec.find_duplicates(reqs)
    # the crashed cell: both repetitions present exactly once; two warm-ups per server start
    died = [c for c in cells if c["status"] == "server_died"]
    assert len(died) == 1 and died[0]["reason"] == "crash_mid_cell" and not died[0]["final"]
    cell = died[0]["cell"]
    for rep in (0, 1):
        assert len([r for r in measured(reqs, cell, "A") if r["repetition"] == rep]) == 3
    warm = [r for r in reqs if r["cell"] == cell and r["warmup"]]
    assert len(warm) == 4 and len({r["server_run_id"] for r in warm}) == 2
    ev = events(sess)
    disc = [e for e in ev if e["event"] == "discarded_partial"]
    assert len(disc) == 1 and disc[0]["reason"] == "crash_mid_cell" and disc[0]["requests"]
    assert any(e["event"] == "cell_restart" for e in ev) and first
    final = [c for c in cells if c["cell"] == cell and c["final"]]
    assert final[0]["status"] == "complete"


def test_repeated_crashes_end_the_cell_as_did_not_fit(tmp_path, free_port):
    sess, code, _ = run_session(tmp_path, free_port, {"crash_after": 3}, reps=1, restarts=1)
    assert code == 0
    _, cells = read_records(sess)
    fin = [c for c in cells if c["final"]]
    assert {c["status"] for c in fin} == {"did_not_fit"}
    assert {c["reason"] for c in fin} == {"crash_mid_cell"}
    assert sum(c["status"] == "server_died" for c in cells) == 6  # 3 cells x 2 attempts


def test_timeout_and_hung_server_are_stopped_and_recorded(tmp_path, free_port, monkeypatch):
    from smallpc.sweep import client

    monkeypatch.setattr(client, "TIMEOUT_BASE_S", 1.0)
    monkeypatch.setattr(client, "PREFILL_FLOOR_TPS", 1e9)
    monkeypatch.setattr(client, "DECODE_FLOOR_TPS", 1e9)
    t0 = time.monotonic()
    sess, _, _ = run_session(tmp_path, free_port, {"hang_after": 3}, reps=1, restarts=0)
    ev = events(sess)
    died = [e for e in ev if e["event"] == "server_died"]
    assert died and {e["reason"] for e in died} == {"hung_server"}
    _, cells = read_records(sess)
    assert {c["reason"] for c in cells if c["final"]} == {"hung_server"}
    # the hung mock ignores nothing, so SIGINT stops it; the whole thing stayed fast
    assert time.monotonic() - t0 < 60


def test_hung_server_that_ignores_sigint_is_killed(tmp_path, free_port, monkeypatch):
    from smallpc.sweep import client

    monkeypatch.setattr(client, "TIMEOUT_BASE_S", 1.0)
    monkeypatch.setattr(client, "PREFILL_FLOOR_TPS", 1e9)
    monkeypatch.setattr(client, "DECODE_FLOOR_TPS", 1e9)
    env = make_env(tmp_path, free_port, {"hang_after": 3, "ignore_sigint": True})
    orig = env.server_factory

    def factory():
        s = orig()
        s.stop = lambda timeout_s=60, _s=s, _o=s.stop: _o(2)  # shorten the SIGINT wait
        return s

    env.server_factory = factory
    sess, _, _ = run_session(tmp_path, free_port, env=env, reps=1, restarts=0)
    stops = [json.loads(p.read_text()) for p in (tmp_path / "logs").glob("*/stop-status.json")]
    assert any(s["method"] == "sigkill" for s in stops)
    assert list((tmp_path / "logs").glob("*/exit-code")) != []


def test_request_timeout_on_a_healthy_slow_server(tmp_path, free_port, monkeypatch):
    from smallpc.sweep import client

    monkeypatch.setattr(client, "TIMEOUT_BASE_S", 0.5)
    monkeypatch.setattr(client, "PREFILL_FLOOR_TPS", 1e9)
    monkeypatch.setattr(client, "DECODE_FLOOR_TPS", 1e9)
    sess, _, _ = run_session(tmp_path, free_port, {"slow_s": 1.5}, reps=1, restarts=0)
    died = [e for e in events(sess) if e["event"] == "server_died"]
    assert died and {e["reason"] for e in died} == {"request_timeout"}


def test_timeout_scales_with_the_prompt():
    from smallpc.sweep.client import timeout_s

    assert timeout_s(98_304 + 3000, 400) > 600  # a 96K pair never times out falsely
    assert timeout_s(98_304, 0) > timeout_s(8192, 0) + 400
    assert timeout_s(100, 0) >= 120


# ------------------------------------------------------------------ resume


def test_resume_after_a_kill_mid_cell_has_no_duplicates(tmp_path, free_port):
    env = make_env(tmp_path, free_port)
    sp = mini_spec(tmp_path, reps=2)
    sess = Session(env, load_sweep(sp), sp, "s1")
    # interrupt inside the second cell's second repetition: raise from the provider
    seen: set = set()
    real_get = env.provider.get

    def get(kind, length, repetition=0, base_url=None):
        key = (kind, length, repetition)
        if kind == "pair" and repetition == 1 and sess_cells_done(sess) >= 1:
            if key in seen:  # the second get is the measurement itself (the first is the prefetch)
                raise KeyboardInterrupt
            seen.add(key)
        return real_get(kind, length, repetition, base_url)

    env.provider.get = get
    assert sess.run() == 130
    reqs1, cells1 = read_records(sess)
    n1 = len(reqs1)
    assert any(c["status"] == "interrupted" for c in cells1)
    # nothing is left running: every server this session started has exited
    from smallpc.sweep.server import pid_alive

    pidfiles = list((tmp_path / "logs").glob("*/server.pid"))
    assert pidfiles
    assert not [
        p
        for p in pidfiles
        if pid_alive(int(p.read_text()), (p.parent / "server.start").read_text().strip())
    ]
    # resume with a new Session (a new process would do the same)
    env.provider.get = real_get
    sess2 = Session(env, load_sweep(sp), sp, "s1")
    assert sess2.run(resume=True) == 0
    reqs, cells = read_records(sess2)
    assert len(reqs) > n1 and not rec.find_duplicates(reqs)
    finals = {c["cell"] for c in cells if c["final"] and c["status"] == "complete"}
    assert finals == {"Pa-32K", "Pb-32K", "stock-32K"}
    for cell in finals:
        for rep in (0, 1):
            assert len([r for r in measured(reqs, cell, "B") if r["repetition"] == rep]) == 3
    # the cell that was running was restarted with a new server and a new warm-up
    cut = next(c["cell"] for c in cells1 if c["status"] == "interrupted")
    warm = [r for r in reqs if r["cell"] == cut and r["warmup"]]
    assert len({r["server_run_id"] for r in warm}) == 2 and len(warm) == 4
    # a completed cell is skipped on resume: no new server for it
    done_first = next(
        c["cell"] for c in cells1 if c["status"] == "complete" and c["role"] == "measured"
    )
    assert len([e for e in events(sess2) if e["event"] == "server_start"
                and e["cell"] == done_first]) == 1  # fmt: skip
    assert any(e["event"] == "cell_skipped" and e["cell"] == done_first for e in events(sess2))
    assert not [r for r in reqs if r["utc"] == "" or r["batch_size"] < 1]


def sess_cells_done(sess) -> int:
    return len([c for c in sess.store.load().cells if c["final"] and c["role"] == "measured"])


def test_a_torn_last_line_and_incomplete_batches_are_ignored(tmp_path, free_port):
    sess, _, _ = run_session(tmp_path, free_port, reps=1)
    path = sess.store.path
    good = len(read_records(sess)[0])
    lines = path.read_text().splitlines()
    # a batch missing its last line, and a torn line without a newline at the end
    victim = json.loads(lines[-3])
    victim.update(batch_id="deadbeef0000", batch_index=0, batch_size=2)
    with open(path, "a") as f:
        f.write(json.dumps(victim) + "\n")
        f.write('{"record_type": "request", "batch_id": "abc", "batch_')
    ld = sess.store.load()
    assert ld.torn_lines == 1 and ld.incomplete_batches == 1 and len(ld.requests) == good
    # appending after a torn line starts on a fresh line and the new batch is read in full
    sess.store.append_batch(rec.stamp_batch([dict(victim)]))
    assert len(sess.store.load().requests) == good + 1


def test_resume_refuses_a_changed_spec_manifest_sampling_or_filter(tmp_path, free_port):
    sess, _, env = run_session(tmp_path, free_port, reps=1)
    sp = mini_spec(tmp_path, reps=1)
    # spec changed
    sp.write_text(sp.read_text() + "\n# edited\n")
    with pytest.raises(ProvenanceError, match="spec_sha256"):
        Session(env, load_sweep(sp), sp, "s1").open(resume=True)
    sp2 = mini_spec(tmp_path, reps=1)
    # manifest changed
    env.manifest_path.write_text('{"changed": true}')
    with pytest.raises(ProvenanceError, match="manifest_sha256"):
        Session(env, load_sweep(sp2), sp2, "s1").open(resume=True)
    env.manifest_path.write_text("{}")
    # filter changed
    with pytest.raises(ProvenanceError, match="filter"):
        Session(env, load_sweep(sp2), sp2, "s1", filters={"context": "32K"}).open(resume=True)
    # sampling section changed
    model = tmp_path / "model2.toml"
    model.write_text((env.model_path).read_text() + "\n[sampling.general]\ntemperature = 0.9\n")
    env.model_path = model
    with pytest.raises(ProvenanceError, match="sampling_sha256"):
        Session(env, load_sweep(sp2), sp2, "s1").open(resume=True)


def test_resume_with_a_new_code_commit_warns_and_stamps_new_records(tmp_path, free_port):
    env = make_env(tmp_path, free_port)
    sp = mini_spec(tmp_path, reps=1)
    sess = Session(env, load_sweep(sp), sp, "s1")
    env.provider.get = _interrupt_at(env.provider.get, sess, cells_done=1)
    assert sess.run() == 130
    env.git = {**env.git, "commit": "b" * 40, "short": "b" * 10}
    env.provider.get = type(env.provider).get.__get__(env.provider)
    sess2 = Session(env, load_sweep(sp), sp, "s1")
    assert sess2.run(resume=True) == 0
    reqs, _ = read_records(sess2)
    assert {r["code_commit"] for r in reqs} == {"a" * 10, "b" * 10}
    warn = [
        e for e in events(sess2) if e["event"] == "warning" and e["kind"] == "code_commit_changed"
    ]
    assert len(warn) == 1
    runs = json.loads((sess2.dir / "session.json").read_text())["runs"]
    assert len(runs) == 2 and runs[1]["warnings"] and runs[1]["resumed"]


def _interrupt_at(real_get, sess, cells_done):
    def get(kind, length, repetition=0, base_url=None):
        if kind == "pair" and sess_cells_done(sess) >= cells_done:
            raise KeyboardInterrupt
        return real_get(kind, length, repetition, base_url)

    return get


def test_dirty_code_is_refused_for_a_new_session_unless_allowed(tmp_path, free_port):
    env = make_env(tmp_path, free_port)
    env.git = {**env.git, "dirty": True, "dirty_paths": ["src/x.py"]}
    sp = mini_spec(tmp_path, reps=1)
    with pytest.raises(ProvenanceError, match="uncommitted changes in src/x.py"):
        Session(env, load_sweep(sp), sp, "s1").open(resume=False)
    s = Session(env, load_sweep(sp), sp, "s2", allow_dirty=True)
    s.open(resume=False)
    sj = json.loads((s.dir / "session.json").read_text())
    assert sj["allow_dirty"] is True and sj["git"]["dirty"] is True


def test_session_json_records_the_provenance(tmp_path, free_port):
    sess, _, env = run_session(tmp_path, free_port, reps=1)
    sj = json.loads((sess.dir / "session.json").read_text())
    for k in ("spec_sha256", "manifest_sha256", "sampling_sha256"):
        assert len(sj[k]) == 64
    assert sj["git"]["commit"] == "a" * 40 and sj["git"]["dirty"] is False
    assert sj["model_sha256"] == "b" * 64 and sj["llama_cpp_commit"] == "c" * 40
    assert sj["cell_order"] == sess.order and sj["state"] == "complete" and sj["filters"] == {}


# ------------------------------------------------------------------ precondition retries


def test_transient_precondition_failures_are_retried_with_pauses(tmp_path, free_port):
    calls = {"n": 0}

    def pre(idle):
        calls["n"] += 1
        p = json.loads(json.dumps(GOOD_PRE))
        if calls["n"] <= 2:  # the first cell fails twice, then the CPU settles
            p.update(ok=False, aborts=["CPU not idle: busy 40% (limit 10.0%) after waiting 600 s"],
                     transient_aborts=["CPU not idle"])  # fmt: skip
        return p

    sleeps: list[float] = []
    sess, code, _ = run_session(tmp_path, free_port, reps=1, pre_fn=pre, sleeps=sleeps)
    assert code == 0 and [x for x in sleeps if x] == [600.0, 600.0]
    ev = [e for e in events(sess) if e["event"] in ("precondition", "precondition_wait")]
    assert [e["event"] for e in ev[:5]] == ["precondition", "precondition_wait", "precondition",
                                            "precondition_wait", "precondition"]  # fmt: skip
    assert [e.get("ok") for e in ev if e["event"] == "precondition"][:3] == [False, False, True]
    summ = json.loads(next((sess.dir / "cells").glob("*.json")).read_text())
    first = min((json.loads(p.read_text()) for p in (sess.dir / "cells").glob("*.json")),
                key=lambda s: s["instances"][0]["started_utc"])  # fmt: skip
    assert summ and len(first["instances"][0]["preconditions"]["attempts"]) == 3


def test_transient_failures_that_persist_abort_the_session_resumably(tmp_path, free_port):
    def pre(idle):
        p = json.loads(json.dumps(GOOD_PRE))
        p.update(ok=False, aborts=["MemAvailable 18.0 GiB < 20 GiB"],
                 transient_aborts=["MemAvailable 18.0 GiB < 20 GiB"])  # fmt: skip
        return p

    sleeps: list[float] = []
    sess, code, env = run_session(tmp_path, free_port, reps=1, pre_fn=pre, sleeps=sleeps)
    assert code == 3 and [x for x in sleeps if x] == [
        600.0,
        600.0,
        600.0,
    ]  # 1 try + 3 retries, 3 pauses
    assert len([e for e in events(sess) if e["event"] == "precondition"]) == 4
    sj = json.loads((sess.dir / "session.json").read_text())
    assert sj["state"] == "aborted" and sj["exit_code"] == 3 and "MemAvailable" in sj["last_error"]
    reqs, cells = read_records(sess)
    assert not reqs and not [c for c in cells if c["status"] == "did_not_fit"]
    # resumable: with the machine healthy again the same session completes
    env.preconditions_fn = lambda idle: json.loads(json.dumps(GOOD_PRE))
    sp = mini_spec(tmp_path, reps=1)
    sess2 = Session(env, load_sweep(sp), sp, "s1")
    assert sess2.run(resume=True) == 0


@pytest.mark.parametrize(
    "msg",
    ["the GPU lock is held by another job", "other GPU compute processes: python3(12)",
     "llama-server already running: pids [5]"],
)  # fmt: skip
def test_hard_precondition_failures_abort_at_once(tmp_path, free_port, msg):
    def pre(idle):
        p = json.loads(json.dumps(GOOD_PRE))
        p.update(ok=False, aborts=[msg], hard_aborts=[msg])
        return p

    sleeps: list[float] = []
    sess, code, _ = run_session(tmp_path, free_port, reps=1, pre_fn=pre, sleeps=sleeps)
    assert code == 3 and not [x for x in sleeps if x]
    assert len([e for e in events(sess) if e["event"] == "precondition"]) == 1


def test_busy_port_and_missing_binary_abort_the_session(tmp_path, free_port):
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", free_port))
        s.listen()
        sess, code, _ = run_session(tmp_path, free_port, reps=1)
    assert code == 1  # launch refused: not a did_not_fit
    _, cells = read_records(sess)
    assert not [c for c in cells if c["status"] == "did_not_fit"]
    assert "already in use" in json.loads((sess.dir / "session.json").read_text())["last_error"]


def test_real_wait_for_idle_is_used_between_retries(monkeypatch):
    from smallpc.sweep.core import HardAbort as H
    from smallpc.sweep.core import TransientAbort as T

    assert issubclass(H, Exception) and issubclass(T, Exception) and H.exit_code == T.exit_code == 3
    assert HardAbort is H and TransientAbort is T
