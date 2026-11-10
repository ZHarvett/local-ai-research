"""Canary bracketing and drift, the re-run mode, the record schema and the config hash."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from smallpc.config import load_sweep
from smallpc.sweep import provenance
from smallpc.sweep import records as rec
from smallpc.sweep.session import Session
from sweep_fakes import events, make_env, mini_spec, read_records
from test_sweep_session import measured, run_session

# ------------------------------------------------------------------ canary


def canary_reqs(reqs, role):
    return [r for r in reqs if r["role"] == role]


def test_canary_brackets_the_session_with_fresh_repetition_indices(tmp_path, free_port):
    sess, code, env = run_session(tmp_path, free_port, canary=True, reps=1)
    assert code == 0
    reqs, cells = read_records(sess)
    start, end = canary_reqs(reqs, "canary_start"), canary_reqs(reqs, "canary_end")
    # repetitions 100 upward: start 100, 101; end 102, 103 (two canary repetitions in the test spec)
    assert {r["repetition"] for r in start} == {100, 101}
    assert {r["repetition"] for r in end} == {102, 103}
    # each repetition: the short point and the 1K pair; no nonce is ever reused
    for group in (start, end):
        assert {r["kind"] for r in group} == {"short", "A", "B"}
        assert {r["depth"] for r in group if r["kind"] in ("A", "B")} == {1024}
    ids = [r["workload_id"] for r in start + end if r["kind"] != "B"]
    assert len(ids) == len(set(ids))
    nonces = [r["nonce"] for r in start + end if r["kind"] != "B"]
    assert len(nonces) == len(set(nonces))
    # start canary first, end canary last, each on its own server with its own warm-up
    names = [c["cell"] for c in cells if c["final"]]
    assert names[0] == "canary-start" and names[-1] == "canary-end"
    assert {r["server_run_id"] for r in start}.isdisjoint({r["server_run_id"] for r in end})
    assert not rec.find_duplicates(reqs)
    # canary requests are never mixed into the measured results
    assert not [r for r in measured(reqs) if r["repetition"] >= 100]


def test_no_drift_when_the_machine_is_steady(tmp_path, free_port):
    sess, _, _ = run_session(tmp_path, free_port, canary=True, reps=1)
    sj = json.loads((sess.dir / "session.json").read_text())
    d = sj["drift"]["main"]
    assert d["flag"] is None and d["complete"]
    assert d["metrics"]["pp_fresh_16k"]["relative_difference"] == pytest.approx(0.0, abs=1e-9)
    assert set(d["decided_on"]) == {"pp_fresh_16k", "tg_16k"}


def test_drift_is_flagged_from_the_start_and_end_canaries(tmp_path, free_port):
    env = make_env(tmp_path, free_port)
    orig = env.server_factory
    n = {"servers": 0}

    def factory():
        s = orig()
        n["servers"] += 1
        if n["servers"] == 5:  # start canary, three cells, then the end canary: it runs slower
            s.env["MOCK_BEHAVIOR"] = json.dumps(
                {"vram_file": str(tmp_path / "vram.txt"), "speed_factor": 0.7}
            )
        return s

    env.server_factory = factory
    sess, code, _ = run_session(tmp_path, free_port, canary=True, reps=1, env=env)
    assert code == 0 and n["servers"] == 5
    d = json.loads((sess.dir / "session.json").read_text())["drift"]["main"]
    assert d["flag"] == "drift"
    pp = d["metrics"]["pp_fresh_16k"]
    assert pp["flag"] == "drift" and 0.25 < pp["relative_difference"] < 0.35
    assert pp["end_mean"] < pp["start_mean"] and len(pp["start_values"]) == 2
    assert any(e["event"] == "drift" and e["flag"] == "drift" for e in events(sess))


# ------------------------------------------------------------------ re-run mode


def test_rerun_appends_attempt_2_for_flagged_repetitions_only(tmp_path, free_port):
    # the second Request B of every server is a cache miss: repetition 0 of every cell is flagged
    sess, _, _ = run_session(
        tmp_path, free_port, {"cache_miss_B": {"on": [1]}}, reps=2, canary=True
    )
    before = sess.store.path.read_bytes()
    reqs, _ = read_records(sess)
    idx = rec.Index(sess.store.load())
    flagged = idx.flagged_repetitions()
    assert {r for (_, r) in flagged} == {0} and len(flagged) == 3
    assert all(v == ["cache_miss"] for v in flagged.values())

    env2 = make_env(tmp_path, free_port)  # same machine and configs, no misbehaviour any more
    sp = mini_spec(tmp_path, reps=2, canary=True)
    s2 = Session(env2, load_sweep(sp), sp, "s1", mode="rerun")
    assert s2.rerun_flagged() == 0
    after = s2.store.path.read_bytes()
    assert after.startswith(before)  # old lines are never edited
    reqs2, cells2 = read_records(s2)
    a2 = [r for r in reqs2 if r["attempt"] == 2]
    assert a2 and {r["role"] for r in a2} == {"measured", "warmup"}  # canaries have own indices
    m2 = [r for r in a2 if r["role"] == "measured"]
    assert len(m2) == 3 * 7 and {r["repetition"] for r in m2} == {0}
    assert not [r for r in m2 if r["flags"]]  # attempt 2 is clean
    # attempt 1 still has its flagged lines
    assert (
        len([r for r in measured(reqs2) if r["attempt"] == 1 and "cache_miss" in r["flags"]]) == 3
    )
    # the rerun canaries use their own repetition indices
    canary_reps = {
        r["repetition"] for r in reqs2 if r["role"].startswith("canary") and r["repetition"] >= 110
    }
    assert canary_reps == {110, 111, 112, 113}
    assert not rec.find_duplicates(reqs2)
    # never an attempt 3: a second pass finds nothing left to do
    size = s2.store.path.stat().st_size
    s3 = Session(env2, load_sweep(sp), sp, "s1", mode="rerun")
    assert s3.rerun_flagged() == 0 and s3.store.path.stat().st_size == size
    assert all(r["attempt"] in (1, 2) for r in reqs2)


def test_a_completed_rerun_leaves_finished_utc_alone(tmp_path, free_port):
    """WP12: a re-run records its own end as ``rerun_finished_utc`` (merged into session.json) and
    never overwrites the main run's ``finished_utc``; the status and report readers do not care."""
    from smallpc import analysis
    from smallpc.sweep import status

    sess, _, _ = run_session(
        tmp_path, free_port, {"cache_miss_B": {"on": [1]}}, reps=2, canary=True
    )
    sj = sess.dir / "session.json"
    before = json.loads(sj.read_text())
    assert before["state"] == "complete" and before["finished_utc"]
    assert "rerun_finished_utc" not in before
    info_before = analysis.session_info(analysis.load_session(sess.dir))
    status_before = status.report(sess.dir)

    env2 = make_env(tmp_path, free_port)
    sp = mini_spec(tmp_path, reps=2, canary=True)
    s2 = Session(env2, load_sweep(sp), sp, "s1", mode="rerun")
    assert s2.rerun_flagged() == 0
    after = json.loads(sj.read_text())
    assert after["finished_utc"] == before["finished_utc"]  # not overwritten
    assert after["rerun_finished_utc"] and after["state"] == "complete"
    assert after["created_utc"] == before["created_utc"]  # other keys are merged, not replaced
    assert set(before) <= set(after)
    info_after = analysis.session_info(analysis.load_session(sess.dir))
    # the analysis reads no end time of the session: same keys, no finished_utc anywhere in it
    assert set(info_after) == set(info_before)
    assert info_after["created_utc"] == info_before["created_utc"]
    assert "finished_utc" not in json.dumps(info_after) + json.dumps(info_before)
    status_after = status.report(sess.dir)
    # the status tool reads state, cell order and records, never the end time of the main run
    assert status_after["state"] == status_before["state"] == "complete"
    assert status_after["cells_done"] == status_before["cells_done"]
    assert status_after["records"]["requests"] > status_before["records"]["requests"]


def test_short_gen_is_not_rerun(tmp_path, free_port):
    sess, _, _ = run_session(tmp_path, free_port, {"short_gen_B": {"on": [0], "value": 50}}, reps=1)
    idx = rec.Index(sess.store.load())
    assert any("short_gen" in r["flags"] for r in sess.store.load().requests)
    assert idx.flagged_repetitions() == {}
    env2 = make_env(tmp_path, free_port)
    sp = mini_spec(tmp_path, reps=1)
    s2 = Session(env2, load_sweep(sp), sp, "s1", mode="rerun")
    size = s2.store.path.stat().st_size
    assert s2.rerun_flagged() == 0 and s2.store.path.stat().st_size == size


def test_did_not_fit_cells_are_not_rerun(tmp_path, free_port):
    sess, _, _ = run_session(tmp_path, free_port, {"oom_at_start": True}, reps=1)
    env2 = make_env(tmp_path, free_port)
    sp = mini_spec(tmp_path, reps=1)
    s2 = Session(env2, load_sweep(sp), sp, "s1", mode="rerun")
    size = s2.store.path.stat().st_size
    assert s2.rerun_flagged() == 0 and s2.store.path.stat().st_size == size


# ------------------------------------------------------------------ the record schema


def good_request(**kw):
    base = dict(
        session_id="s", cell="c", config_hash="0123456789abcdef", server_run_id="r",
        server_instance=0, code_commit="a" * 10, utc="2026-11-09T00:00:00Z", role="measured",
        warmup=False, kind="A", workload_id="A-v0-1000-r0", workload_kind="pair", depth=1000,
        variant=0, repetition=0, nonce="n", seed=1, position=1, n_predict=0, stream=False,
        sampling={"seed": 1}, expected={"d": 1000}, timings={"cache_n": 0, "prompt_n": 1000},
        client={"t_start_epoch": 1.0, "t_end_epoch": 2.0, "wall_s": 1.0},
        batch_id="b", batch_index=0, batch_size=1,
    )  # fmt: skip
    return {**base, **kw}


def test_a_valid_request_record_validates_and_round_trips():
    r = rec.RequestRecord.model_validate(good_request(schema=1))
    d = r.model_dump(by_alias=True)
    assert d["schema"] == 1 and d["id_slot"] is None and d["draft_n"] is None
    assert rec.RequestRecord.model_validate(d)  # round trip
    # every field the plan names is present in the schema
    fields = set(rec.RequestRecord.model_fields)
    for need in ("session_id", "cell", "config_hash", "workload_id", "kind", "depth", "variant",
                 "repetition", "nonce", "seed", "attempt", "timings", "draft_n",
                 "draft_n_accepted", "stop_type", "client", "snapshot_id", "telemetry", "flags",
                 "id_slot", "code_commit", "warmup"):  # fmt: skip
        assert need in fields, need


@pytest.mark.parametrize(
    "change",
    [
        {"config_hash": "xyz"},
        {"attempt": 3},
        {"kind": "C"},
        {"role": "other"},
        {"unexpected": 1},
        {"client": {"t_start_epoch": 1.0}},
        {"batch_id": None},
    ],
)
def test_invalid_request_records_are_rejected(change):
    with pytest.raises(ValidationError):
        rec.RequestRecord.model_validate(good_request(**change))


def test_missing_required_fields_are_rejected():
    r = good_request()
    for k in ("session_id", "config_hash", "workload_id", "timings", "client", "batch_id"):
        bad = {x: v for x, v in r.items() if x != k}
        with pytest.raises(ValidationError):
            rec.RequestRecord.model_validate(bad)


def test_cell_records_validate():
    c = dict(session_id="s", cell="c", config_hash=None, status="did_not_fit", final=True,
             reason="context", flags=["did_not_fit"], code_commit="a" * 10, utc="x",
             batch_id="b")  # fmt: skip
    assert rec.CellRecord.model_validate(c).final is True
    with pytest.raises(ValidationError):
        rec.CellRecord.model_validate({**c, "status": "weird"})


def test_every_line_of_a_real_session_validates(tmp_path, free_port):
    sess, _, _ = run_session(tmp_path, free_port, canary=True, reps=1)
    n = 0
    for line in sess.store.path.read_text().splitlines():
        obj = json.loads(line)
        (rec.RequestRecord if obj["record_type"] == "request" else rec.CellRecord).model_validate(
            obj
        )
        n += 1
    assert n > 40


def test_duplicate_detection_and_the_resume_index():
    a = good_request(attempt=1)
    b = good_request(attempt=1, kind="B", workload_id="B-v0-1000-r0")
    assert rec.find_duplicates([a, b]) == []
    assert len(rec.find_duplicates([a, dict(a)])) == 1
    # a re-run (attempt 2) and a warm-up on another server are not duplicates
    assert rec.find_duplicates([a, good_request(attempt=2)]) == []
    w1 = good_request(attempt=1, role="warmup", warmup=True, server_run_id="r1")
    w2 = good_request(attempt=1, role="warmup", warmup=True, server_run_id="r2")
    assert rec.find_duplicates([w1, w2]) == [] and len(rec.find_duplicates([w1, dict(w1)])) == 1


# ------------------------------------------------------------------ the config hash


ARGV = ["/x/llama-server", "-m", "/x/m.gguf", "--port", "8080", "-c", "32768", "--fit", "on"]


def test_config_hash_is_stable_and_covers_argv_model_and_commit():
    h = provenance.config_hash(ARGV, "b" * 64, "c" * 40)
    assert h == provenance.config_hash(list(ARGV), "b" * 64, "c" * 40) and len(h) == 16
    assert provenance.config_hash([*ARGV, "-np", "1"], "b" * 64, "c" * 40) != h
    assert provenance.config_hash(ARGV[:-1] + ["off"], "b" * 64, "c" * 40) != h
    assert provenance.config_hash(ARGV, "d" * 64, "c" * 40) != h
    assert provenance.config_hash(ARGV, "b" * 64, "e" * 40) != h
    assert provenance.config_hash(ARGV[:3] + ["--port", "9"] + ARGV[5:], "b" * 64, "c" * 40) != h
    # argv order matters: the order is part of the rendered command line
    assert provenance.config_hash(sorted(ARGV), "b" * 64, "c" * 40) != h


def test_config_hash_value_is_pinned():
    # a change of the hash algorithm would orphan every stored session: pin one value
    assert provenance.config_hash(ARGV, "b" * 64, "c" * 40) == PINNED


PINNED = "e49bbe775ed9ec53"


def test_git_state_reports_the_commit_and_dirty_paths_in_the_guarded_directories(tmp_path):
    import subprocess

    def git(*a):
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *a],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    git("init", "-q")
    for d in ("src", "configs", "scripts", "data"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "f.txt").write_text("1\n")
    git("add", "-A")
    git("commit", "-qm", "x")
    clean = provenance.git_state(tmp_path)
    assert clean["dirty"] is False and clean["dirty_paths"] == []
    assert (
        clean["commit"] == git("rev-parse", "HEAD").strip()
        and clean["short"] == clean["commit"][:10]
    )
    (tmp_path / "src/f.txt").write_text("2\n")  # tracked, modified
    (tmp_path / "configs/new.toml").write_text("x\n")  # untracked
    (tmp_path / "data/f.txt").write_text("2\n")  # not a guarded directory
    st = provenance.git_state(tmp_path)
    assert st["dirty"] is True
    assert sorted(st["dirty_paths"]) == ["configs/new.toml", "src/f.txt"]


def test_model_sha_is_cached_and_a_missing_file_is_marked_unverified(tmp_path):
    f = tmp_path / "m.gguf"
    f.write_bytes(b"abc")
    cache = tmp_path / "cache.json"
    import hashlib

    want = hashlib.sha256(b"abc").hexdigest()
    r = provenance.model_sha256(f, want, cache)
    assert r["sha256"] == want and r["verified"] is True
    assert json.loads(cache.read_text())  # cached by path, size and mtime
    assert provenance.model_sha256(f, "0" * 64, cache)["verified"] is False  # declared differs
    miss = provenance.model_sha256(tmp_path / "none.gguf", "d" * 64, cache)
    assert miss["verified"] is False and miss["sha256"] == "d" * 64
