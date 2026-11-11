"""Final selection of one context from one session, with provenance (WP12 part 2g, step C.3).

Runs ``smallpc.select`` in final mode on ONE session (so every pair is a paired comparison) with a
sanity file, and writes ``<out>.json`` and ``<out>.md``: the selection output, plus the sessions
(spec, hashes, code commit), the sanity file (path and sha256) and the rule text applied.

    uv run python tools/stage2_final_selection.py --session data/raw/s2a-32K \\
        --sanity data/sanity/stage2-all.json --out data/analysis/stage2/32K-final
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from smallpc import analysis, labels, select
from smallpc.config import repo_root
from smallpc.stage2 import eligibility as el


def build(
    result: dict, prov: dict, sanity_path: str, sanity_sha: str, sanity: dict
) -> tuple[dict, str]:
    """``(json object, markdown)`` from a ``select_final`` result and its provenance."""
    cells = {n: c.get("result") for n, c in sanity.get("cells", {}).items()}
    obj = {
        "stage": "final selection (plan section 3.3, one session)",
        **result,
        "sanity_file": {"path": sanity_path, "sha256": sanity_sha, "results": cells},
        "provenance": prov,
    }
    md = select.render_markdown(result, "results")
    lines = [
        "",
        "## Provenance",
        "",
        "| session | spec | spec sha256 | session code commit |",
        "|---|---|---|---|",
    ]
    for s in prov["sessions"]:
        lines.append(
            f"| {s['session_id']} | {s['spec_path']} | {s['spec_sha256'][:16]} | "
            f"{(s['session_git_commit'] or '-')[:10]} |"
        )
    lines += [
        "",
        f"- sanity file: `{sanity_path}` (sha256 {sanity_sha[:16]})",
        f"- plan version: {prov['plan_version']}",
        f"- code commit of this tool: {prov['code'].get('commit')} "
        f"(dirty: {prov['code'].get('dirty')})",
        f"- llama.cpp commit: {prov['llama_cpp_commit']}",
        "",
        "### Rule text applied (plan v1.6, verbatim)",
        "",
    ]
    for t in prov["rule_text"]:
        lines += [("> " + ln if ln else ">") for ln in t.splitlines()] + [""]
    return obj, md.rstrip() + "\n" + "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--session", required=True, type=Path)
    ap.add_argument("--sanity", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    root = repo_root()
    checks, override = el.check_sessions([a.session], root, False)
    prov = el.provenance("2a", checks, root, override_used=override)
    res = analysis.analyse([a.session])
    raw = a.sanity.read_bytes()
    sanity = json.loads(raw)
    result = json.loads(json.dumps(select.select_final(res, sanity)))
    obj, md = build(result, prov, str(a.sanity), hashlib.sha256(raw).hexdigest(), sanity)
    obj["label"], obj["banner"] = "results", labels.banner("results")
    base = a.out.with_suffix("") if a.out.suffix in (".json", ".md") else a.out
    base.parent.mkdir(parents=True, exist_ok=True)
    base.with_name(base.name + ".json").write_text(json.dumps(obj, indent=1) + "\n")
    base.with_name(base.name + ".md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
