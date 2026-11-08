#!/usr/bin/env python3
"""Scripted OpenAI-compatible endpoint for harness tests: no model, no GPU, 127.0.0.1 only.

    fake_openai_server.py --port-file FILE --script SCRIPT.json [--model NAME]

The script is a JSON list; the n-th /v1/chat/completions request is answered with its n-th entry
(the last entry repeats). Each entry is {"text": "..."} or {"tool": "bash", "args": {...}}.
Requests that carry no tools (title generation and similar) get a fixed text answer and do not
consume a script entry. Every request body is appended to ``<script>.requests.jsonl``, so a
test can see what was asked.
GET /v1/models returns the model; GET /health returns 200.
"""

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--port-file", required=True)
ap.add_argument("--script", required=True)
ap.add_argument("--model", default="fake-model")
ap.add_argument("--delay", type=float, default=0.0, help="seconds to wait before answering")
args = ap.parse_args()
SCRIPT = json.loads(Path(args.script).read_text())
LOG = Path(args.script + ".requests.jsonl")
LOCK = threading.Lock()
COUNT = [0]


def chunk(delta, finish=None, usage=None):
    c = {
        "id": "chatcmpl-fake",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": args.model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    if usage:
        c["usage"] = usage
    return c


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") == "/v1/models":
            self._json({"object": "list", "data": [{"id": args.model, "object": "model"}]})
        elif self.path.rstrip("/") == "/props":
            self._json(
                {
                    "total_slots": 1,
                    "model_path": "fake.gguf",
                    "default_generation_settings": {"n_ctx": 65536},
                }
            )
        else:
            self._json({"status": "ok"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        aux = not body.get("tools")  # requests without tools are auxiliary (e.g. a title)
        with LOCK:
            n = COUNT[0]
            COUNT[0] += 0 if aux else 1
            with LOG.open("a") as f:
                f.write(json.dumps(body) + "\n")
        time.sleep(args.delay)
        step = {"text": "Smoke probe"} if aux else SCRIPT[min(n, len(SCRIPT) - 1)]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        out = [chunk({"role": "assistant", "content": ""})]
        if "tool" in step:
            call = {
                "index": 0,
                "id": f"call_{n}",
                "type": "function",
                "function": {"name": step["tool"], "arguments": json.dumps(step["args"])},
            }
            out.append(chunk({"tool_calls": [call]}))
            finish = "tool_calls"
        else:
            out.append(chunk({"content": step["text"]}))
            finish = "stop"
        out.append(chunk({}, finish))
        out.append(
            chunk({}, None, {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
        )
        for c in out:
            self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
Path(args.port_file).write_text(f"{srv.server_address[1]}\n")
srv.serve_forever()
