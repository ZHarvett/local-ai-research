"""A refused or failed start never modifies an existing session, and ``--rerun-flagged`` works on a
session that was started with ``--only`` (WP11 part 2: the real Stage 1 sessions were all started
with ``--only context=...``; the first ``--rerun-flagged`` was refused and overwrote session.json).

Uses the mock server and the fixture helpers of the other sweep tests; no GPU."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from smallpc.config import load_sweep
from smallpc.sweep import records as rec
from smallpc.sweep.core import EXIT_PROVENANCE, ProvenanceError
from smallpc.sweep.session import Session
from sweep_fakes import MINI_SPEC, make_env, mini_spec, read_records, write_spec
from test_sweep_session import measured, run_session


def two_context_spec(tmp_path: Path, reps: int = 2) -> Path:
    """The mini spec with a second context (64K) that ``--only context=32K`` leaves out."""
    text = MINI_SPEC.format(reps=reps, restarts=2, canary="")
    text = text.replace(
        '"32K" = { context = 32768 }', '"32K" = { context = 32768 }\n"64K" = { context = 65536 }'
    )
    text = text.replace('context = ["32K"]', 'context = ["32K", "64K"]')
    return write_spec(tmp_path, text, "spec2.toml")


def tree(d: Path) -> dict[str, str]:
    """Relative path -> SHA-256 of every file below ``d`` (a byte-for-byte fingerprint)."""
    return {
        str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(d.rglob("*"))
        if p.is_file()
    }


def filtered_session(tmp_path, port, behavior=None):
    env = make_env(tmp_path, port, behavior)
    sp = two_context_spec(tmp_path)
    sess = Session(env, load_sweep(sp), sp, "s1", filters={"context": "32K"})
    assert sess.run() == 0
    return sess, env, sp


# ------------------------------------------------------------------ (i) re-run of a filtered session


def test_rerun_of_a_session_started_with_only_reruns_just_the_flagged_unit(tmp_path, free_port):
    # the second Request B of every server is a cache miss: repetition 0 of every cell is flagged
    sess, _, sp = filtered_session(tmp_path, free_port, {"cache_miss_B": {"on": [1]}})
    stored = json.loads((sess.dir / "session.json").read_text())
    assert stored["filters"] == {"context": "32K"}
    flagged = rec.Index(sess.store.load()).flagged_repetitions()
    assert {r for (_, r) in flagged} == {0} and len(flagged) == 3
    before = sess.store.path.read_bytes()

    env2 = make_env(tmp_path, free_port)  # no misbehaviour any more
    # no --only on the command line: the stored filter is used (the Stage 1 runbook command)
    s2 = Session(env2, load_sweep(sp), sp, "s1", mode="rerun")
    assert s2.rerun_flagged() == 0
    assert s2.filters == {"context": "32K"}
    assert s2.store.path.read_bytes().startswith(before)  # old lines are never edited
    reqs, _ = read_records(s2)
    a2 = [r for r in measured(reqs) if r["attempt"] == 2]
    assert len(a2) == 3 * 7 and {r["repetition"] for r in a2} == {0}
    assert {r["cell"] for r in a2} == {"Pa-32K", "Pb-32K", "stock-32K"}
    assert not [r for r in a2 if r["flags"]]
    # the unflagged unit (repetition 1) has no attempt-2 records, and there is no attempt 3
    assert all(r["attempt"] == 1 for r in measured(reqs) if r["repetition"] == 1)
    assert all(r["attempt"] in (1, 2) for r in reqs)
    assert not rec.find_duplicates(reqs)
    # the session file keeps everything it had, and records the re-run as a run of its own
    after = json.loads((sess.dir / "session.json").read_text())
    for key in (
        "spec_sha256",
        "manifest_sha256",
        "sampling_sha256",
        "git",
        "cell_order",
        "filters",
    ):
        assert after[key] == stored[key]
    assert [r["mode"] for r in after["runs"]] == ["run", "rerun"] and after["state"] == "complete"

    # a second pass, now with the same --only on the command line, plans nothing more
    size = s2.store.path.stat().st_size
    s3 = Session(env2, load_sweep(sp), sp, "s1", filters={"context": "32K"}, mode="rerun")
    assert s3.rerun_flagged() == 0 and s3.store.path.stat().st_size == size


# ------------------------------------------------------------------ (ii) conflicting --only


@pytest.mark.parametrize("started_with", [{"context": "32K"}, {}])
def test_rerun_with_a_conflicting_only_is_refused_and_touches_nothing(
    tmp_path, free_port, capsys, started_with
):
    if started_with:
        sess, env, sp = filtered_session(tmp_path, free_port, {"cache_miss_B": {"on": [1]}})
        given = {"context": "64K"}
    else:
        sess, _, env = run_session(tmp_path, free_port, {"cache_miss_B": {"on": [1]}}, reps=2)
        sp = mini_spec(tmp_path, reps=2)
        given = {"context": "32K"}
    snap = tree(sess.dir)
    capsys.readouterr()
    s2 = Session(
        make_env(tmp_path, free_port), load_sweep(sp), sp, "s1", filters=given, mode="rerun"
    )
    assert s2.rerun_flagged() == EXIT_PROVENANCE
    assert tree(sess.dir) == snap  # every file of the session is byte-identical, none added
    err = capsys.readouterr().err
    assert "--only filter" in err and "refused" in err
    # the stored state survives the refusal
    assert json.loads((sess.dir / "session.json").read_text())["state"] == "complete"


# ------------------------------------------------------------------ (iii) refused resume


def _spec_edited(tmp_path, env, sp):
    sp.write_text(sp.read_text() + "\n# edited\n")
    return {}


def _manifest_changed(tmp_path, env, sp):
    env.manifest_path.write_text('{"changed": true}')
    return {}


def _filter_changed(tmp_path, env, sp):
    return {"filters": {"context": "32K"}}


def _no_resume_flag(tmp_path, env, sp):
    return {"resume": False}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_spec_edited, "spec_sha256"),
        (_manifest_changed, "manifest_sha256"),
        (_filter_changed, "filter"),
        (_no_resume_flag, "already exists"),
    ],
)
def test_a_refused_resume_touches_nothing(tmp_path, free_port, capsys, change, message):
    sess, _, env = run_session(tmp_path, free_port, reps=1)
    sp = mini_spec(tmp_path, reps=1)
    snap = tree(sess.dir)
    opts = change(tmp_path, env, sp)
    capsys.readouterr()
    s2 = Session(env, load_sweep(sp), sp, "s1", filters=opts.get("filters"))
    assert s2.run(resume=opts.get("resume", True)) == EXIT_PROVENANCE
    assert tree(sess.dir) == snap  # session.json, progress.json, events.jsonl, records: unchanged
    err = capsys.readouterr().err
    assert message in err and "refused" in err


def test_a_refused_new_session_leaves_no_files(tmp_path, free_port, capsys):
    env = make_env(tmp_path, free_port)
    env.git = {**env.git, "dirty": True, "dirty_paths": ["src/x.py"]}
    sp = mini_spec(tmp_path, reps=1)
    s = Session(env, load_sweep(sp), sp, "s9")
    assert s.run() == EXIT_PROVENANCE
    assert not (env.out_root / "s9").exists()  # not even a stub session.json
    assert "uncommitted changes" in capsys.readouterr().err


# ------------------------------------------------------------------ (iv) merge, (v) unreadable files


def _opened(tmp_path, free_port):
    sess, _, env = run_session(tmp_path, free_port, reps=1)
    sp = mini_spec(tmp_path, reps=1)
    s2 = Session(env, load_sweep(sp), sp, "s1")
    s2.open(resume=True)
    return s2


def test_update_session_and_progress_merge_and_keep_unrelated_keys(tmp_path, free_port):
    s2 = _opened(tmp_path, free_port)
    sj, pj = s2.dir / "session.json", s2.dir / "progress.json"
    d = json.loads(sj.read_text())
    d["written_by_someone_else"] = {"keep": 1}
    sj.write_text(json.dumps(d))
    p = json.loads(pj.read_text())
    p["extra_progress_key"] = 7
    pj.write_text(json.dumps(p))

    s2.update_session(state="interrupted", note="x")
    s2.progress(phase="probe")
    after = json.loads(sj.read_text())
    assert after["state"] == "interrupted" and after["note"] == "x"
    assert after["written_by_someone_else"] == {"keep": 1}
    assert {k: after[k] for k in ("spec_sha256", "cell_order", "git")} == {
        k: d[k] for k in ("spec_sha256", "cell_order", "git")
    }
    prog = json.loads(pj.read_text())
    assert prog["phase"] == "probe" and prog["extra_progress_key"] == 7
    assert prog["session_id"] == "s1"


def test_a_session_that_was_not_opened_cannot_write(tmp_path):
    env = make_env(tmp_path, 1)
    sp = mini_spec(tmp_path, reps=1)
    s = Session(env, load_sweep(sp), sp, "never")
    with pytest.raises(ProvenanceError, match="not opened"):
        s.update_session(state="aborted")
    s.progress(phase="x")  # remembered in memory only
    assert not (env.out_root / "never").exists()


@pytest.mark.parametrize("garbage", ["{not json", "[1, 2]", ""])
def test_an_unreadable_session_json_is_never_overwritten(tmp_path, free_port, capsys, garbage):
    sess, _, env = run_session(tmp_path, free_port, reps=1)
    sp = mini_spec(tmp_path, reps=1)
    sj = sess.dir / "session.json"
    sj.write_text(garbage)
    snap = tree(sess.dir)
    capsys.readouterr()
    assert Session(env, load_sweep(sp), sp, "s1").run(resume=True) == EXIT_PROVENANCE
    assert Session(env, load_sweep(sp), sp, "s1", mode="rerun").rerun_flagged() == EXIT_PROVENANCE
    assert tree(sess.dir) == snap and sj.read_text() == garbage
    assert "session.json" in capsys.readouterr().err


def test_a_file_that_becomes_unreadable_mid_session_is_not_replaced(tmp_path, free_port):
    s2 = _opened(tmp_path, free_port)
    for name, call in (
        ("session.json", lambda: s2.update_session(state="complete")),
        ("progress.json", lambda: s2.progress(phase="probe")),
    ):
        f = s2.dir / name
        f.write_text("{broken")
        with pytest.raises(ProvenanceError, match="unreadable"):
            call()
        assert f.read_text() == "{broken"
