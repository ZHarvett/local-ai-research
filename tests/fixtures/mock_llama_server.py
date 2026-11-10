#!/usr/bin/env python3
"""A mock llama-server for the sweep tests. launch-server.sh starts it through a test-only machine
config (``llama_server = ".../mock_llama_server.py"``); the real configs/machine.toml is untouched.

It understands the rendered argv (``--host --port -c -ub -np --fit --n-cpu-moe -cmoe
--moe-cache-mib --spec-type``), writes a startup log with the lines the parsers read, and serves
``/health``, ``/props`` and ``/completion`` (plain and streaming) with timings shaped like the WP8
live check (prefill 770-880 tokens/s, decode 50-85 tokens/s, falling with depth).

The prefix cache is real: every slot remembers its token sequence, a request is served by the slot
with the longest common prefix, and ``cache_n`` is that prefix (llama-server always re-evaluates
the last token, so a fully cached prompt reports ``cache_n = n - 1``). Request A with
``n_predict`` 0 reports one generated token, as the pinned build does.

Misbehaviour comes from the ``MOCK_BEHAVIOR`` environment variable (JSON). Each entry may carry
``"on": [indices]``, the zero-based indices among requests of that class (A = n_predict 0,
B = streaming, F = any other); without ``on`` it applies to all of them:

    warm_prefill_A   {"cache_n": 100}   A reuses 100 tokens of a stale prefix (prompt_n = d - 100)
    cache_miss_B     true               B finds an empty cache (cache_n 0, prompt_n = d + 3000)
    short_gen_B      50                 B stops after 50 tokens
    wrong_accounting 7                  prompt_n is reported 7 too high ({"cls": "A"} limits it)
    oom_at_start     true               prints a CUDA out-of-memory error and exits 1
    crash_after      N                  exits 139 after N completions (once, see crash_marker)
    crash_marker     PATH               file whose existence disables the crash (written on crash)
    slow_s           S                  sleeps S seconds before answering (every request)
    hang_after       N                  after N completions never answers again
    ignore_sigint    true               ignores SIGINT (stop-server.sh must SIGKILL)
    vram_file        PATH               the card's "memory.used" is written here (MiB)
    vram_base_mib    N                  used = base + moe cache + context * vram_per_ctx_mib
    vram_total_mib   N                  above this at start: out-of-memory exit
    vram_per_layer_mib N                used += (40 - n_cpu_moe) * N when --n-cpu-moe is given
    vram_per_draft_mib N                used += draft length * N when --spec-type is given (MTP head
                                        and draft context)
    speed_factor     X                  multiplies prefill and decode speed (a drifting machine)
    n_part           N                  expert layers the fake --fit puts on the CPU (default 17)
    fit_intervene    true               the fake --fit asks to reduce device memory
    no_id_slot       true               responses carry no id_slot
    time_scale       X                  sleep X * simulated seconds per request (default 0)
    output           {"mode": M}        what ``return_tokens`` requests (the sanity check) get back:
                                        healthy (default: pseudo-random token ids that depend only
                                        on the prompt, so two healthy servers agree), loop (one
                                        token forever), short ({"n": N}: stops after N tokens) or
                                        diverge ({"at": I}: healthy until index I, then different)
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BEHAVIOR = json.loads(os.environ.get("MOCK_BEHAVIOR", "{}"))
args = sys.argv[1:]


def arg(flag: str, default=None):
    return args[args.index(flag) + 1] if flag in args else default


host, port = arg("--host", "127.0.0.1"), int(arg("--port"))
n_ctx = int(arg("-c", "4096"))
n_parallel = int(arg("-np", "-1"))
ubatch = int(arg("-ub", "512"))
cache_mib = int(arg("--moe-cache-mib", "0"))
cmoe = "-cmoe" in args
draft_n = int(arg("--spec-draft-n-max", "0"))
n_cpu_moe = arg("--n-cpu-moe")
fit_on = arg("--fit", "on") == "on"
unified = n_parallel in (-1, 0)  # stock: automatic slots, unified KV
n_slots = 4 if n_parallel in (-1, 0) else n_parallel
per_slot = n_ctx if unified else n_ctx // n_slots


def stamp() -> str:
    return f"0.{int(time.monotonic() % 60):02d}.000.000"


def log(msg: str, level: str = "I") -> None:
    print(f"{stamp()} {level} {msg}", flush=True)


def vram_used() -> float:
    return (
        BEHAVIOR.get("vram_base_mib", 6000.0)
        + cache_mib
        + n_ctx * BEHAVIOR.get("vram_per_ctx_mib", 0.02)
        + ((40 - int(n_cpu_moe)) * BEHAVIOR.get("vram_per_layer_mib", 0.0) if n_cpu_moe else 0.0)
        + (draft_n * BEHAVIOR.get("vram_per_draft_mib", 0.0) if "--spec-type" in args else 0.0)
    )


def write_vram(extra: float = 0.0) -> None:
    f = BEHAVIOR.get("vram_file")
    if f:
        tmp = f + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(f"{vram_used() + extra:.1f}\n")
        os.replace(tmp, f)


# ---------------------------------------------------------------------------------- startup
log("srv  llama_server: initializing ...")
if BEHAVIOR.get("oom_at_start") or vram_used() > BEHAVIOR.get("vram_total_mib", 1e9):
    log("ggml_backend_cuda_buffer_type_alloc_buffer: allocating 14000.00 MiB on device 0: "
        "cudaMalloc failed: out of memory", "E")  # fmt: skip
    log("llama_model_load: error loading model: unable to allocate CUDA0 buffer", "E")
    log("srv    load_model: failed to load model", "E")
    sys.exit(1)
if fit_on:
    log("cmn  common_fit_a: fitting params to device memory ...")
    log("common_params_fit_impl: projected to use 12000 MiB of device memory vs. 15803 MiB of free "
        "device memory")  # fmt: skip
    if BEHAVIOR.get("fit_intervene"):
        log("common_params_fit_impl: need to reduce device memory by 600 MiB")
    else:
        log("common_params_fit_impl: will leave 3803 >= 1024 MiB of free device memory, "
            "no changes needed")  # fmt: skip
    n_part = BEHAVIOR.get("n_part", 17)
    log(f"common_params_fit_impl: set ngl_per_device[0].(n_layer, n_part, overflow_type)="
        f"(40, {n_part}, MOE)")  # fmt: skip
    log("common_fit_params: successfully fit params to free device memory")
if cmoe or n_cpu_moe is not None:
    log("llama_model_loader: tensor overrides to CPU are used with mmap enabled", "W")
log("load_tensors: offloaded 42/42 layers to GPU")
log("load_tensors:        CUDA0 model buffer size = 13139.00 MiB")
log("load_tensors:   CPU_Mapped model buffer size = 7557.00 MiB")
log("llama_context: constructing llama_context")
log(f"llama_context: n_seq_max     = {1 if not unified else n_slots}")
log(f"llama_context: n_ctx         = {n_ctx}")
log(f"llama_context: n_ctx_seq     = {per_slot}")
log(f"llama_context: n_ubatch      = {ubatch}")
log(f"llama_context: kv_unified    = {'true' if unified else 'false'}")
log(f"srv    load_model: initializing, n_slots = {n_slots}, n_ctx_slot = {per_slot}, "
    f"kv_unified = '{'true' if unified else 'false'}'")  # fmt: skip
write_vram()


# ---------------------------------------------------------------------------------- the model
lock = threading.Lock()
hung = threading.Event()  # a hung server answers nothing, /health included
slots: list[list[int]] = [[] for _ in range(n_slots)]
last_used = [0] * n_slots
counters = {"A": 0, "B": 0, "F": 0, "all": 0}
tick = [0]


def lcp(a: list[int], b: list[int]) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def applies(name: str, cls: str, idx: int) -> bool:
    v = BEHAVIOR.get(name)
    if v is None or v is False:
        return False
    if isinstance(v, dict) and "on" in v:
        return idx in v["on"]
    return True


def value(name: str, default):
    v = BEHAVIOR.get(name)
    if isinstance(v, dict):
        return v.get("value", v.get("cache_n", default))
    return default if v is True else v


def pp_rate(n: int) -> float:
    return (886.0 - 1.2e-3 * n) * BEHAVIOR.get("speed_factor", 1.0)


def tg_rate(n: int) -> float:
    return (85.0 - 3.5e-4 * n) * BEHAVIOR.get("speed_factor", 1.0)


def gen_tokens(prompt: list[int], n: int) -> list[int]:
    """The token ids a ``return_tokens`` request gets back (see ``output`` in the module doc)."""
    cfg = BEHAVIOR.get("output") or {}
    mode = cfg.get("mode", "healthy")
    seed = hashlib.sha256(json.dumps(prompt).encode()).hexdigest()
    rng = random.Random(seed)
    base = [rng.randrange(1000, 60000) for _ in range(n)]
    if mode == "loop":
        return [7] * n
    if mode == "short":
        return base[: int(cfg.get("n", 30))]
    if mode == "diverge":
        rng2 = random.Random(seed + "-diverge")
        at = int(cfg.get("at", 200))
        return base[:at] + [rng2.randrange(1000, 60000) for _ in range(max(n - at, 0))]
    return base


def serve(body: dict) -> dict:
    prompt = body["prompt"]
    n_predict = body.get("n_predict", -1)
    cls = "A" if n_predict == 0 else ("B" if body.get("stream") else "F")
    with lock:
        counters["all"] += 1
        idx = counters[cls]
        counters[cls] += 1
        # slot choice: longest common prefix, else the least recently used
        best, best_n = 0, -1
        for i, s in enumerate(slots):
            n = lcp(prompt, s)
            if n > best_n or (n == best_n and last_used[i] < last_used[best]):
                best, best_n = i, n
        cache_n = best_n if body.get("cache_prompt", True) else 0
        if cache_n >= len(prompt):
            cache_n = len(prompt) - 1  # the last token is always evaluated
        if cls == "A" and BEHAVIOR.get("warm_prefill_A") and applies("warm_prefill_A", "A", idx):
            cache_n = max(cache_n, int(value("warm_prefill_A", 100)))
        if cls == "B" and applies("cache_miss_B", "B", idx):
            cache_n = 0
        prompt_n = len(prompt) - cache_n
        pn = n_predict if n_predict >= 0 else 400
        predicted_n = 1 if n_predict == 0 else pn
        stop_type = "limit"
        if (
            cls == "B"
            and BEHAVIOR.get("short_gen_B") is not None
            and applies("short_gen_B", "B", idx)
        ):
            predicted_n, stop_type = int(value("short_gen_B", 50)), "eos"
        out_tokens = None
        if body.get("return_tokens") and n_predict != 0:
            out_tokens = gen_tokens(prompt, pn)
            predicted_n = len(out_tokens)
            if predicted_n < pn:
                stop_type = "eos"
        slots[best] = list(prompt) + [-1] * predicted_n  # generated tokens never match a prompt
        tick[0] += 1
        last_used[best] = tick[0]
        shown_prompt_n = prompt_n
        wa = BEHAVIOR.get("wrong_accounting")
        if (
            wa
            and (not isinstance(wa, dict) or wa.get("cls", cls) == cls)
            and applies("wrong_accounting", cls, idx)
        ):
            shown_prompt_n += int(value("wrong_accounting", 7))
    prompt_ms = prompt_n / pp_rate(len(prompt)) * 1000
    predicted_ms = predicted_n / tg_rate(len(prompt)) * 1000
    timings = {
        "cache_n": cache_n,
        "prompt_n": shown_prompt_n,
        "prompt_ms": round(prompt_ms, 3),
        "prompt_per_token_ms": round(prompt_ms / max(prompt_n, 1), 4),
        "prompt_per_second": round(prompt_n / max(prompt_ms, 1e-9) * 1000, 3),
        "predicted_n": predicted_n,
        "predicted_ms": round(predicted_ms, 3),
        "predicted_per_token_ms": round(predicted_ms / max(predicted_n, 1), 4),
        "predicted_per_second": round(predicted_n / max(predicted_ms, 1e-9) * 1000, 3),
    }
    if "--spec-type" in args:
        timings |= {"draft_n": predicted_n // 2, "draft_n_accepted": predicted_n // 3}
    resp = {
        "stop": True,
        "stop_type": stop_type,
        "truncated": False,
        "tokens_evaluated": len(prompt),
        "tokens_cached": len(prompt) + predicted_n - 1,
        "timings": timings,
        "content": "",
    }
    if out_tokens is not None:
        resp["tokens"] = out_tokens
    if not BEHAVIOR.get("no_id_slot"):
        resp["id_slot"] = best
    sim_s = (prompt_ms + predicted_ms) / 1000
    return {"resp": resp, "sim_s": sim_s, "cls": cls, "idx": idx, "predicted_n": predicted_n}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if hung.is_set():
            time.sleep(10**6)
        if self.path == "/health":
            self._json({"status": "ok"})
        elif self.path == "/props":
            self._json({
                "build_info": "mock-b0",
                "total_slots": n_slots,
                "default_generation_settings": {"n_ctx": per_slot},
                "endpoints": {"endpoint_slots": True},
            })  # fmt: skip
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/completion":
            return self._json({"error": "not found"}, 404)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        n_done = counters["all"]
        if BEHAVIOR.get("hang_after") is not None and n_done >= BEHAVIOR["hang_after"]:
            hung.set()
            time.sleep(10**6)
        if BEHAVIOR.get("slow_s"):
            time.sleep(BEHAVIOR["slow_s"])
        marker = BEHAVIOR.get("crash_marker")
        crash_at = BEHAVIOR.get("crash_after")
        if crash_at is not None and n_done >= crash_at and not (marker and os.path.exists(marker)):
            if marker:
                with open(marker, "w") as mf:
                    mf.write("crashed\n")
            log("srv  CUDA error: an illegal memory access was encountered", "E")
            os._exit(139)
        r = serve(body)
        scale = BEHAVIOR.get("time_scale", 0.0)
        if scale:
            time.sleep(r["sim_s"] * scale)
        write_vram(extra=BEHAVIOR.get("vram_request_extra_mib", 0.0))
        resp = r["resp"]
        if not body.get("stream"):
            return self._json(resp)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        n_chunks = max(1, min(r["predicted_n"], 8))
        for i in range(n_chunks):
            chunk = {"content": f"tok{i} ", "stop": False}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(f"data: {json.dumps(resp)}\n\n".encode())
        self.wfile.flush()


def on_sigint(*_):
    if cache_mib:
        log("llama_moe_cache: ubatch <= 8: hits = 83621, misses = 41364 (0 on the CPU), "
            "hit rate = 66.90%, uploaded = 75560.51 MiB")  # fmt: skip
        log("llama_moe_cache: large batches: 115236 experts copied from the cache, 69520.69 MiB")
    log("srv  mock server: SIGINT, shutting down")
    os._exit(0)


signal.signal(signal.SIGINT, signal.SIG_IGN if BEHAVIOR.get("ignore_sigint") else on_sigint)
log(f"srv  server_on_li: listening on http://{host}:{port}")
log("srv  update_slots: all slots are idle")
ThreadingHTTPServer((host, port), Handler).serve_forever()
