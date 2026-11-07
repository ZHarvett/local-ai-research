#!/usr/bin/env python3
"""Stand-in for llama-server in launch/stop tests. Understands --host/--port, ignores the rest.

FAKE_LOAD_DELAY=<s>   /health answers 503 for this long first
FAKE_IGNORE_SIGINT=1  ignore SIGINT (forces stop-server.sh to fall back to SIGKILL)
FAKE_EXIT_AT_START=N  exit immediately with code N
"""

import os
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

args = sys.argv[1:]
host = args[args.index("--host") + 1]
port = int(args[args.index("--port") + 1])
if "FAKE_EXIT_AT_START" in os.environ:
    print("fake server: failing at start", flush=True)
    sys.exit(int(os.environ["FAKE_EXIT_AT_START"]))

ready_at = time.monotonic() + float(os.environ.get("FAKE_LOAD_DELAY", "0"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ok = self.path == "/health" and time.monotonic() >= ready_at
        self.send_response(200 if ok else 503)
        self.end_headers()

    def log_message(self, *a):
        pass


def on_sigint(*_):
    print("fake server: SIGINT, shutting down", flush=True)
    sys.exit(0)


signal.signal(signal.SIGINT, signal.SIG_IGN if os.environ.get("FAKE_IGNORE_SIGINT") else on_sigint)
print(f"fake server: listening on {host}:{port}; argv={args}", flush=True)
HTTPServer((host, port), Handler).serve_forever()
