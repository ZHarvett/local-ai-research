"""smallpc.harness: configs rendered from templates and a (fake) /props. CI-safe: no server."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from conftest import REPO
from smallpc import harness
from smallpc.config import load_harness

POLICY = load_harness().context_policy


def props_payload(slot=16384, total=65536, slots=4, model="m.gguf"):
    props = {
        "total_slots": slots,
        "model_path": f"/models/{model}",
        "default_generation_settings": {"n_ctx": slot},
    }
    if total is not None:
        props["n_ctx"] = total
    return props, {"object": "list", "data": [{"id": model, "object": "model"}]}


def fake_client(slot=16384, total=65536, slots=4, model="m.gguf"):
    props, models = props_payload(slot, total, slots, model)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/props":
            return httpx.Response(200, json=props)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=models)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_props_reads_the_slot_context_the_total_and_the_model_id():
    p = harness.fetch_props("http://127.0.0.1:8080", fake_client(slot=16384, total=65536, slots=4))
    assert (p.n_ctx_slot, p.n_ctx_total, p.total_slots, p.model_id) == (16384, 65536, 4, "m.gguf")
    assert p.model_path == "/models/m.gguf"


def test_per_slot_context_is_used_where_it_differs_from_the_total():
    p = harness.fetch_props("http://h", fake_client(slot=16384, total=65536, slots=4))
    oc = harness.render_opencode(p, "127.0.0.1", 8080)
    limit = oc["provider"]["llamacpp"]["models"]["m.gguf"]["limit"]
    assert limit == {"context": 16384, "output": 4096}  # not 65536
    dsh = harness.render_dsh(p, "127.0.0.1", 8080)
    assert "contextWindow: 16384" in dsh and "65536" not in dsh and "maxTokens: 4096" in dsh


@pytest.mark.parametrize(
    ("slot", "expected"),
    [(65536, 16384), (32768, 8192), (131072, 16384), (16384, 4096), (2048, 512), (3, 1)],
)
def test_output_limit_formula(slot, expected):
    assert harness.output_limit(slot, POLICY) == expected


def test_context_is_never_hard_coded():
    for slot in (8192, 40000, 99999):
        p = harness.fetch_props("http://h", fake_client(slot=slot, total=slot * 2))
        oc = harness.render_opencode(p, "127.0.0.1", 8080)
        lim = oc["provider"]["llamacpp"]["models"]["m.gguf"]["limit"]
        assert lim["context"] == slot and lim["output"] == min(16384, slot // 4)
    # the templates carry placeholders only: no digit sequence that could be a context size
    for name in ("opencode.json.tmpl", "dsh.cordis.patch.yml.tmpl"):
        text = (REPO / "configs/harness" / name).read_text()
        assert "@@CONTEXT@@" in text and "@@OUTPUT@@" in text
        assert not re.findall(r"(?<![\w.@-])\d{4,}(?![\w.])", text), name


def test_missing_props_fields_are_errors_not_guesses():
    with pytest.raises(ValueError, match="n_ctx"):
        harness.parse_props({"default_generation_settings": {}}, {"data": [{"id": "x"}]})
    with pytest.raises(ValueError, match="no model"):
        harness.parse_props({"default_generation_settings": {"n_ctx": 1}}, {"data": []})


def test_opencode_config_values():
    p = harness.fetch_props("http://h", fake_client(model="weird/model.v2.gguf"))
    oc = harness.render_opencode(p, "127.0.0.1", 9931)
    prov = oc["provider"]["llamacpp"]
    assert prov["npm"] == "@ai-sdk/openai-compatible"
    assert prov["options"]["baseURL"] == "http://127.0.0.1:9931/v1"
    assert list(prov["models"]) == ["weird/model.v2.gguf"]
    assert oc["model"] == "llamacpp/weird/model.v2.gguf"
    assert oc["enabled_providers"] == ["llamacpp"]
    assert oc["autoupdate"] is False and oc["share"] == "disabled"
    assert set(oc) == {
        "$schema",
        "autoupdate",
        "share",
        "enabled_providers",
        "model",
        "provider",
        "permission",
    }  # everything else stays at the OpenCode default


def test_opencode_permission_patterns_are_what_the_plan_says():
    p = harness.fetch_props("http://h", fake_client())
    perm = harness.render_opencode(p, "127.0.0.1", 8080)["permission"]
    assert perm["*"] == "deny"  # catch-all, fail closed
    allowed = [k for k, v in perm["bash"].items() if v == "allow"]
    assert allowed == [
        "pytest",
        "pytest *",
        "python -m pytest",
        "python -m pytest *",
        "ls",
        "ls *",
        "cat *",
    ]
    assert perm["bash"]["*"] == "deny"
    # last match wins: every deny that narrows an allow comes after the allows
    keys = list(perm["bash"])
    for narrower in ("cat /*", "cat ~*", "ls /*", "ls ~*", "*..*"):
        assert perm["bash"][narrower] == "deny" and keys.index(narrower) > keys.index("cat *")
    for tool in ("external_directory", "webfetch", "websearch", "task", "skill", "lsp", "question"):
        assert perm[tool] == "deny"
    assert perm["doom_loop"] == "deny" and perm["edit"] == "allow"
    assert perm["read"]["*.env"] == "deny"  # the default would ask


def test_no_ask_and_no_blanket_allow_anywhere_in_the_real_config():
    p = harness.fetch_props("http://h", fake_client())
    text = json.dumps(harness.render_opencode(p, "127.0.0.1", 8080))
    assert '"ask"' not in text
    assert '"permission": "allow"' not in text
    for bad in ("dangerously", "--auto", "OPENCODE_PERMISSION"):
        assert bad not in text


def test_probe_only_ask_option_is_not_part_of_a_normal_render(tmp_path, monkeypatch):
    monkeypatch.setattr(
        harness, "fetch_props", lambda *a, **k: harness.parse_props(*props_payload())
    )
    out = tmp_path / "oc.json"
    assert harness.main(["render-opencode", "--out", str(out)]) == 0
    assert '"ask"' not in out.read_text()
    out2 = tmp_path / "oc-ask.json"
    harness.main(["render-opencode", "--out", str(out2), "--probe-ask-pattern", "curl *"])
    assert json.loads(out2.read_text())["permission"]["bash"]["curl *"] == "ask"


def test_dsh_patch_values():
    p = harness.fetch_props("http://h", fake_client())
    text = harness.render_dsh(p, "127.0.0.1", 8080)
    assert "api: openai-completions" in text
    assert 'baseURL: "http://127.0.0.1:8080/v1"' in text
    assert "apiKeyEnv: DSH_LOCAL_API_KEY" in text and "sk-" not in text  # key is never in the file
    assert 'model: "m.gguf"' in text and 'provider: "llamacpp"' in text
    for web in ("tool-web", "web-search-deepseek", "web-deepseek-api", "web-fetch-http"):
        assert re.search(rf"- id: {web}\n  disabled: true", text)
    assert "@@" not in text
    assert (
        "- id: approval" not in text
    )  # the shipped policy (ask, fails closed in headless) is kept


def test_harness_environment_switches():
    assert harness.OPENCODE_ENV == {
        "OPENCODE_DISABLE_AUTOUPDATE": "1",
        "OPENCODE_DISABLE_MODELS_FETCH": "1",
        "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
        "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
    }
    assert harness.DSH_ENV["DSH_TELEMETRY_MODE"] == "DISABLED"
    assert harness.DSH_ENV["DSH_PERMISSION_MODE"] == "workspace-write"
    assert harness.DSH_ENV["DSH_LOCAL_API_KEY"].startswith("sk-local")


def test_smoke_scripts_never_skip_permissions_or_use_sudo_and_always_sandbox():
    for name in ("smoke-opencode.sh", "smoke-dsh.sh", "_smoke_lib.sh"):
        text = (REPO / "scripts" / name).read_text()
        for bad in ("--auto", "dangerously", "OPENCODE_PERMISSION", "sudo", "danger-full-access"):
            assert bad not in text, (name, bad)
    for name in ("smoke-opencode.sh", "smoke-dsh.sh"):
        text = (REPO / "scripts" / name).read_text()
        assert "_sandbox.sh" in text and "--bridge" in text
        assert "run-detached.sh --gpu" in text  # documented entry point
