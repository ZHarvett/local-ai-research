"""Per-request pattern of a harness run, from the llama-server log (WP7).

    python -m smallpc.requests --server-log LOG --harness opencode|dsh [--harness-log FILE]
        [--events FILE] [--run-id ID] [--out FILE]

The numbers are those llama-server prints per request (``print_timing``, "new prompt"), the same
values it returns as ``timings``; the harness consumes the response stream, so the response itself
is not visible to us. They are **smoke-task data**: they show how a harness behaves on a tiny
task, not what real agent turns look like (step plan 3.4).

Classification of main-loop vs auxiliary requests (a title request is the known one):

* OpenCode: its debug log marks every model call (``stream ... small=true agent=title`` vs
  ``small=false agent=build``); the k-th call is matched to the k-th server task by arrival order,
  and cross-checked against prompt size (auxiliary prompts are tiny).
* dsh: the JSON events give the number of main-loop steps; the requests with the smallest prompts
  beyond that count are auxiliary (verified on the scripted probe: a title request has no tools).
* Anything that cannot be classified is reported as ``unclassified``.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LABEL = "smoke-task data, not representative of real agent turns"
_TASK = r"slot\s+[^:|]+:\s+id\s+(\d+)\s+\|\s+task\s+(-?\d+)\s+\|\s+"
_NEW = re.compile(_TASK + r"new prompt, n_ctx_slot = (\d+), n_keep = \d+, task\.n_tokens = (\d+)")
_PROMPT = re.compile(_TASK + r"prompt eval time =\s*([\d.]+) ms /\s*(\d+) tokens")
_EVAL = re.compile(_TASK + r"\s*eval time =\s*([\d.]+) ms /\s*(\d+) tokens")
_TOTAL = re.compile(_TASK + r"\s*total time =\s*([\d.]+) ms /\s*(\d+) tokens")
_REL = re.compile(_TASK + r"stop processing: n_tokens = (\d+), truncated = (\d)")
_OC_STREAM = re.compile(
    r"message=stream providerID=(\S+) modelID=(\S+) session\.id=(\S+) small=(true|false) "
    r"agent=(\S+) mode=(\S+)"
)


def parse_server_requests(log: str) -> list[dict]:
    """One record per finished request, in task-id order (arrival order)."""
    tasks: dict[int, dict] = {}
    for line in log.splitlines():
        if m := _NEW.search(line):
            tasks.setdefault(int(m[2]), {})["prompt_total"] = int(m[4])
            tasks[int(m[2])]["n_ctx_slot"] = int(m[3])
        elif m := _PROMPT.search(line):
            t = tasks.setdefault(int(m[2]), {})
            t["prompt_ms"], t["prompt_n"] = float(m[3]), int(m[4])
        elif m := _EVAL.search(line):
            t = tasks.setdefault(int(m[2]), {})
            t["predicted_ms"], t["predicted_n"] = float(m[3]), int(m[4])
        elif m := _TOTAL.search(line):
            tasks.setdefault(int(m[2]), {})["total_ms"] = float(m[3])
        elif m := _REL.search(line):
            t = tasks.setdefault(int(m[2]), {})
            t["slot"], t["truncated"] = int(m[1]), bool(int(m[4]))
    out = []
    for task_id in sorted(k for k in tasks if k >= 0):
        t = tasks[task_id]
        if "prompt_n" not in t or "total_ms" not in t:
            continue  # request not finished (or an internal task without timings)
        total = t.get("prompt_total")
        out.append(
            {
                "task": task_id,
                "slot": t.get("slot"),
                "prompt_n": t["prompt_n"],
                "cache_n": total - t["prompt_n"] if total is not None else None,
                "prompt_total": total,
                # llama-server reports one generated token for an n_predict 0 request; keep as is
                "predicted_n": t.get("predicted_n", 0),
                "prompt_ms": t["prompt_ms"],
                "predicted_ms": t.get("predicted_ms", 0.0),
                "time_ms": t["total_ms"],
                "truncated": t.get("truncated"),
            }
        )
    return out


def opencode_calls(harness_log: str) -> list[dict]:
    return [
        {"provider": m[1], "model": m[2], "session": m[3], "small": m[4] == "true", "agent": m[5]}
        for m in _OC_STREAM.finditer(harness_log)
    ]


def classify(requests: list[dict], harness: str, calls: list[dict] | None, main_steps: int | None):
    """Add ``kind`` (main/auxiliary/unclassified) and ``classified_by`` to each request."""
    reqs = [dict(r) for r in requests]
    if harness == "opencode" and calls and len(calls) == len(reqs):
        for r, c in zip(reqs, calls, strict=True):
            r["kind"] = "auxiliary" if c["small"] else "main"
            r["agent"] = c["agent"]
            r["classified_by"] = "opencode debug log (k-th model call = k-th server task)"
    elif harness == "dsh" and main_steps is not None and 0 < main_steps <= len(reqs):
        by_size = sorted(reqs, key=lambda r: r["prompt_total"] or 0, reverse=True)
        main = {id(r) for r in by_size[:main_steps]}
        for r in reqs:
            r["kind"] = "main" if id(r) in main else "auxiliary"
            r["classified_by"] = (
                f"{main_steps} main-loop steps from the JSON events; the {main_steps} largest "
                "prompts are main, the rest auxiliary"
            )
    else:
        for r in reqs:
            r["kind"] = "unclassified"
            r["classified_by"] = "no usable harness log or event count"
    return reqs


def size_cross_check(reqs: list[dict]) -> dict:
    """Do the classes separate by prompt size? (auxiliary prompts are tiny next to main ones)."""
    main = [r["prompt_total"] for r in reqs if r["kind"] == "main" and r["prompt_total"]]
    aux = [r["prompt_total"] for r in reqs if r["kind"] == "auxiliary" and r["prompt_total"]]
    ok = bool(main and aux) and max(aux) < min(main)
    return {
        "main_min_prompt_tokens": min(main) if main else None,
        "auxiliary_max_prompt_tokens": max(aux) if aux else None,
        "classes_separate_by_prompt_size": ok if (main and aux) else None,
    }


def totals(reqs: list[dict]) -> dict:
    def agg(rs):
        return {
            "requests": len(rs),
            "prompt_n": sum(r["prompt_n"] for r in rs),
            "cache_n": sum(r["cache_n"] or 0 for r in rs),
            "predicted_n": sum(r["predicted_n"] for r in rs),
            "time_ms": round(sum(r["time_ms"] for r in rs), 2),
        }

    return {
        "all": agg(reqs),
        "main": agg([r for r in reqs if r["kind"] == "main"]),
        "auxiliary": agg([r for r in reqs if r["kind"] == "auxiliary"]),
        "unclassified": agg([r for r in reqs if r["kind"] == "unclassified"]),
    }


def build_pattern(
    run_id: str,
    harness: str,
    server_log: str,
    harness_log: str = "",
    main_steps: int | None = None,
) -> dict:
    reqs = parse_server_requests(server_log)
    calls = opencode_calls(harness_log) if harness == "opencode" else None
    reqs = classify(reqs, harness, calls, main_steps)
    for i, r in enumerate(reqs, 1):
        r["order"] = i
    main = [r for r in reqs if r["kind"] == "main"]
    # a "turn" is the whole harness run for the one smoke prompt: the user message until the final
    # answer. It contains many main-loop requests (steps) plus any auxiliary ones.
    return {
        "label": LABEL,
        "run_id": run_id,
        "harness": harness,
        "requests": reqs,
        "turn_definition": (
            "one turn = the single smoke prompt, from the user message to the final answer; "
            "it holds the main-loop requests (one per step) and any auxiliary requests"
        ),
        "per_turn": {
            "turns": 1,
            "requests_per_turn": len(reqs),
            "main_requests_per_turn": len(main),
            "auxiliary_requests_per_turn": len([r for r in reqs if r["kind"] == "auxiliary"]),
            "totals": totals(reqs),
        },
        "classification": size_cross_check(reqs),
        "any_request_truncated": any(r["truncated"] for r in reqs),
        "source": "llama-server log (print_timing, new prompt); cache_n = task.n_tokens - prompt_n",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.requests")
    ap.add_argument("--server-log", required=True)
    ap.add_argument("--harness", choices=["opencode", "dsh"], required=True)
    ap.add_argument("--harness-log", help="OpenCode debug log (stderr of --print-logs)")
    ap.add_argument("--main-steps", type=int, help="dsh: main-loop steps from the JSON events")
    ap.add_argument("--run-id", default="run")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    pattern = build_pattern(
        a.run_id,
        a.harness,
        Path(a.server_log).read_text(errors="replace"),
        Path(a.harness_log).read_text(errors="replace") if a.harness_log else "",
        a.main_steps,
    )
    text = json.dumps(pattern, indent=2) + "\n"
    if a.out:
        Path(a.out).write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
