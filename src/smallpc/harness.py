"""Render the OpenCode and dsh configs from templates, reading the context from the server (WP7).

    python -m smallpc.harness render-opencode --out FILE [--props-url URL]
    python -m smallpc.harness render-dsh --out FILE [--props-url URL]
    python -m smallpc.harness env opencode|dsh [--dsh-home DIR]

The context window is never hard-coded: it comes from the running server's ``/props``. The
**per-slot** value (``default_generation_settings.n_ctx``) is used for ``limit.context`` /
``contextWindow``, because that is the context one request can actually use; the total ``n_ctx``
is recorded next to it. ``limit.output = min(cap, per_slot // divisor)`` (configs/harness.toml
``[context_policy]``). Templates live in ``configs/harness/``; ``@@NAME@@`` placeholders are
replaced after parsing, so values are typed and correctly escaped.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from .config import HarnessContextPolicy, load_harness, load_machine, repo_root

PROVIDER_ID = "llamacpp"

# Environment the harness runs with, on top of scripts/_sandbox.sh's isolation environment.
# Each entry is documented in docs/decisions.md and data/harness/network-observed.md.
OPENCODE_ENV = {
    "OPENCODE_DISABLE_AUTOUPDATE": "1",  # no update check or self-update
    "OPENCODE_DISABLE_MODELS_FETCH": "1",  # no catalogue fetch from models.opencode.ai
    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",  # no default plugin installs from npm
    "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",  # no language-server downloads
}
DSH_ENV = {
    "DSH_TELEMETRY_MODE": "DISABLED",  # default FEEDBACK_ONLY would export to a DeepSeek collector
    "DSH_PERMISSION_MODE": "workspace-write",  # sandbox: writes only inside the working directory
    "DSH_LOCAL_API_KEY": "sk-local-dummy",  # placeholder: the route requires some key
}


@dataclass(frozen=True)
class ServerProps:
    n_ctx_slot: int  # default_generation_settings.n_ctx: what one request can use
    n_ctx_total: int | None  # top-level n_ctx when /props reports it
    total_slots: int
    model_id: str  # as /v1/models reports it
    model_path: str | None

    def as_dict(self) -> dict:
        return asdict(self)


def parse_props(props: dict, models: dict) -> ServerProps:
    gen = props.get("default_generation_settings") or {}
    slot = gen.get("n_ctx")
    if not isinstance(slot, int) or slot <= 0:
        raise ValueError("/props has no default_generation_settings.n_ctx")
    data = models.get("data") or []
    if not data or not data[0].get("id"):
        raise ValueError("/v1/models lists no model")
    total = props.get("n_ctx")
    return ServerProps(
        n_ctx_slot=slot,
        n_ctx_total=total if isinstance(total, int) else None,
        total_slots=int(props.get("total_slots") or 1),
        model_id=str(data[0]["id"]),
        model_path=props.get("model_path"),
    )


def fetch_props(base_url: str, client: httpx.Client | None = None) -> ServerProps:
    base = base_url.rstrip("/")
    own = client is None
    client = client or httpx.Client(timeout=30)
    try:
        props = client.get(f"{base}/props").raise_for_status().json()
        models = client.get(f"{base}/v1/models").raise_for_status().json()
    finally:
        if own:
            client.close()
    return parse_props(props, models)


def output_limit(n_ctx_slot: int, policy: HarnessContextPolicy) -> int:
    return max(1, min(policy.output_cap, n_ctx_slot // policy.output_divisor))


def _fill(node, values: dict[str, object]):
    """Replace ``@@NAME@@`` in keys and strings; a string that is exactly a placeholder is typed."""
    if isinstance(node, dict):
        return {str(_fill(k, values)): _fill(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [_fill(v, values) for v in node]
    if isinstance(node, str):
        for name, val in values.items():
            tag = f"@@{name}@@"
            if node == tag:
                return val
            node = node.replace(tag, str(val))
    return node


def template_values(props: ServerProps, host: str, port: int, policy: HarnessContextPolicy) -> dict:
    return {
        "PROVIDER_ID": PROVIDER_ID,
        "MODEL_ID": props.model_id,
        "HOST": host,
        "PORT": port,
        "CONTEXT": props.n_ctx_slot,
        "OUTPUT": output_limit(props.n_ctx_slot, policy),
    }


def render_opencode(props: ServerProps, host: str, port: int, root: Path | None = None) -> dict:
    root = root or repo_root()
    policy = load_harness(root / "configs/harness.toml").context_policy
    tmpl = json.loads((root / "configs/harness/opencode.json.tmpl").read_text())
    return _fill(tmpl, template_values(props, host, port, policy))


def render_dsh(props: ServerProps, host: str, port: int, root: Path | None = None) -> str:
    root = root or repo_root()
    policy = load_harness(root / "configs/harness.toml").context_policy
    text = (root / "configs/harness/dsh.cordis.patch.yml.tmpl").read_text()
    for name, val in template_values(props, host, port, policy).items():
        # string placeholders sit inside double quotes in the template: escape, do not re-quote
        text = text.replace(
            f"@@{name}@@", json.dumps(val)[1:-1] if isinstance(val, str) else str(val)
        )
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("render-opencode", "render-dsh"):
        p = sub.add_parser(name)
        p.add_argument("--out", required=True)
        p.add_argument("--props-url", help="llama-server base URL (default: machine.toml)")
        p.add_argument("--host", help="host in the rendered base URL (default: machine.toml)")
        p.add_argument(
            "--port", type=int, help="port in the rendered base URL (default: machine.toml)"
        )
    sub.choices["render-opencode"].add_argument(
        "--probe-ask-pattern",
        help="PROBE ONLY: leave this bash pattern at 'ask' to test non-interactive behaviour",
    )
    e = sub.add_parser("env")
    e.add_argument("harness", choices=["opencode", "dsh"])
    e.add_argument("--dsh-home")
    a = ap.parse_args(argv)

    if a.cmd == "env":
        env = dict(OPENCODE_ENV if a.harness == "opencode" else DSH_ENV)
        if a.harness == "dsh" and a.dsh_home:
            env["DSH_HOME"] = a.dsh_home
        for k, v in env.items():
            print(f"{k}={v}")
        return 0

    machine = load_machine()
    host, port = a.host or machine.server.host, a.port or machine.server.port
    base = a.props_url or f"http://{host}:{port}"
    props = fetch_props(base)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.cmd == "render-opencode":
        cfg = render_opencode(props, host, port)
        if a.probe_ask_pattern:
            cfg["permission"]["bash"][a.probe_ask_pattern] = "ask"
        out.write_text(json.dumps(cfg, indent=2) + "\n")
    else:
        out.write_text(render_dsh(props, host, port))
    print(json.dumps({"props": props.as_dict(), "out": str(out)}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
