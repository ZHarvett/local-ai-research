"""WP5 health suite: bring up the pinned llama-server and check every endpoint and behaviour that
later steps rely on. Writes ``data/health/endpoints-<UTC date>.json``.

Every server is started through ``scripts/launch-server.sh`` (and stopped with
``scripts/stop-server.sh``); this module never execs llama-server itself. It must run under the
GPU lock (``scripts/healthcheck.sh`` takes care of that). llama.cpp is not modified and nothing is
worked around: unexpected behaviour is recorded as a FAIL with its evidence.

Phases (one or more servers each):

* ``A``  health-64k, no MTP: endpoints, tokenizer, templates, prompt cache, n_probs, thinking
         budget, metrics, slot save/restore (check 6), MTP-off greedy references.
* ``B``  MTP draft length 1: draft_n, acceptance (S4a gate), equivalence.
* ``C``  MTP draft length 2: the same, plus MTP across slot files / the host-RAM prompt cache
         (check 8), one fresh server per arm.
* ``D``  MTP with ``-np 2``: record what the server does.
* ``E``  expert cache (``-cmoe --moe-cache-mib 4096``): statistics line, then the ``-lv 4`` A/B.

Pure helpers (``aggregate_acceptance``, ``draft_verdict``, ``chatml`` ...) are unit-tested without a
GPU; everything that needs a server is marked ``gpu`` in the tests.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import tomllib
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from . import neartie, parsers
from .config import load_machine, load_model, load_server, repo_root
from .gguf_check import normalize_template
from .render import resolve_model_path

ROOT = repo_root()
BASE_CONFIG = ROOT / "configs/server/health-64k.toml"
SLOT_DIR = Path("/dev/shm/local-ai-research-slots")
GREEDY = {"temperature": 0.0, "seed": 1234}
APPENDIX_B_TIMINGS = ["prompt_n", "cache_n", "predicted_n", "prompt_ms", "predicted_ms"]
CODE_FILES = [  # real MIT-licensed sources in third_party/llama.cpp (LICENSE: MIT)
    ("common/fit.cpp", "cpp"),
    ("ggml/src/ggml-cuda/mmvq.cu", "cuda"),
    ("convert_lora_to_gguf.py", "python"),
]
TARGET_TOKENS = 4000
IM_END = "<|im_end|>"

# ------------------------------------------------------------------------------------ records


def excerpt(obj, n: int = 300):
    """Shorten long strings (recursively) for the evidence column."""
    if isinstance(obj, str):
        return obj if len(obj) <= n else obj[:n] + f"...[{len(obj)} chars]"
    if isinstance(obj, dict):
        return {k: excerpt(v, n) for k, v in obj.items()}
    if isinstance(obj, list):
        shown = [excerpt(v, n) for v in obj[:12]]
        return shown + [f"...[{len(obj)} items]"] if len(obj) > 12 else shown
    return obj


class Recorder:
    """Collects check records: PASS/FAIL with the request, the key part of the response, evidence
    and (mandatory for every FAIL) an explanation."""

    def __init__(self, phase: str):
        self.phase = phase
        self.checks: list[dict] = []

    def add(self, cid, name, ok, request=None, response=None, evidence=None, explanation=None):
        if not ok and not explanation:
            raise ValueError(f"check {cid}: a FAIL needs an explanation")
        self.checks.append(
            {
                "id": cid,
                "name": name,
                "phase": self.phase,
                "status": "PASS" if ok else "FAIL",
                "request": excerpt(request),
                "response": excerpt(response),
                "evidence": excerpt(evidence),
                "explanation": explanation,
            }
        )
        print(f"[{self.phase}] {cid}: {'PASS' if ok else 'FAIL'} - {name}", flush=True)
        return ok

    def failed(self) -> list[dict]:
        return [c for c in self.checks if c["status"] == "FAIL"]


# ------------------------------------------------------------------------------- pure helpers


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def template_hash(text: str) -> str:
    """SHA-256 of the whitespace-normalised template (the WP4 normalisation)."""
    return sha256_text(normalize_template(text))


def nonce() -> str:
    return f"[run {uuid.uuid4().hex[:12]}] "


def chatml(system: str, user: str, thinking: bool) -> str:
    """The model's chat format as rendered by its template: the generation prompt opens a
    ``<think>`` block, or (non-thinking) an empty one."""
    head = f"<|im_start|>system\n{system}{IM_END}\n<|im_start|>user\n{user}{IM_END}\n"
    return (
        head + "<|im_start|>assistant\n" + ("<think>\n" if thinking else "<think>\n\n</think>\n\n")
    )


def user_turn(text: str, thinking: bool = False) -> str:
    return f"<|im_start|>user\n{text}{IM_END}\n<|im_start|>assistant\n" + (
        "<think>\n" if thinking else "<think>\n\n</think>\n\n"
    )


def aggregate_acceptance(runs: list[dict]) -> dict:
    """Aggregate over prompts as sum(accepted) / sum(drafted), NOT the mean of per-prompt ratios."""
    drafted = sum(r.get("draft_n", 0) or 0 for r in runs)
    accepted = sum(r.get("draft_n_accepted", 0) or 0 for r in runs)
    return {
        "draft_n": drafted,
        "draft_n_accepted": accepted,
        "acceptance": (accepted / drafted) if drafted else None,
        "per_prompt": [
            {
                "draft_n": r.get("draft_n", 0) or 0,
                "draft_n_accepted": r.get("draft_n_accepted", 0) or 0,
                "acceptance": (r["draft_n_accepted"] / r["draft_n"]) if r.get("draft_n") else None,
                "predicted_n": r.get("predicted_n"),
            }
            for r in runs
        ],
    }


def ratio(t: dict) -> float | None:
    d = t.get("draft_n") or 0
    return (t.get("draft_n_accepted", 0) or 0) / d if d else None


def draft_verdict(control: dict, control2: dict, arm: dict) -> dict:
    """Did the draft state survive? Compare the arm's turn-3 draft statistics with the control and
    with a repeat of the control (run-to-run variation).

    A lost state shows up as fewer drafted tokens or a lower acceptance ratio than both controls,
    by more than the controls differ from each other (at least 0.02 in ratio, 20% in draft_n).
    """
    rc, rc2, ra = ratio(control), ratio(control2), ratio(arm)
    if ra is None:
        return {"verdict": "no_drafting", "detail": "the arm drafted no tokens on turn 3"}
    if rc is None or rc2 is None:
        return {"verdict": "inconclusive", "detail": "a control drafted no tokens"}
    tol_ratio = max(abs(rc - rc2), 0.02)
    n_lo = min(control.get("draft_n") or 0, control2.get("draft_n") or 0)
    n_tol = max(abs((control.get("draft_n") or 0) - (control2.get("draft_n") or 0)), 0.2 * n_lo)
    lower_ratio = ra < min(rc, rc2) - tol_ratio
    fewer = (arm.get("draft_n") or 0) < n_lo - n_tol
    detail = (
        f"acceptance arm {ra:.3f} vs controls {rc:.3f} / {rc2:.3f} (tolerance {tol_ratio:.3f}); "
        f"draft_n arm {arm.get('draft_n')} vs controls {control.get('draft_n')} / "
        f"{control2.get('draft_n')} (tolerance {n_tol:.0f})"
    )
    if lower_ratio or fewer:
        return {"verdict": "draft_state_lost_or_degraded", "detail": detail}
    return {"verdict": "draft_state_preserved", "detail": detail}


def pack_to_tokens(lines: list[str], count_tokens, target: int, low: float = 0.95) -> list[str]:
    """Longest prefix of ``lines`` whose token count is <= target (binary search on lines)."""
    lo, hi = 1, len(lines)
    best = 1
    while lo <= hi:
        mid = (lo + hi) // 2
        n = count_tokens("".join(lines[:mid]))
        if n <= target:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return lines[:best]


def dump_toml(d: dict) -> str:
    out = []
    for k, v in d.items():
        if isinstance(v, bool):
            out.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, int | float):
            out.append(f"{k} = {v}")
        else:
            out.append(f"{k} = {json.dumps(str(v))}")
    return "\n".join(out) + "\n"


def variant_config(overrides: dict) -> dict:
    """The health-64k config with fields overridden; a value of None removes the field."""
    cfg = tomllib.loads(BASE_CONFIG.read_text())
    for k, v in overrides.items():
        if v is None:
            cfg.pop(k, None)
        else:
            cfg[k] = v
    return cfg


# ------------------------------------------------------------------------------ system probes


def run(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def vram_mib() -> int | None:
    p = run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"])
    try:
        return int(p.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return None


def meminfo() -> dict:
    out = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, _, v = line.partition(":")
        if k in ("MemAvailable", "SwapFree", "SwapTotal"):
            out[k + "_mib"] = int(v.split()[0]) // 1024
    for line in Path("/proc/vmstat").read_text().splitlines():
        if line.startswith(("pswpin ", "pgmajfault ")):
            k, v = line.split()
            out[k] = int(v)
    return out


def proc_stats(pid: int) -> dict:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        rss_pages = int(Path(f"/proc/{pid}/statm").read_text().split()[1])
        return {"majflt": int(fields[9]), "rss_mib": rss_pages * 4096 // (1024 * 1024)}
    except (OSError, IndexError, ValueError):
        return {}


def llama_server_processes() -> list[str]:
    p = run(["pgrep", "-a", "llama-server"])
    return [line for line in p.stdout.splitlines() if line.strip()]


def embedded_template_from_gguf(path: str) -> str | None:
    from gguf import GGUFReader

    f = GGUFReader(path).get_field("tokenizer.chat_template")
    return None if f is None else str(f.contents())


# --------------------------------------------------------------------------------- the server


class Server:
    """One llama-server started and stopped through the repository scripts."""

    def __init__(self, phase: str, name: str, overrides: dict, scratch: Path, stamp: str):
        self.phase, self.name, self.overrides = phase, name, overrides
        self.machine = load_machine()
        self.base = f"http://{self.machine.server.host}:{self.machine.server.port}"
        self.rid = f"health-{stamp}-{phase}-{name}"
        self.run_dir = ROOT / "data/logs" / self.rid
        self.cfg_path = scratch / f"{phase}-{name}.toml"
        self.cfg_path.write_text(dump_toml(variant_config(overrides)))
        self.started = False
        self.launch_output = ""
        self.launch_rc: int | None = None
        self.vram: dict[str, int | None] = {}
        self.mem: dict = {}
        self.stop_status: dict | None = None
        self.client: httpx.Client | None = None
        self.pid: int | None = None

    # -- lifecycle
    def __enter__(self) -> Server:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def start(self, health_timeout: int = 420) -> bool:
        self.vram["before"] = vram_mib()
        self.mem["before"] = meminfo()
        kw = {"pass_fds": (9,)} if _fd_open(9) else {}
        p = run(
            [
                str(ROOT / "scripts/launch-server.sh"),
                "--run-id",
                self.rid,
                "--health-timeout",
                str(health_timeout),
                str(self.cfg_path),
            ],
            **kw,
        )
        self.launch_rc = p.returncode
        self.launch_output = (p.stdout + p.stderr).strip()
        self.started = p.returncode == 0
        if self.started:
            self.client = httpx.Client(base_url=self.base, timeout=httpx.Timeout(1200.0))
            pidfile = self.run_dir / "server.pid"
            self.pid = int(pidfile.read_text()) if pidfile.exists() else None
            self.vram["loaded"] = vram_mib()
            self.mem["loaded"] = meminfo() | proc_stats(self.pid or 0)
        return self.started

    def stop(self) -> dict | None:
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.stop_status is None and (self.run_dir / "server.pid").exists():
            self.mem["before_stop"] = meminfo() | proc_stats(self.pid or 0)
            p = run([str(ROOT / "scripts/stop-server.sh"), "--timeout", "90", str(self.run_dir)])
            sf = self.run_dir / "stop-status.json"
            self.stop_status = json.loads(sf.read_text()) if sf.exists() else {"error": p.stderr}
            self.vram["after_stop"] = vram_mib()
        return self.stop_status

    def record(self) -> dict:
        return {
            "phase": self.phase,
            "name": self.name,
            "run_dir": str(self.run_dir.relative_to(ROOT)),
            "overrides": self.overrides,
            "argv": (self.run_dir / "argv.txt").read_text().split("\n")[:-1]
            if (self.run_dir / "argv.txt").exists()
            else None,
            "started": self.started,
            "launch_rc": self.launch_rc,
            "launch_output": excerpt(self.launch_output, 600),
            "vram_mib": self.vram,
            "memory": self.mem,
            "stop_status": self.stop_status,
        }

    # -- log
    @property
    def log_path(self) -> Path:
        return self.run_dir / "server.log"

    def mark(self) -> int:
        return self.log_path.stat().st_size if self.log_path.exists() else 0

    def log_since(self, mark: int) -> str:
        with open(self.log_path, "rb") as f:
            f.seek(mark)
            return f.read().decode("utf-8", errors="replace")

    def log(self) -> str:
        return self.log_since(0)

    # -- http
    def get(self, path: str, **kw) -> httpx.Response:
        return self.client.get(path, **kw)

    def post(self, path: str, body: dict | None = None, **kw) -> httpx.Response:
        return self.client.post(path, json=body or {}, **kw)

    def tokenize(self, text: str, pieces: bool = False) -> list:
        r = self.post(
            "/tokenize",
            {"content": text, "add_special": False, "parse_special": True, "with_pieces": pieces},
        )
        r.raise_for_status()
        return r.json()["tokens"]

    def n_tokens(self, text: str) -> int:
        return len(self.tokenize(text))

    def completion(self, prompt, n_predict: int, **params) -> dict:
        body = {"prompt": prompt, "n_predict": n_predict, "return_tokens": True} | params
        r = self.post("/completion", body)
        r.raise_for_status()
        return r.json()

    def slot_action(self, action: str, filename: str | None = None) -> dict:
        body = {"filename": filename} if filename else {}
        r = self.post(f"/slots/0?action={action}", body)
        return {"http": r.status_code, "body": r.json() if r.content else None}


def _fd_open(fd: int) -> bool:
    try:
        os.fstat(fd)
        return True
    except OSError:
        return False


def timings_of(resp: dict) -> dict:
    t = resp.get("timings", {}) or {}
    return {
        k: t.get(k)
        for k in (
            "cache_n",
            "prompt_n",
            "prompt_ms",
            "prompt_per_second",
            "predicted_n",
            "predicted_ms",
            "predicted_per_second",
            "draft_n",
            "draft_n_accepted",
        )
        if k in t
    }


# -------------------------------------------------------------------- shared test material


def build_code_prompts(srv: Server, repo_commit: str) -> list[dict]:
    """Three prompts from real source files, about TARGET_TOKENS tokens of code each."""
    out = []
    for rel, lang in CODE_FILES:
        text = (ROOT / "third_party/llama.cpp" / rel).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        kept = pack_to_tokens(lines, srv.n_tokens, TARGET_TOKENS)
        code = "".join(kept)
        user = (
            f"Below is the beginning of the source file `{rel}` from the llama.cpp project.\n\n"
            f"```{lang}\n{code}```\n\nContinue the code: write the next function(s) in the same "
            "style. Reply with code only."
        )
        system = "You are an expert programmer. Reply with code only."
        out.append(
            {
                "recipe": {
                    "repo": "ggml-org/llama.cpp (MIT)",
                    "commit": repo_commit,
                    "file": rel,
                    "lines_kept": len(kept),
                    "code_tokens": srv.n_tokens(code),
                },
                "system": system,
                "user": user,
                "prompt": chatml(system, user, thinking=False),
                "prompt_thinking": chatml(system, user, thinking=True),
            }
        )
        out[-1]["recipe"]["prompt_tokens"] = srv.n_tokens(out[-1]["prompt"])
        out[-1]["recipe"]["prompt_sha256"] = sha256_text(out[-1]["prompt"])
    return out


def card_sampling() -> dict:
    s = load_model().sampling.general
    return {"temperature": s.temperature, "top_p": s.top_p, "top_k": s.top_k, "seed": 1234}


def acceptance_runs(srv: Server, prompts: list[dict], sampling: dict, key="prompt") -> dict:
    runs = []
    for p in prompts:
        r = srv.completion(p[key], 512, cache_prompt=False, **sampling)
        t = timings_of(r)
        t["text_head"] = r.get("content", "")[:120]
        runs.append(t)
    return aggregate_acceptance(runs) | {"timings_keys": sorted(runs[0].keys())}


def equivalence_runs(srv: Server, prompts: list[dict]) -> list[dict]:
    """Greedy 256-token runs with the top-2 alternatives of every generated token."""
    out = []
    for p in prompts:
        r = srv.completion(p["prompt"], 256, cache_prompt=False, n_probs=2, **GREEDY)
        out.append(
            {
                "file": p["recipe"]["file"],
                "tokens": r.get("tokens", []),
                "gaps": neartie.gaps_of(r.get("completion_probabilities")),
                "has_probs": bool(r.get("completion_probabilities")),
                "timings": timings_of(r),
            }
        )
    return out


def compare_equivalence(off: list[dict], on: list[dict]) -> list[dict]:
    res = []
    for a, b in zip(off, on, strict=True):
        d = neartie.classify(a["tokens"], b["tokens"], a["gaps"], b["gaps"], prefer="b")
        res.append(
            {"file": a["file"], "n_off": len(a["tokens"]), "n_on": len(b["tokens"])} | d.as_dict()
        )
    return res


# --------------------------------------------------------------------------------- phase A


def thinking_prompt(variant: int) -> str:
    if variant == 0:
        return (
            "Solve this puzzle. Five houses stand in a row, numbered 1 to 5 from left to right. "
            "Each house has a different colour (red, green, blue, yellow, white), a different "
            "owner (Ann, Bob, Cy, Di, Ed), a different pet (cat, dog, fish, bird, snake), a "
            "different drink (tea, coffee, milk, juice, water) and a different hobby (chess, "
            "golf, piano, chess-boxing, painting). Clues: Ann lives in the red house. Bob owns "
            "the dog. The green house is immediately to the left of the white house. The owner of "
            "the green house drinks coffee. The person who plays piano owns the bird. The owner "
            "of the yellow house paints. The person in the middle house drinks milk. Cy lives in "
            "the first house. The golf player lives next to the cat owner. The painter lives "
            "next to the horse... no horse exists, ignore that clue. The chess player drinks "
            "juice. Di plays chess-boxing. Ed lives next to the blue house. Check every "
            "constraint carefully and give the full assignment."
        )
    return (
        "Find all positive integers n < 200 such that n^2 + n + 41 is NOT prime, and list the "
        "first ten. Verify each candidate by explicit factorisation and double-check your "
        "arithmetic step by step before answering."
    )


def check_thinking_budget(srv: Server, rec: Recorder) -> dict:
    def ask(prompt: str, **extra) -> dict:
        body = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 3000,
            "temperature": 0.0,
            "seed": 1234,
        } | extra
        r = srv.post("/v1/chat/completions", body)
        r.raise_for_status()
        j = r.json()
        msg = j["choices"][0]["message"]
        reasoning = msg.get("reasoning_content") or ""
        return {
            "reasoning_tokens": len(srv.tokenize(reasoning)) if reasoning else 0,
            "content_chars": len(msg.get("content") or ""),
            "content_head": (msg.get("content") or "")[:160],
            "reasoning_tail": reasoning[-160:],
            "finish_reason": j["choices"][0].get("finish_reason"),
            "completion_tokens": j.get("usage", {}).get("completion_tokens"),
            "timings": timings_of(j),
        }

    free = None
    for variant in (0, 1):
        free = ask(thinking_prompt(variant))
        if free["reasoning_tokens"] >= 300:
            break
    budget = 64
    capped = ask(thinking_prompt(variant), reasoning_budget_tokens=budget)
    alias = ask(thinking_prompt(variant), thinking_budget_tokens=budget)
    ok = (
        free["reasoning_tokens"] >= 300
        and capped["reasoning_tokens"] <= budget + 32
        and capped["reasoning_tokens"] <= 0.25 * free["reasoning_tokens"]
        and capped["content_chars"] > 0
    )
    expl = None
    if not ok:
        expl = (
            f"unbudgeted reasoning {free['reasoning_tokens']} tokens, budgeted "
            f"{capped['reasoning_tokens']} (budget {budget}); a PASS needs unbudgeted >= 300, "
            f"budgeted <= {budget + 32} and <= 25% of unbudgeted, and an answer after the thinking"
        )
    rec.add(
        "4.thinking_budget",
        "per-request thinking budget honoured with the global --reasoning-budget unset",
        ok,
        request={
            "endpoint": "/v1/chat/completions",
            "field": "reasoning_budget_tokens (alias thinking_budget_tokens)",
            "budget": budget,
            "prompt_variant": variant,
        },
        response={"without_budget": free, "with_budget": capped, "with_alias": alias},
        evidence={
            "reasoning_tokens_without": free["reasoning_tokens"],
            "reasoning_tokens_with_64": capped["reasoning_tokens"],
            "alias_reasoning_tokens": alias["reasoning_tokens"],
            "global_flag": "--reasoning-budget not given (default -1)",
        },
        explanation=expl,
    )
    return {"free": free, "budget": capped, "alias": alias}


def slot_test(srv: Server, rec: Recorder, tag: str) -> dict:
    """Check 6: save, erase, restore, continue; compare with a never-saved continuation."""
    system = nonce() + "You are a careful assistant."
    code = (ROOT / "third_party/llama.cpp/common/fit.cpp").read_text().splitlines(keepends=True)
    user = "Summarise this code in one sentence:\n" + "".join(
        pack_to_tokens(code, srv.n_tokens, 1200)
    )
    p_tokens = srv.tokenize(chatml(system, user, thinking=False))
    fname = f"wp5-{tag}.bin"

    r1 = srv.completion(p_tokens, 48, cache_prompt=True, **GREEDY)
    g1 = r1["tokens"]
    prompt2 = p_tokens + g1 + srv.tokenize(user_turn("Now list its helper functions."))
    save = srv.slot_action("save", fname)

    m = srv.mark()
    ctl = srv.completion(prompt2, 64, cache_prompt=True, n_probs=2, **GREEDY)
    ctl_log = srv.log_since(m)

    erase = srv.slot_action("erase")
    m = srv.mark()
    erase_check = srv.completion(p_tokens, 0, cache_prompt=True, **GREEDY)
    erase_log = srv.log_since(m)
    erase_src = parsers.parse_cache_source("", erase_log, erase_check["timings"].get("cache_n"))

    m_a = srv.mark()
    restore = srv.slot_action("restore", fname)
    action_log = srv.log_since(m_a)
    m = srv.mark()
    res = srv.completion(prompt2, 64, cache_prompt=True, n_probs=2, **GREEDY)
    res_log = srv.log_since(m)
    cache_n = res["timings"].get("cache_n")
    n_restored = (restore.get("body") or {}).get("n_restored")
    src = parsers.parse_cache_source(action_log, res_log, cache_n, n_restored)
    verdict = neartie.classify(
        ctl["tokens"],
        res["tokens"],
        neartie.gaps_of(ctl.get("completion_probabilities")),
        neartie.gaps_of(res.get("completion_probabilities")),
    )
    expected = save["body"].get("n_saved") if save.get("body") else None
    erase_clean = (erase_check["timings"].get("cache_n") or 0) == 0
    restored_ok = (cache_n or 0) >= 0.9 * (expected or 1) and src["verdict"] == "slot_restore"
    confounded = (not erase_clean) or src["verdict"] == "prompt_cache"
    data = {
        "tag": tag,
        "cache_ram": "default" if tag == "default" else tag,
        "prompt_tokens": len(p_tokens),
        "saved_tokens": expected,
        "save": save,
        "erase": erase,
        "erase_check": {"timings": timings_of(erase_check), "source": erase_src},
        "restore": restore,
        "control": {
            "timings": timings_of(ctl),
            "prompt_cache_load": "found better prompt" in ctl_log,
        },
        "restored": {"timings": timings_of(res), "source": src},
        "continuation_equivalence": verdict.as_dict(),
        "confounded_by_prompt_cache": confounded,
        "log_restore_action": excerpt(action_log, 500),
    }
    ok = (
        save["http"] == 200
        and restore["http"] == 200
        and erase["http"] == 200
        and verdict.ok
        and restored_ok
        and erase_clean
    )
    expl = None
    if not ok:
        why = []
        if not erase_clean:
            why.append(
                f"after erase a fresh request for the same prompt reported cache_n="
                f"{erase_check['timings'].get('cache_n')} (source: {erase_src['verdict']}), so "
                "the erase check is confounded by the host-RAM prompt cache"
            )
        if not restored_ok:
            why.append(
                f"after restore cache_n={cache_n} (saved {expected} tokens), prefix source "
                f"'{src['verdict']}'"
            )
        if not verdict.ok:
            why.append(f"continuation differs from the never-saved run: {verdict.reason}")
        for n, a in (("save", save), ("erase", erase), ("restore", restore)):
            if a["http"] != 200:
                why.append(f"{n} returned HTTP {a['http']}: {a['body']}")
        expl = "; ".join(why)
    rec.add(
        f"6.slots_save_erase_restore[{tag}]",
        f"slot save, erase, restore, continue (cache-ram {tag})",
        ok,
        request={"slot": 0, "file": fname, "continuation_tokens": 64},
        response={
            "n_saved": expected,
            "erase_check_cache_n": erase_check["timings"].get("cache_n"),
            "restored_cache_n": cache_n,
            "restored_source": src["verdict"],
        },
        evidence=data,
        explanation=expl,
    )
    del ctl_log
    return data


def phase_a(ctx: dict) -> dict:
    rec = Recorder("A")
    data: dict = {}
    servers = []
    with Server("A", "health64k", {}, ctx["scratch"], ctx["stamp"]) as srv:
        servers.append(srv)
        if not srv.started:
            rec.add("0.start", "health-64k server starts", False, explanation=srv.launch_output)
            return {"checks": rec.checks, "servers": [srv.record()]}
        machine_model = resolve_model_path(load_server(BASE_CONFIG), load_machine(), load_model())
        # ---- 1. basic
        h = srv.get("/health")
        rec.add(
            "1.health",
            "GET /health",
            h.status_code == 200,
            "GET /health",
            h.json(),
            explanation=f"HTTP {h.status_code}",
        )
        props = srv.get("/props").json()
        gen = props.get("default_generation_settings", {})
        n_ctx = gen.get("n_ctx")
        rec.add(
            "1.props.n_ctx",
            "/props n_ctx equals the requested context",
            n_ctx == 65536 and props.get("total_slots") == 1,
            "GET /props",
            {"n_ctx": n_ctx, "total_slots": props.get("total_slots")},
            explanation=f"n_ctx={n_ctx}, total_slots={props.get('total_slots')}, requested 65536/1",
        )
        tmpl = props.get("chat_template", "")
        embedded = embedded_template_from_gguf(machine_model)
        h_props, h_emb = template_hash(tmpl), template_hash(embedded or "")
        h_off = load_model().chat_template.normalized_sha256
        rec.add(
            "1.props.template",
            "/props chat template equals the template embedded in the GGUF (decision: embedded)",
            h_props == h_emb,
            "GET /props -> chat_template",
            {
                "props_sha256": h_props,
                "embedded_sha256": h_emb,
                "official_sha256": h_off,
                "props_equals_official": h_props == h_off,
            },
            {
                "normalisation": "whitespace runs -> one space, stripped, UTF-8, SHA-256",
                "model_check_json": "stores identical=false and the diff, no hash; embedded hash "
                "computed from the GGUF here",
            },
            explanation="the template llama-server reports differs from the GGUF-embedded one",
        )
        rec.add(
            "1.props.model_path",
            "/props model path is the verified GGUF",
            props.get("model_path") == machine_model,
            "GET /props",
            {"model_path": props.get("model_path"), "expected": machine_model},
            explanation="model_path differs from the configured model file",
        )
        data["props"] = {
            "build_info": props.get("build_info"),
            "n_ctx": n_ctx,
            "total_slots": props.get("total_slots"),
            "chat_template_caps": props.get("chat_template_caps"),
            "bos_token": props.get("bos_token"),
            "eos_token": props.get("eos_token"),
            "endpoints": {k: v for k, v in props.items() if k.startswith("endpoint_")},
            "default_sampling": {
                k: gen.get("params", {}).get(k)
                for k in ("temperature", "top_k", "top_p", "min_p", "seed")
            },
        }
        # warm-up and VRAM
        srv.completion("def fib(n):", 16, cache_prompt=False, **GREEDY)
        srv.vram["after_warmup"] = vram_mib()
        placement = parsers.parse_fit_placement(srv.log())
        data["placement"] = placement
        data["startup_warnings"] = placement.get("warnings")

        # ---- 2. tokenize / templates
        text = "Hello, world! def f(x): return x * 2  # naïve ünïcode ✓"
        r = srv.post("/tokenize", {"content": text, "add_special": False, "with_pieces": True})
        pieces = r.json().get("tokens", [])
        ids = [p["id"] for p in pieces if isinstance(p, dict)]
        plain = srv.tokenize(text)
        det = srv.post("/detokenize", {"tokens": ids}).json().get("content")
        rec.add(
            "2.tokenize",
            "/tokenize with_pieces, /detokenize round trip",
            bool(ids) and ids == plain and det == text,
            {"content": text, "with_pieces": True},
            {"first_pieces": pieces[:4], "n_tokens": len(ids), "detokenized": det},
            explanation=f"ids==plain: {ids == plain}; round trip equal: {det == text}",
        )
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }
        ]
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Weather in Paris?"},
        ]
        at = srv.post("/apply-template", {"messages": msgs, "tools": tools})
        prompt_text = at.json().get("prompt", "") if at.status_code == 200 else ""
        n_apply = srv.n_tokens(prompt_text) if prompt_text else None
        chat = srv.post(
            "/v1/chat/completions",
            {"messages": msgs, "tools": tools, "max_tokens": 1, "temperature": 0.0},
        )
        n_chat = (
            chat.json().get("usage", {}).get("prompt_tokens") if chat.status_code == 200 else None
        )
        dev = srv.post(
            "/apply-template",
            {"messages": [{"role": "developer", "content": "Be terse."}, msgs[1]]},
        )
        unk = srv.post(
            "/apply-template", {"messages": [{"role": "narrator", "content": "x"}, msgs[1]]}
        )
        manual = chatml("You are helpful.", "Weather in Paris?", thinking=True)
        plain_at = srv.post("/apply-template", {"messages": msgs}).json().get("prompt")
        rec.add(
            "2.apply_template",
            "/apply-template with tools, checked against the embedded template",
            at.status_code == 200 and "get_weather" in prompt_text and n_apply == n_chat,
            {"messages": msgs, "tools": "get_weather(city)"},
            {
                "http": at.status_code,
                "prompt_head": prompt_text[:200],
                "prompt_tail": prompt_text[-60:],
                "apply_template_tokens": n_apply,
                "chat_completions_prompt_tokens": n_chat,
            },
            {
                "developer_role_http": dev.status_code,
                "unknown_role_http": unk.status_code,
                "note": "the embedded template accepts the developer role and unknown roles; the "
                "official one raises (docs/decisions.md)",
                "manual_chatml_equals_template": plain_at == manual,
            },
            explanation="tool block missing from the rendered prompt, or its token count differs "
            "from the prompt the chat endpoint actually evaluated",
        )

        # ---- 3. completions and the prompt cache
        pnonce = nonce()
        base_prompt = chatml(pnonce + "You are brief.", "Name three primary colours.", False)
        c1 = srv.completion(base_prompt, 24, cache_prompt=True, **GREEDY)
        c2 = srv.completion(base_prompt, 24, cache_prompt=True, **GREEDY)
        c3 = srv.completion(base_prompt, 24, cache_prompt=False, **GREEDY)
        t1 = c1.get("timings", {})
        missing = [k for k in APPENDIX_B_TIMINGS if k not in t1]
        rec.add(
            "3.timings",
            "/completion returns the Appendix B timings fields",
            not missing,
            "POST /completion",
            timings_of(c1),
            {
                "all_timing_keys": sorted(t1.keys()),
                "appendix_b": ["prompt_n", "cache_n", "predicted_n"],
            },
            explanation=f"missing timings fields: {missing}",
        )
        data["timing_fields"] = sorted(t1.keys())
        rec.add(
            "3.prompt_cache.reuse",
            "a repeated prefix is reused (cache_n > 0)",
            (c2["timings"].get("cache_n") or 0) > 0,
            "same prompt twice",
            {"first": timings_of(c1), "second": timings_of(c2)},
            explanation=f"second request cache_n={c2['timings'].get('cache_n')}",
        )
        rec.add(
            "3.prompt_cache.disabled",
            "cache_prompt:false gives cache_n = 0",
            (c3["timings"].get("cache_n") or 0) == 0,
            "same prompt, cache_prompt=false",
            timings_of(c3),
            explanation=f"cache_n={c3['timings'].get('cache_n')}",
        )
        np_ = srv.completion("The capital of France is", 6, n_probs=4, **GREEDY)
        cp = np_.get("completion_probabilities") or []
        first = cp[0] if cp else {}
        alts = first.get("top_logprobs") or first.get("top_probs") or []
        rec.add(
            "3.n_probs",
            "n_probs returns alternatives for each generated token",
            len(cp) == len(np_.get("tokens", [])) and len(alts) >= 2,
            {"n_probs": 4},
            {
                "entries": len(cp),
                "alternatives_in_first": len(alts),
                "first_entry_keys": sorted(first.keys()),
                "first_entry": first,
            },
            {"format": "default (not post_sampling_probs)"},
            explanation=f"{len(cp)} entries for {len(np_.get('tokens', []))} tokens; "
            f"{len(alts)} alternatives",
        )
        data["n_probs_format"] = {"keys": sorted(first.keys()), "alternatives": len(alts)}

        # ---- 4. thinking budget
        data["thinking_budget"] = check_thinking_budget(srv, rec)

        # ---- 5. metrics
        mtext = srv.get("/metrics").text
        names = sorted(set(re.findall(r"^# TYPE (\S+)", mtext, re.M)))
        mm = re.search(r"^llamacpp:prompt_tokens_total (\S+)", mtext, re.M)
        rec.add(
            "5.metrics",
            "/metrics returns Prometheus text",
            bool(names) and bool(mm) and float(mm[1]) > 0,
            "GET /metrics",
            {
                "content_type_ok": "# HELP" in mtext,
                "metric_names": names[:12],
                "n_metrics": len(names),
                "prompt_tokens_total": mm[1] if mm else None,
            },
            explanation="no '# TYPE' lines or no llamacpp:prompt_tokens_total counter > 0",
        )

        # ---- 6. slots
        data["slot_test_default"] = slot_test(srv, rec, "default")
        rec.add(
            "6.slots_listing",
            "GET /slots lists the slot",
            srv.get("/slots").status_code == 200,
            "GET /slots",
            {"slots": len(srv.get("/slots").json())},
            explanation="/slots did not answer HTTP 200",
        )

        # ---- MTP-off references (used by phases B and C)
        prompts = build_code_prompts(srv, ctx["llama_commit"])
        data["code_prompts"] = [p["recipe"] for p in prompts]
        data["reference"] = equivalence_runs(srv, prompts)
        data["reference_has_probs"] = all(x["has_probs"] for x in data["reference"])
    data["server_log_checkpoints"] = parsers.parse_checkpoints(srv.log())

    # repeat the slot test with --cache-ram 0 when the default run was confounded
    slot_default = data["slot_test_default"]
    if slot_default["confounded_by_prompt_cache"]:
        with Server("A", "cacheram0", {"cache_ram": 0}, ctx["scratch"], ctx["stamp"]) as s0:
            servers.append(s0)
            if s0.started:
                data["slot_test_cache_ram0"] = slot_test(s0, rec, "cache-ram-0")
            else:
                rec.add(
                    "6.cache_ram0.start",
                    "server with --cache-ram 0 starts",
                    False,
                    explanation=s0.launch_output,
                )
    return {"checks": rec.checks, "servers": [s.record() for s in servers], "phase_a": data}


# --------------------------------------------------------------------------------- phase B / C


def mtp_overrides(n: int, **extra) -> dict:
    return {"spec_type": "draft-mtp", "spec_draft_n_max": n} | extra


def mtp_basic(srv: Server, rec: Recorder, n: int, ctx: dict, ref: list[dict], prompts: list[dict]):
    """Checks 7: draft_n, acceptance (greedy; card sampling for information), equivalence."""
    out: dict = {"draft_length": n}
    probe = srv.completion(prompts[0]["prompt"], 64, cache_prompt=False, **GREEDY)
    t = timings_of(probe)
    rec.add(
        f"7.mtp.draft_n[{n}]",
        f"MTP draft length {n}, -np 1: draft_n > 0",
        (t.get("draft_n") or 0) > 0,
        {"spec_draft_n_max": n, "n_predict": 64},
        t,
        {"timings_keys": sorted((probe.get("timings") or {}).keys())},
        explanation=f"draft_n missing or 0 in timings: {t}",
    )
    out["timings_keys_with_drafting"] = sorted((probe.get("timings") or {}).keys())
    greedy = acceptance_runs(srv, prompts, GREEDY)
    card = acceptance_runs(srv, prompts, card_sampling())
    think = acceptance_runs(srv, prompts, GREEDY, key="prompt_thinking")
    out["acceptance_greedy"] = greedy
    out["acceptance_card_sampling"] = card
    out["acceptance_greedy_thinking_on"] = think
    if n == 1:
        a = greedy["acceptance"]
        rec.add(
            "7.mtp.acceptance_d1_greedy",
            "S4(a): acceptance at draft length 1 >= 50% (greedy, code)",
            a is not None and a >= 0.5,
            {
                "prompts": 3,
                "n_predict": 512,
                "temperature": 0,
                "aggregate": "sum(draft_n_accepted)/sum(draft_n)",
            },
            {k: greedy[k] for k in ("draft_n", "draft_n_accepted", "acceptance")},
            {
                "per_prompt": greedy["per_prompt"],
                "card_sampling_info_only": card["acceptance"],
                "thinking_on_info_only": think["acceptance"],
            },
            explanation=f"aggregate greedy acceptance {a} is below 0.5",
        )
        out["s4a_pass"] = a is not None and a >= 0.5
    else:
        rec.add(
            f"7.mtp.acceptance_d{n}",
            f"acceptance at draft length {n} (recorded)",
            greedy["draft_n"] > 0,
            {"prompts": 3, "n_predict": 512, "temperature": 0},
            {k: greedy[k] for k in ("draft_n", "draft_n_accepted", "acceptance")},
            {
                "per_prompt": greedy["per_prompt"],
                "card_sampling": card["acceptance"],
                "thinking_on": think["acceptance"],
            },
            explanation="no draft tokens at all",
        )
    on = equivalence_runs(srv, prompts)
    if len(ref) != len(on):
        rec.add(
            f"7.mtp.equivalence[{n}]",
            f"greedy MTP off vs on (draft length {n})",
            False,
            explanation="no MTP-off reference from phase A in this run directory",
        )
        out["n_probs_with_drafting"] = all((x["timings"].get("draft_n") or 0) > 0 for x in on)
        return out
    cmp_ = compare_equivalence(ref, on)
    out["equivalence"] = cmp_
    out["n_probs_with_drafting"] = all((x["timings"].get("draft_n") or 0) > 0 for x in on)
    bad = [c for c in cmp_ if c["verdict"] not in ("identical", "near_tie")]
    rec.add(
        f"7.mtp.equivalence[{n}]",
        f"greedy MTP off vs on (draft length {n}), 3 prompts x 256 tokens",
        not bad,
        {"n_probs": 2, "near_tie_rule": "top-2 gap < 0.5 nats at the first divergence"},
        [
            {k: c[k] for k in ("file", "verdict", "position", "gap_nats", "gap_source")}
            for c in cmp_
        ],
        {
            "has_probs_with_mtp": all(x["has_probs"] for x in on),
            "drafting_during_n_probs": out["n_probs_with_drafting"],
        },
        explanation="; ".join(
            f"{c['file']}: {c['verdict']} at {c['position']} ({c['reason']})" for c in bad
        ),
    )
    return out


def phase_b(ctx: dict) -> dict:
    rec = Recorder("B")
    ref_doc = ctx["phases"].get("A", {}).get("phase_a")
    with Server("B", "mtp-d1", mtp_overrides(1), ctx["scratch"], ctx["stamp"]) as srv:
        if not srv.started:
            rec.add(
                "7.mtp.start_d1",
                "MTP draft length 1 server starts",
                False,
                explanation=srv.launch_output,
            )
            return {"checks": rec.checks, "servers": [srv.record()], "s4a_pass": False}
        prompts = build_code_prompts(srv, ctx["llama_commit"])
        ref = ref_doc["reference"] if ref_doc else None
        if ref is None:
            rec.add(
                "7.mtp.reference",
                "MTP-off reference from phase A available",
                False,
                explanation="phase A has not run in this run directory",
            )
            return {"checks": rec.checks, "servers": [srv.record()], "s4a_pass": False}
        srv.completion("def fib(n):", 16, cache_prompt=False, **GREEDY)
        srv.vram["after_warmup"] = vram_mib()
        placement = parsers.parse_fit_placement(srv.log())
        data = mtp_basic(srv, rec, 1, ctx, ref, prompts)
        data["placement"] = placement
    return {
        "checks": rec.checks,
        "servers": [srv.record()],
        "phase_b": data,
        "s4a_pass": data.get("s4a_pass", False),
    }


CONV_SYSTEM = "You are a concise assistant that writes short Python snippets."
CONV_USERS = [
    "Write a Python function fib(n) that returns the n-th Fibonacci number. Code only.",
    "Now add type hints and a one-line docstring. Code only.",
    "Now write three pytest tests for it. Code only.",
]


class Convo:
    """A deterministic multi-turn chat built on token arrays, so every turn is a pure append to
    exactly the tokens the server evaluated (nothing is re-rendered or re-tokenized)."""

    def __init__(self, srv: Server, nonce_text: str, users: list[str], system=CONV_SYSTEM):
        self.srv, self.users = srv, users
        self.tokens: list[int] = srv.tokenize(chatml(nonce_text + system, users[0], False))
        self.results: list[dict] = []

    def turn(self, i: int, n_predict: int = 160, **params) -> dict:
        if i > 0:
            tail = f"{IM_END}\n" if self.tokens[-1] != self.srv.tokenize(IM_END)[0] else "\n"
            self.tokens = self.tokens + self.srv.tokenize(tail + user_turn(self.users[i]))
        r = self.srv.completion(self.tokens, n_predict, cache_prompt=True, **GREEDY, **params)
        self.tokens = self.tokens + r["tokens"]
        self.results.append(r)
        return r


def turn_record(r: dict) -> dict:
    t = timings_of(r)
    return t | {
        "n_tokens": len(r.get("tokens", [])),
        "text_head": r.get("content", "")[:100],
    }


def scenario_users(srv: Server, scenario: str) -> list[str]:
    """User turns of a check-8 conversation. ``short``: about 180 tokens of history after turn 2.
    ``long``: turn 1 carries about 3,000 tokens of real code, so the draft context holds real
    history (more sensitive to a lost draft state) while staying below --checkpoint-min-step."""
    if scenario == "short":
        return CONV_USERS
    code = (ROOT / "third_party/llama.cpp/common/fit.cpp").read_text().splitlines(keepends=True)
    kept = "".join(pack_to_tokens(code, srv.n_tokens, 3000))
    first = (
        f"Here is a C++ file:\n```cpp\n{kept}```\n"
        "Write a Python function fib(n) that returns the n-th Fibonacci number. Code only."
    )
    return [first, *CONV_USERS[1:]]


def run_arm(
    ctx: dict, arm: str, overrides: dict, use_probs: bool, sub: str, scenario: str = "short"
) -> dict:
    """One check-8 arm on its own fresh MTP server (draft length 2, -np 1, 64K)."""
    n8 = "[check8 conversation] "  # same text in every arm on purpose: arms run on separate servers
    probs = {"n_probs": 2} if use_probs else {}
    name = f"{scenario}-{sub}"
    with Server("C", name, mtp_overrides(2) | overrides, ctx["scratch"], ctx["stamp"]) as srv:
        if not srv.started:
            return {"arm": arm, "error": srv.launch_output, "server": srv.record()}
        conv = Convo(srv, n8, scenario_users(srv, scenario))
        conv.turn(0)
        conv.turn(1)
        info: dict = {"context_tokens_after_turn2": len(conv.tokens)}
        action_log = ""
        if arm in ("slot_files", "slot_files_cache_ram0"):
            fname = f"wp5-c8-{scenario}-{sub}.bin"
            info["save"] = srv.slot_action("save", fname)
            info["erase"] = srv.slot_action("erase")
            m = srv.mark()
            info["restore"] = srv.slot_action("restore", fname)
            action_log = srv.log_since(m)
        elif arm == "prompt_cache":
            other = Convo(
                srv, nonce(), ["Explain what a hash map is in two sentences."], "You are brief."
            )
            other.turn(0, 64)
            info["unrelated_context_tokens"] = len(other.tokens)
        m = srv.mark()
        r3 = conv.turn(2, **probs)
        seg = srv.log_since(m)
        t3 = timings_of(r3)
        restored = (info.get("restore") or {}).get("body") or {}
        info["source"] = parsers.parse_cache_source(
            action_log, seg, t3.get("cache_n"), restored.get("n_restored")
        )
        info["checkpoints_in_restore_action"] = parsers.parse_checkpoints(action_log)
        info["checkpoints_in_turn3"] = parsers.parse_checkpoints(seg)
        info["checkpoint_log_lines_turn3"] = [
            ln.split(" ", 2)[-1] for ln in seg.splitlines() if "checkpoint" in ln
        ][:10]
        full_log = srv.log()
        return {
            "arm": arm,
            "turn3": turn_record(r3),
            "turn3_tokens": r3["tokens"],
            "turn3_gaps": neartie.gaps_of(r3.get("completion_probabilities")),
            "info": info,
            "checkpoints": parsers.parse_checkpoints(full_log),
            "spec_stats_log": parsers.parse_spec_stats(seg),
            "draft_state_log_lines": [
                ln for ln in (action_log + seg).splitlines() if "draft" in ln.lower()
            ][:8],
            "prompt_save_lines": [
                ln.split(" ", 2)[-1] for ln in full_log.splitlines() if "prompt_save" in ln
            ][:8],
            "server": srv.record(),
            "turn_summaries": [turn_record(x) for x in conv.results],
        }


def compare_arm(ctl: dict, ctl2: dict, arm: dict) -> dict:
    d = neartie.classify(
        ctl["turn3_tokens"], arm["turn3_tokens"], ctl["turn3_gaps"], arm["turn3_gaps"], prefer="b"
    )
    dv = draft_verdict(ctl["turn3"], ctl2["turn3"], arm["turn3"])
    prefix = arm["info"]["context_tokens_after_turn2"]
    cache_n = arm["turn3"].get("cache_n") or 0
    exercised = cache_n >= 0.9 * prefix
    return {
        "arm": arm["arm"],
        "restore_exercised": exercised,
        "cache_n": cache_n,
        "prefix_tokens": prefix,
        "source": arm["info"]["source"]["verdict"],
        "tokens_vs_control": d.as_dict(),
        "draft": dv,
        "turn3": {
            k: arm["turn3"].get(k)
            for k in ("cache_n", "prompt_n", "predicted_n", "draft_n", "draft_n_accepted")
        },
    }


def phase_c(ctx: dict) -> dict:
    rec = Recorder("C")
    servers = []
    ref_doc = ctx["phases"].get("A", {}).get("phase_a")
    data: dict = {}
    with Server("C", "mtp-d2", mtp_overrides(2), ctx["scratch"], ctx["stamp"]) as srv:
        servers.append(srv)
        if not srv.started:
            rec.add(
                "7.mtp.start_d2",
                "MTP draft length 2 server starts",
                False,
                explanation=srv.launch_output,
            )
            return {"checks": rec.checks, "servers": [srv.record()]}
        prompts = build_code_prompts(srv, ctx["llama_commit"])
        srv.completion("def fib(n):", 16, cache_prompt=False, **GREEDY)
        srv.vram["after_warmup"] = vram_mib()
        data = mtp_basic(srv, rec, 2, ctx, ref_doc["reference"] if ref_doc else [], prompts)
        data["placement"] = parsers.parse_fit_placement(srv.log())
        data["props_after"] = {
            "total_slots": srv.get("/props").json().get("total_slots"),
        }
    use_probs = bool(data.get("n_probs_with_drafting"))
    c8 = {"n_probs_used_on_turn3": use_probs, "thinking": "off (empty think block)"}
    for scenario in ("short", "long"):
        c8[scenario] = check8_scenario(ctx, rec, scenario, use_probs)
    return {
        "checks": rec.checks,
        "servers": [s.record() for s in servers],
        "phase_c": data | {"check8": c8},
    }


def check8_scenario(ctx: dict, rec: Recorder, scenario: str, use_probs: bool) -> dict:
    """Control, control repeat, slot files, host-RAM prompt cache; one fresh server per arm."""
    c8: dict = {
        "scenario": scenario,
        "conversation": {"system": CONV_SYSTEM, "users": [u[:200] for u in CONV_USERS]},
    }
    sc = scenario
    ctl = run_arm(ctx, "control", {}, use_probs, "control", sc)
    ctl2 = run_arm(ctx, "control_repeat", {}, use_probs, "control2", sc)
    arms = {
        "slot_files": run_arm(ctx, "slot_files", {}, use_probs, "slotfiles", sc),
        "prompt_cache": run_arm(ctx, "prompt_cache", {}, use_probs, "promptcache", sc),
    }
    for a in (ctl, ctl2, *arms.values()):
        if srv_rec := a.pop("server", None):
            c8.setdefault("servers", []).append(srv_rec)
    if "error" in ctl or "error" in ctl2:
        rec.add(
            f"8.control[{sc}]",
            "MTP save/restore control runs",
            False,
            explanation=str(ctl.get("error") or ctl2.get("error")),
        )
        return c8
    c8["control"] = {
        k: ctl[k]
        for k in (
            "turn3",
            "info",
            "checkpoints",
            "turn_summaries",
            "draft_state_log_lines",
            "prompt_save_lines",
        )
    }
    c8["control_repeat"] = {k: ctl2[k] for k in ("turn3", "info", "checkpoints")}
    c8["control_tokens_identical_on_repeat"] = ctl["turn3_tokens"] == ctl2["turn3_tokens"]
    results = {}
    for name, arm in arms.items():
        if "error" in arm:
            rec.add(
                f"8.mtp_save_restore.{name}[{sc}]",
                f"MTP across {name}",
                False,
                explanation=str(arm["error"]),
            )
            continue
        results[name] = compare_arm(ctl, ctl2, arm)
        c8[name] = {
            k: arm[k]
            for k in (
                "turn3",
                "info",
                "checkpoints",
                "draft_state_log_lines",
                "prompt_save_lines",
                "turn_summaries",
            )
        }
    if results.get("slot_files", {}).get("source") == "prompt_cache":
        # the slot-file restore was served by the prompt cache: repeat it with --cache-ram 0
        a0 = run_arm(ctx, "slot_files_cache_ram0", {"cache_ram": 0}, use_probs, "slotfiles0", sc)
        ctl0 = run_arm(ctx, "control_cache_ram0", {"cache_ram": 0}, use_probs, "control0", sc)
        for a in (a0, ctl0):
            if s := a.pop("server", None):
                c8.setdefault("servers", []).append(s)
        if "error" not in a0 and "error" not in ctl0:
            results["slot_files_cache_ram0"] = compare_arm(ctl0, ctl0, a0)
            c8["slot_files_cache_ram0"] = {
                k: a0[k] for k in ("turn3", "info", "draft_state_log_lines")
            }
    c8["results"] = results
    c8["checkpoints_created_anywhere"] = max(
        (a["checkpoints"]["created"] for a in (ctl, ctl2, *arms.values()) if "checkpoints" in a),
        default=None,
    )
    for name, res in results.items():
        valid = res["restore_exercised"] and res["tokens_vs_control"]["verdict"] in (
            "identical",
            "near_tie",
        )
        expl = None
        if not valid:
            expl = (
                f"restore exercised: {res['restore_exercised']} (cache_n {res['cache_n']} of "
                f"{res['prefix_tokens']} prefix tokens, source {res['source']}); "
                f"tokens vs control: "
                f"{res['tokens_vs_control']['verdict']} ({res['tokens_vs_control']['reason']})"
            )
        rec.add(
            f"8.mtp_save_restore.{name}[{sc}]",
            f"MTP draft state across {name.replace('_', ' ')} ({sc} history)",
            valid,
            {"draft_length": 2, "np": 1, "ctx": 65536, "scenario": sc},
            res["turn3"],
            {
                "source_of_prefix": res["source"],
                "prefix_tokens": res["prefix_tokens"],
                "tokens_vs_control": res["tokens_vs_control"]["verdict"],
                "draft_state": res["draft"],
                "FINDING": res["draft"]["verdict"],
            },
            explanation=expl,
        )
    return c8


# --------------------------------------------------------------------------------- phase D, E


def phase_d(ctx: dict) -> dict:
    rec = Recorder("D")
    with Server("D", "mtp-np2", mtp_overrides(2, parallel=2), ctx["scratch"], ctx["stamp"]) as srv:
        info: dict = {"launch_rc": srv.launch_rc, "started": srv.started}
        if not srv.started:
            log = srv.log() if srv.log_path.exists() else ""
            msgs = [
                ln
                for ln in log.splitlines()
                if re.search(r" (E|W) |error|not support|fail", ln, re.I)
            ]
            info["rejected"] = True
            info["messages"] = msgs[-8:]
            info["launch_output_tail"] = excerpt(srv.launch_output, 800)
            exit_f = srv.run_dir / "exit-code"
            info["exit_code"] = exit_f.read_text().strip() if exit_f.exists() else None
        else:
            info["rejected"] = False
            props = srv.get("/props").json()
            info["total_slots"] = props.get("total_slots")
            prompts = [
                chatml(nonce() + "x", f"Write a haiku about {t}.", False) for t in ("sea", "sun")
            ]
            outs = []
            for prompt in prompts:  # one at a time
                r = srv.completion(prompt, 48, cache_prompt=False, **GREEDY)
                outs.append(timings_of(r))
            info["sequential_requests"] = outs
            with ThreadPoolExecutor(max_workers=2) as pool:  # both slots busy at once
                futs = [
                    pool.submit(srv.completion, p, 128, cache_prompt=False, **GREEDY)
                    for p in prompts
                ]
                info["concurrent_requests"] = [timings_of(f.result()) for f in futs]
            slots = srv.get("/slots").json()
            info["slots_listing"] = [
                {k: sl.get(k) for k in ("id", "n_ctx", "is_processing")} for sl in slots
            ]
            info["placement"] = parsers.parse_fit_placement(srv.log())
            info["spec_stats_log"] = parsers.parse_spec_stats(srv.log())[-4:]
            info["vram_after_requests"] = vram_mib()
    rec.add(
        "7.mtp.np2",
        "MTP with -np 2: record whether the server rejects it",
        True,
        {"spec_type": "draft-mtp", "spec_draft_n_max": 2, "parallel": 2},
        info,
        {"note": "observation only; not a pass/fail of the server"},
    )
    return {"checks": rec.checks, "servers": [srv.record()], "phase_d": info}


def cmoe_overrides(**extra) -> dict:
    return {"fit": None, "cpu_moe": True, "moe_cache_mib": 4096, "slot_save_path": None} | extra


def decode_arm(ctx: dict, label: str, lv: int | None, reps: int = 3) -> dict:
    ov = cmoe_overrides(log_verbosity=lv)
    with Server("E", f"ab-{label}", ov, ctx["scratch"], ctx["stamp"]) as srv:
        if not srv.started:
            return {"label": label, "error": srv.launch_output, "server": srv.record()}
        prompts = build_code_prompts(srv, ctx["llama_commit"])
        srv.completion(prompts[0]["prompt"], 64, cache_prompt=False, **GREEDY)  # warm-up, discarded
        speeds = []
        for k in range(reps):
            r = srv.completion(prompts[k % 3]["prompt"], 256, cache_prompt=False, **GREEDY)
            t = timings_of(r)
            speeds.append(
                {
                    "prompt": prompts[k % 3]["recipe"]["file"],
                    "predicted_n": t["predicted_n"],
                    "tg_per_s": t["predicted_per_second"],
                    "pp_per_s": t["prompt_per_second"],
                }
            )
        vals = [s["tg_per_s"] for s in speeds]
        out = {
            "label": label,
            "log_verbosity": lv,
            "reps": speeds,
            "mean": statistics.mean(vals),
            "min": min(vals),
            "max": max(vals),
        }
    out["stats_in_log"] = parsers.parse_moe_cache_stats(srv.log())
    out["server"] = srv.record()
    return out


def phase_e(ctx: dict) -> dict:
    rec = Recorder("E")
    servers = []
    data: dict = {}
    with Server(
        "E", "cmoe-lv4", cmoe_overrides(log_verbosity=4), ctx["scratch"], ctx["stamp"]
    ) as srv:
        servers.append(srv)
        if not srv.started:
            rec.add(
                "9.moe_cache.start",
                "-cmoe --moe-cache-mib 4096 -lv 4 starts",
                False,
                explanation=srv.launch_output,
            )
            return {"checks": rec.checks, "servers": [srv.record()]}
        prompts = build_code_prompts(srv, ctx["llama_commit"])
        data["workload"] = [p["recipe"] for p in prompts]
        data["requests"] = []
        for p in prompts:
            r = srv.completion(p["prompt"], 128, cache_prompt=False, **GREEDY)
            data["requests"].append(timings_of(r))
        data["placement"] = parsers.parse_fit_placement(srv.log())
        srv.vram["after_requests"] = vram_mib()
    stats = parsers.parse_moe_cache_stats(srv.log())
    data["stats"] = stats
    rec.add(
        "9.moe_cache.stats_line",
        "expert-cache statistics line present after a clean SIGINT stop and parses",
        stats["present"] and (srv.stop_status or {}).get("method") == "sigint",
        {"flags": "-cmoe --moe-cache-mib 4096 -lv 4", "requests": 3},
        {
            "classes": stats["classes"],
            "overall_hit_rate_pct": stats["overall_hit_rate_pct"],
            "large_batch_copies": stats.get("large_batch_copies"),
            "config": stats.get("config"),
        },
        {"stop": srv.stop_status},
        explanation="no 'llama_moe_cache: ... hit rate' line in the log after shutdown",
    )
    # -lv 4 A/B (3 repetitions per arm)
    a = decode_arm(ctx, "lv4", 4)
    b = decode_arm(ctx, "default", None)
    ab: dict = {"arms": {"lv4": a, "default": b}, "order": ["lv4", "default"]}
    for arm in (a, b):
        s = arm.pop("server", None)
        if s:
            servers_rec = s
            data.setdefault("ab_servers", []).append(servers_rec)
    if "error" in a or "error" in b:
        rec.add(
            "9.lv4_ab",
            "-lv 4 decode-speed A/B",
            False,
            explanation=str(a.get("error") or b.get("error")),
        )
    else:
        diff = (a["mean"] - b["mean"]) / b["mean"] * 100
        spread = max(a["max"] - a["min"], b["max"] - b["min"])
        ab["difference_pct_lv4_vs_default"] = round(diff, 2)
        ab["within_arm_spread_tok_s"] = round(spread, 3)
        if abs(a["mean"] - b["mean"]) > spread:
            b2 = decode_arm(ctx, "default-first", None)
            a2 = decode_arm(ctx, "lv4-second", 4)
            for arm in (a2, b2):
                s = arm.pop("server", None)
                if s:
                    data.setdefault("ab_servers", []).append(s)
            ab["reversed_order"] = {"default": b2, "lv4": a2}
            if "error" not in a2 and "error" not in b2:
                ab["reversed_difference_pct_lv4_vs_default"] = round(
                    (a2["mean"] - b2["mean"]) / b2["mean"] * 100, 2
                )
        ab["stats_line_at_default_level"] = b["stats_in_log"]["present"]
        rec.add(
            "9.lv4_ab",
            "-lv 4 versus default log level: decode speed A/B (3 repetitions per arm)",
            True,
            {"config": "-cmoe --moe-cache-mib 4096", "reps": 3, "n_predict": 256},
            {
                "lv4_mean_tok_s": round(a["mean"], 2),
                "default_mean_tok_s": round(b["mean"], 2),
                "difference_pct": ab["difference_pct_lv4_vs_default"],
                "stats_line_at_default_level": ab["stats_line_at_default_level"],
            },
            {"reversed_order_difference_pct": ab.get("reversed_difference_pct_lv4_vs_default")},
        )
    data["lv4_ab"] = ab
    return {"checks": rec.checks, "servers": [s.record() for s in servers], "phase_e": data}


PHASES = {"A": phase_a, "B": phase_b, "C": phase_c, "D": phase_d, "E": phase_e}

# --------------------------------------------------------------------------------- orchestration


def cleanup() -> dict:
    removed = []
    for p in sorted(Path("/dev/shm").glob("local-ai-research-*")):
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
        removed.append(p.name)
    left = sorted(p.name for p in Path("/dev/shm").glob("local-ai-research-*"))
    return {"removed": removed, "left": left, "servers_running": llama_server_processes()}


def preconditions() -> dict:
    mem = meminfo()
    return {
        "llama_server_running": llama_server_processes(),
        "vram_used_mib": vram_mib(),
        "memavailable_mib": mem.get("MemAvailable_mib"),
        "loadavg_1m": float(Path("/proc/loadavg").read_text().split()[0]),
        "gpu_lock_held_by_wrapper": os.environ.get("SMALLPC_GPU_LOCK_HELD"),
        "dev_shm_entries": sorted(p.name for p in Path("/dev/shm").glob("local-ai-research-*")),
    }


def paired_ab(ab: dict) -> dict:
    """Per-prompt (paired) decode-speed difference of the -lv 4 arm against the default arm."""
    a, b = ab["arms"]["lv4"], ab["arms"]["default"]
    pairs = [
        {
            "prompt": x["prompt"],
            "lv4_tok_s": round(x["tg_per_s"], 2),
            "default_tok_s": round(y["tg_per_s"], 2),
            "difference_pct": round((x["tg_per_s"] - y["tg_per_s"]) / y["tg_per_s"] * 100, 2),
        }
        for x, y in zip(a["reps"], b["reps"], strict=True)
    ]
    diffs = [p["difference_pct"] for p in pairs]
    return {"pairs": pairs, "mean_difference_pct": round(statistics.mean(diffs), 2)}


# Lines worth keeping as parser test fixtures, per server (substring patterns).
FIXTURES = {
    "startup-health64k.txt": (
        "-A-health64k",
        None,  # everything except metadata dumps, see _fixture_lines
    ),
    "startup-mtp-d2.txt": (
        "-C-mtp-d2",
        (
            "common_fit",
            "common_params_fit",
            "load_tensors",
            "llama_context",
            "llama_kv_cache",
            "llama_memory_recurrent",
            "sched_reserve",
            "common_speculative",
            "spec ",
            "load_model",
            "offloaded",
        ),
    ),
    "moe-cache-stats.txt": (
        "-E-cmoe-lv4",
        ("llama_moe_cache", "MoE cache", "load_tensors:", "tensor overrides"),
    ),
    "cache-source-prompt-cache.txt": (
        "-C-short-promptcache",
        (
            "prompt_save",
            "better prompt",
            "updating prompt cache",
            "prompt cache update",
            "checkpoint",
            "draft acceptance",
            "statistics",
            "update:",
        ),
    ),
    "cache-source-slot-restore.txt": (
        "-C-short-slotfiles",
        ("load_slot_dr", "restored", "draft acceptance", "statistics", "checkpoint"),
    ),
}


def _fixture_lines(log: str, patterns: tuple | None, limit: int = 260) -> list[str]:
    lines = log.splitlines()
    if patterns is None:
        skip = ("unused tensor", "llama_model_loader: - ", "print_info: ", "load: ")
        lines = [
            ln for ln in lines if not any(k in ln for k in skip) and "common_init_: added" not in ln
        ]
    else:
        lines = [ln for ln in lines if any(k in ln for k in patterns)]
    return lines[:limit]


def export_fixtures(stamp_prefix: str, out_dir: Path) -> list[str]:
    """Write scrubbed log excerpts (home paths -> ``~``) from this run's server logs."""
    home = str(Path.home())
    user = os.environ.get("USER", "")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (needle, patterns) in FIXTURES.items():
        dirs = sorted((ROOT / "data/logs").glob(f"health-{stamp_prefix}*{needle}"))
        if not dirs:
            continue
        log = (dirs[-1] / "server.log").read_text(errors="replace")
        text = "\n".join(_fixture_lines(log, patterns)) + "\n"
        head = (
            f"# excerpt of a real llama-server b12208 log ({needle.strip('-')}), home paths as ~\n"
        )
        (out_dir / name).write_text(
            head + parsers.scrub_log(text, home, (user,) if len(user) > 3 else ())
        )
        written.append(name)
    return written


def aggregate(run_dir: Path, date: str, env: dict) -> dict:
    checks, servers, sections = [], [], {}
    for f in sorted(run_dir.glob("phase-*.json")):
        d = json.loads(f.read_text())
        checks += d.pop("checks", [])
        servers += d.pop("servers", [])
        for k, v in d.items():
            sections[k] = v
    counts = {
        "PASS": sum(c["status"] == "PASS" for c in checks),
        "FAIL": sum(c["status"] == "FAIL" for c in checks),
    }
    a = sections.get("phase_a", {})
    b = sections.get("phase_b", {})
    if (ab := sections.get("phase_e", {}).get("lv4_ab")) and "error" not in ab["arms"]["lv4"]:
        ab["paired"] = paired_ab(ab)
    return {
        "schema": 1,
        "date_utc": date,
        "generated_utc": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plan": "docs/plans/step-0-baseline.md WP5",
        "build": a.get("props", {}).get("build_info"),
        "model": {"file": load_model().file, "sha256": load_model().sha256},
        "chat_template_decision": "embedded GGUF template in every stage (docs/decisions.md)",
        "environment": env,
        "summary": {
            "counts": counts,
            "s4a_acceptance_d1_greedy": (b.get("acceptance_greedy") or {}).get("acceptance"),
            "s4a": "PASS" if sections.get("s4a_pass") else "FAIL",
            "failed_checks": [c["id"] for c in checks if c["status"] == "FAIL"],
        },
        "checks": checks,
        "servers": servers,
    } | {k: v for k, v in sections.items() if k.startswith("phase_")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m smallpc.health", description=__doc__.split("\n")[0]
    )
    ap.add_argument("--phases", default="A,B,C,D,E", help="comma-separated, run in this order")
    ap.add_argument("--run-dir", type=Path, help="reuse a run directory (phase results are kept)")
    ap.add_argument("--no-aggregate", action="store_true")
    ap.add_argument("--export-fixtures", metavar="STAMP_PREFIX", help="write log fixtures and exit")
    args = ap.parse_args(argv)

    if args.export_fixtures:
        names = export_fixtures(args.export_fixtures, ROOT / "tests/fixtures/logs")
        print("wrote fixtures:", ", ".join(names))
        return 0
    if not os.environ.get("SMALLPC_GPU_LOCK_HELD"):
        print("health: run through scripts/healthcheck.sh (GPU lock not held)", file=sys.stderr)
        return 75
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.run_dir or (ROOT / "data/logs" / f"health-{stamp}")
    run_dir.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="smallpc-health-", dir="/tmp"))
    env = preconditions()
    print(json.dumps(env), flush=True)
    if env["llama_server_running"]:
        print("health: a llama-server is already running", file=sys.stderr)
        return 1
    build = json.loads((ROOT / "data/env/build-info.json").read_text())
    ctx = {"scratch": scratch, "stamp": stamp, "llama_commit": build["commit"], "phases": {}}
    for f in run_dir.glob("phase-*.json"):
        ctx["phases"][f.stem.split("-")[1]] = json.loads(f.read_text())
    stop = False
    try:
        for name in args.phases.split(","):
            if stop:
                break
            print(f"=== phase {name} ===", flush=True)
            try:
                res = PHASES[name](ctx)
            except Exception:
                tb = traceback.format_exc()
                print(tb, file=sys.stderr)
                rec = Recorder(name)
                rec.add(
                    f"{name}.error",
                    f"phase {name} completed without a harness error",
                    False,
                    explanation=tb[-1500:],
                )
                res = {"checks": rec.checks, "servers": []}
            ctx["phases"][name] = res
            (run_dir / f"phase-{name}.json").write_text(json.dumps(res, indent=1, default=str))
            if name == "B" and not res.get("s4a_pass"):
                print("S4(a) FAILED: stopping after phase B", flush=True)
                stop = True
    finally:
        env["cleanup"] = cleanup()
        shutil.rmtree(scratch, ignore_errors=True)
        env["after"] = preconditions()
    if not args.no_aggregate:
        date = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
        doc = aggregate(run_dir, date, env)
        out = ROOT / f"data/health/endpoints-{date}.json"
        out.write_text(json.dumps(doc, indent=2, default=str) + "\n")
        print(
            f"wrote {out}  PASS={doc['summary']['counts']['PASS']} "
            f"FAIL={doc['summary']['counts']['FAIL']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
