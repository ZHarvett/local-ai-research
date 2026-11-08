"""configs/harness.toml schema, the committed lockfile and the whole-tree age check (WP7)."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import tomllib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from conftest import REPO
from smallpc import lockage
from smallpc.config import HarnessConfig, load_harness

TOML = REPO / "configs/harness.toml"
CFG = REPO / "configs/harness"
LOCK = json.loads((CFG / "package-lock.json").read_text())
AGES = json.loads((REPO / "data/harness/lockfile-ages.json").read_text())


def raw() -> dict:
    return tomllib.loads(TOML.read_text())


# ---------------------------------------------------------------- schema


def test_committed_harness_toml_validates():
    h = load_harness()
    assert h.package("opencode-ai").version == "1.19.5"
    assert h.package("@deepseek-ai/dsh").version == "0.2.1-rc.5"
    assert h.plugins.version == h.package("@deepseek-ai/dsh").version
    assert h.runtime.node_min == "22.0.0" and h.install.prefix == "third_party/node"
    assert [p.name for p in h.rebuild.packages] == ["opencode-ai"]


@pytest.mark.parametrize("bad", ["^1.19.5", "~1.19.5", "1.19", ">=1.0.0", "latest", "1.x"])
def test_version_ranges_are_rejected(bad):
    d = raw()
    d["packages"][0]["version"] = bad
    with pytest.raises(ValidationError, match="exact"):
        HarnessConfig.model_validate(d)


def test_plugin_version_must_equal_the_dsh_version():
    d = raw()
    d["plugins"]["version"] = "0.2.2-rc.1"
    with pytest.raises(ValidationError, match="exactly the dsh CLI version"):
        HarnessConfig.model_validate(d)


def test_binary_paths_must_be_absolute_and_unknown_fields_fail():
    d = raw()
    d["binaries"]["opencode"] = "third_party/node/bin/opencode"
    with pytest.raises(ValidationError, match="absolute"):
        HarnessConfig.model_validate(d)
    d = raw()
    d["surprise"] = 1
    with pytest.raises(ValidationError):
        HarnessConfig.model_validate(d)


# ---------------------------------------------------------------- lockfile


def test_package_json_pins_are_exact_and_match_harness_toml():
    pkg = json.loads((CFG / "package.json").read_text())
    h = load_harness()
    assert pkg["dependencies"] == {p.name: p.version for p in h.packages}
    for name, v in pkg["dependencies"].items():
        assert re.fullmatch(r"\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?", v), (name, v)
    assert pkg.get("overrides", {}) is not None


def test_lockfile_hash_and_root_match_harness_toml():
    h = load_harness()
    assert hashlib.sha256((CFG / "package-lock.json").read_bytes()).hexdigest() == (
        h.install.lockfile_sha256
    )
    assert LOCK["lockfileVersion"] == 3
    assert (
        LOCK["packages"][""]["dependencies"]
        == json.loads((CFG / "package.json").read_text())["dependencies"]
    )
    for p in h.packages:
        entry = LOCK["packages"]["node_modules/" + p.name]
        assert entry["version"] == p.version and entry["integrity"] == p.integrity


def test_every_dsh_plugin_resolves_to_the_dsh_version():
    h = load_harness()
    plugins = {
        k: v["version"]
        for k, v in LOCK["packages"].items()
        if re.fullmatch(r"node_modules/@deepseek-ai/dsh-[^/]+", k)
    }
    assert len(plugins) == h.plugins.count
    assert set(plugins.values()) == {h.plugins.version}


def test_install_scripts_with_no_approval_are_blocked_by_allow_scripts():
    pkg = json.loads((CFG / "package.json").read_text())
    approved = {k for k, v in pkg["allowScripts"].items() if v is True}
    assert approved == {"opencode-ai@1.19.5"}  # exactly the rebuild list, pinned
    h = load_harness()
    assert {f"{p.name}@{p.version}" for p in h.rebuild.packages} == approved
    scripted = {k for k, v in LOCK["packages"].items() if v.get("hasInstallScript")}
    covered = {"node_modules/" + p.name for p in (*h.rebuild.packages, *h.rebuild.denied)}
    assert scripted <= covered, "a package with an install script is not in harness.toml"


def test_age_evidence_covers_the_whole_lockfile_and_nothing_is_too_new():
    h = load_harness()
    cutoff = lockage.parse_ts(h.age_check.cutoff_utc)
    installed = lockage.parse_ts(h.install.installed_utc)
    assert (installed - cutoff).total_seconds() == h.age_check.rule_days * 86400
    published = {(r["name"], r["version"]): r["published"] for r in AGES["packages"]}
    assert set(lockage.lock_packages(LOCK)) == set(published)
    assert len(published) == h.age_check.packages_checked == AGES["packages_checked"]
    assert h.age_check.too_new == 0 == len(AGES["too_new"])
    assert max(lockage.parse_ts(t) for t in published.values()) <= cutoff
    for o in h.age_check.overrides:  # an override must name an exact pin
        assert re.fullmatch(r".+@\d+\.\d+\.\d+.*", o)


def test_install_script_is_safe():
    text = (REPO / "scripts/install-harnesses.sh").read_text()
    assert '"$npm_bin" ci --ignore-scripts' in text
    assert '--ignore-scripts "--before=$before"' in text
    assert "sudo" not in text and "install -g" not in text and "--global" not in text
    assert "_sandbox.sh" in text  # no unsandboxed npm


# ---------------------------------------------------------------- lockage


def _lock(pkgs: dict[str, str]) -> dict:
    return {
        "packages": {
            "": {"name": "root"},
            **{f"node_modules/{n}": {"version": v} for n, v in pkgs.items()},
            "node_modules/linked": {"link": True},
        }
    }


def test_lock_packages_unique_sorted_and_skips_root_and_links():
    lock = _lock({"b": "1.0.0", "a": "2.0.0"})
    lock["packages"]["node_modules/x/node_modules/@s/c"] = {"version": "3.0.0"}
    assert lockage.lock_packages(lock) == [("@s/c", "3.0.0"), ("a", "2.0.0"), ("b", "1.0.0")]


def test_check_lists_packages_published_after_the_cutoff():
    times = {
        "old": {"1.0.0": "2026-08-01T00:00:00.000Z"},
        "young": {"2.0.0": "2026-11-05T00:00:00.000Z"},
        "edge": {"1.0.0": "2026-11-01T18:25:11.000Z"},  # exactly the cutoff: allowed
    }
    cutoff = datetime(2026, 11, 1, 18, 25, 11, tzinfo=UTC)
    res = lockage.check(
        [("edge", "1.0.0"), ("old", "1.0.0"), ("young", "2.0.0")], cutoff, lambda n: times[n]
    )
    assert [p["name"] for p in res["too_new"]] == ["young"]
    assert res["packages_checked"] == 3 and not res["missing_publish_time"]


def test_check_reports_versions_without_a_publish_time():
    res = lockage.check(
        [("a", "9.9.9")],
        datetime(2026, 1, 1, tzinfo=UTC),
        lambda n: {"1.0.0": "2026-01-01T00:00:00Z"},
    )
    assert res["missing_publish_time"] == ["a@9.9.9"] and res["packages_checked"] == 0


def test_copy_of_toml_roundtrip_is_not_mutated_by_validation():
    d = raw()
    before = copy.deepcopy(d)
    HarnessConfig.model_validate(d)
    assert d == before


def test_committed_isolation_check_is_identical_before_and_after():
    text = (REPO / "data/harness/isolation-check.txt").read_text()
    before = text.split("===== BEFORE")[1].split("===== AFTER")[0].split("\n", 1)[1].strip()
    after = text.split("===== AFTER")[1].split("===== RESULT")[0].split("\n", 1)[1].strip()
    assert before == after and before.count("## ") == 6
    assert "RESULT: IDENTICAL" in text
    assert "/home/" not in text  # home paths are shown as ~


def test_request_pattern_is_labelled_and_complete():
    d = json.loads((REPO / "data/harness/request-pattern.json").read_text())
    assert d["label"] == "smoke-task data, not representative of real agent turns"
    assert {r["harness"] for r in d["runs"]} == {"opencode", "dsh"}
    for run in d["runs"]:
        assert run["label"] == d["label"]
        for r in run["requests"]:
            assert {"prompt_n", "cache_n", "predicted_n", "time_ms", "kind"} <= set(r)
            assert r["kind"] in ("main", "auxiliary") and r["cache_n"] is not None
        assert run["per_turn"]["requests_per_turn"] == len(run["requests"])
