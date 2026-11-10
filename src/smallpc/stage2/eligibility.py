"""Which sessions may drive a Stage 2 decision, and the provenance every decision records.

``decide`` refuses a session whose ``session.json`` records ``allow_dirty`` true, whose spec
header says functional-test, whose id starts with the functional-test prefix of the spec generator
(``specgen.FT_PREFIX``), or that is not complete. The command line has no way around this; unit
tests pass ``allow_ineligible=True`` (or set ``SMALLPC_STAGE2_ALLOW_INELIGIBLE``, which is read
only when pytest is running), and the output then says so.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from ..config import repo_root
from . import rules
from .specgen import FT_LINE, FT_PREFIX

ENV_OVERRIDE = "SMALLPC_STAGE2_ALLOW_INELIGIBLE"


class Refused(Exception):
    """A session may not drive a decision; the message names the session and the reason."""


def _override(allow_ineligible: bool) -> bool:
    return allow_ineligible or (
        os.environ.get(ENV_OVERRIDE) == "1" and "PYTEST_CURRENT_TEST" in os.environ
    )


def spec_header(path: Path) -> str:
    """The leading comment lines of a spec file (everything before the first non-comment line)."""
    out = []
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            break
        out.append(line)
    return "\n".join(out)


def session_check(session_dir: Path, root: Path) -> dict:
    """Eligibility facts of one session: ``reasons`` (refusals), ``warnings``, the spec hash."""
    d = Path(session_dir)
    meta = json.loads((d / "session.json").read_text())
    sid = meta.get("session_id", d.name)
    reasons: list[str] = []
    warnings: list[str] = []
    if sid.startswith(FT_PREFIX) or d.name.startswith(FT_PREFIX):
        reasons.append(f"session id {sid!r} has the functional-test prefix {FT_PREFIX!r}")
    if meta.get("allow_dirty"):
        reasons.append("session.json records allow_dirty = true (started from an uncommitted tree)")
    if meta.get("state") != "complete":
        reasons.append(f"session state is {meta.get('state')!r}, not 'complete'")
    spec_rel = (meta.get("spec") or {}).get("path")
    spec_file = Path(root) / spec_rel if spec_rel else None
    checked = False
    matches = None
    if spec_file is not None and spec_file.exists():
        checked = True
        head = spec_header(spec_file).lower()
        if "functional-test" in head or FT_LINE.split(":")[0].lower() in head:
            reasons.append(f"the spec header of {spec_rel} says functional-test")
        actual = hashlib.sha256(spec_file.read_bytes()).hexdigest()
        matches = actual == meta.get("spec_sha256")
        if not matches:
            warnings.append(
                f"{spec_rel} differs from the spec this session ran "
                f"(sha256 {meta.get('spec_sha256')})"
            )
    else:
        warnings.append(f"spec file {spec_rel!r} not found: its header was not checked")
    return {
        "session_id": sid,
        "dir": str(d),
        "reasons": reasons,
        "warnings": warnings,
        "spec_path": spec_rel,
        "spec_sha256": meta.get("spec_sha256"),
        "spec_file_matches": matches,
        "spec_header_checked": checked,
        "git_commit": (meta.get("git") or {}).get("commit"),
        "git_dirty": (meta.get("git") or {}).get("dirty"),
        "llama_cpp_commit": meta.get("llama_cpp_commit"),
        "state": meta.get("state"),
        "filters": meta.get("filters") or {},
    }


def check_sessions(
    dirs: list[Path], root: Path | None = None, allow_ineligible: bool = False
) -> tuple[list[dict], bool]:
    """Check every session; raise ``Refused`` for the first that may not drive a decision. Returns
    the checks and whether the override was used (it is recorded in the output)."""
    root = Path(root) if root else repo_root()
    checks = [session_check(d, root) for d in dirs]
    bad = [c for c in checks if c["reasons"]]
    override = _override(allow_ineligible)
    if bad and not override:
        c = bad[0]
        raise Refused(
            f"session {c['session_id']} is not eligible to drive a decision: "
            + "; ".join(c["reasons"])
        )
    return checks, bool(bad and override)


def git_state(root: Path | None = None) -> dict:
    """Code commit of the tool that produced a decision, and whether the tree was dirty."""
    root = Path(root) if root else repo_root()

    def run(*args: str) -> str | None:
        p = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )
        return p.stdout.strip() if p.returncode == 0 else None

    commit = run("rev-parse", "HEAD")
    dirty = run("status", "--porcelain", "--", "src", "configs", "scripts")
    return {"commit": commit, "dirty": bool(dirty) if dirty is not None else None}


def build_info_commit(root: Path | None = None) -> str | None:
    p = Path(root or repo_root()) / "data/env/build-info.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    return data.get("commit") or data.get("llama_cpp_commit")


def provenance(
    stage: str,
    checks: list[dict],
    root: Path | None = None,
    *,
    override_used: bool = False,
    git: Callable[[Path | None], dict] = git_state,
) -> dict:
    """Everything needed to reproduce and audit a decision: sessions, spec hashes, plan version,
    code commit, llama.cpp commit and the rule text applied (verbatim)."""
    root = Path(root) if root else repo_root()
    return {
        "stage": stage,
        "sessions": [
            {
                "session_id": c["session_id"],
                "spec_path": c["spec_path"],
                "spec_sha256": c["spec_sha256"],
                "spec_file_matches": c["spec_file_matches"],
                "session_git_commit": c["git_commit"],
                "state": c["state"],
                "filters": c["filters"],
            }
            for c in checks
        ],
        "warnings": [w for c in checks for w in c["warnings"]],
        "plan_version": rules.plan_version(root),
        "code": git(root),
        "llama_cpp_commit": next(
            (c["llama_cpp_commit"] for c in checks if c["llama_cpp_commit"]), None
        ),
        "llama_cpp_build_info_commit": build_info_commit(root),
        "rule_text": list(rules.RULES_BY_STAGE[stage]),
        "eligibility_override": override_used,
    }
