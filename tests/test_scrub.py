from __future__ import annotations

import json

import pytest

from smallpc import scrub
from smallpc.scrub import Identity

# Synthetic names only: the real account name and hostname never appear in the repository.
ID = Identity(username="testuser", hostname="testhost-01", home="/home/testuser")


def test_plain_text():
    text = "user testuser on testhost-01 opened /home/testuser/data/x.json and /home/testuser"
    out = scrub.scrub_text(text, ID)
    assert out == "user <user> on <host> opened ~/data/x.json and ~"


def test_hostname_with_domain_matches_short_name():
    ident = Identity("testuser", "testhost-01.example.net", "/home/testuser")
    assert scrub.scrub_text("ssh testhost-01 and testhost-01.example.net", ident) == (
        "ssh <host> and <host>"
    )


def test_word_boundaries():
    out = scrub.scrub_text("testusers testuser2 xtestuser testuser.", ID)
    assert out == "testusers testuser2 xtestuser <user>."


def test_home_differs_from_username_path():
    ident = Identity("testuser", "h1", "/mnt/homes/tu")
    assert scrub.scrub_text("/mnt/homes/tu/x /home/testuser/y", ident) == "~/x ~/y"


def test_json_escaped_text():
    payload = {"path": "/home/testuser/models/m.gguf", "who": "testuser", "box": "testhost-01"}
    for text in (json.dumps(payload), json.dumps(payload).replace("/", "\\/")):
        out = scrub.scrub_text(text, ID)
        assert "testuser" not in out and "testhost" not in out
        parsed = json.loads(out)
        assert parsed["path"] == "~/models/m.gguf"
        assert parsed["who"] == "<user>" and parsed["box"] == "<host>"


def test_json_escaped_special_characters_in_names():
    ident = Identity('te"st', "h-1", '/home/te"st')
    text = json.dumps({"p": '/home/te"st/x', "u": 'te"st'})
    out = json.loads(scrub.scrub_text(text, ident))
    assert out == {"p": "~/x", "u": "<user>"}


def test_scrub_json_structure():
    obj = {"testuser": ["/home/testuser/a", {"h": "testhost-01"}], "n": 3, "ok": True}
    assert scrub.scrub_json(obj, ID) == {"<user>": ["~/a", {"h": "<host>"}], "n": 3, "ok": True}


def test_short_names_are_not_replaced():
    ident = Identity("a", "b", "/")
    assert scrub.scrub_text("a b / c", ident) == "a b / c"


def test_find_in_text_reports_line_and_kind_only():
    text = "clean\nsee /home/testuser/x\nhost testhost-01 here\n"
    found = scrub.find_in_text(text, ID)
    assert (2, "home-path") in found and (3, "hostname") in found
    assert all(isinstance(k, str) and "test" not in k for _, k in found)


@pytest.fixture
def synthetic(monkeypatch):
    monkeypatch.setattr(Identity, "current", classmethod(lambda cls: ID))


def test_check_cli_finds_and_does_not_print_secrets(tmp_path, capsys, synthetic):
    (tmp_path / "sub").mkdir()
    bad = tmp_path / "sub" / "bad.txt"
    bad.write_text("fine\nowner testuser\npath /home/testuser/x\nhost testhost-01\n")
    (tmp_path / "good.txt").write_text("nothing here\n")
    (tmp_path / "bin.dat").write_bytes(b"\0\1testuser\2")  # binary: skipped
    rc = scrub.main(["--check", str(tmp_path)])
    cap = capsys.readouterr()
    assert rc == 1
    lines = cap.out.strip().splitlines()
    assert f"{bad}:2: username" in lines
    assert f"{bad}:3: home-path" in lines
    assert f"{bad}:4: hostname" in lines
    assert not any("good.txt" in line or "bin.dat" in line for line in lines)
    for secret in ("testuser", "testhost-01"):
        assert secret not in cap.out.replace(str(tmp_path), "")
        assert secret not in cap.err


def test_check_cli_passes_on_clean_and_json_escaped_is_found(tmp_path, capsys, synthetic):
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"p": "~/x", "u": "<user>"}))
    assert scrub.main(["--check", str(ok)]) == 0
    esc = tmp_path / "esc.json"
    esc.write_text(json.dumps({"p": "/home/testuser/x"}).replace("/", "\\/"))
    assert scrub.main(["--check", str(esc)]) == 1
    capsys.readouterr()


def test_check_skips_git_directory(tmp_path, synthetic):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("testuser\n")
    assert scrub.check_paths([tmp_path], ID) == []


def test_default_identity_is_read_at_run_time():
    ident = Identity.current()
    assert ident.home and isinstance(ident.hostname, str)
