"""Logging HTTP/HTTPS proxy that denies (or allowlists) outbound connections (WP7 discovery).

    python -m smallpc.netproxy --log FILE [--port N] [--allow HOST ...]

Every CONNECT (HTTPS) and absolute-URI HTTP request is logged as one JSON line with its host, port
and decision. Hosts not on the allowlist get ``403`` and nothing is forwarded; with no ``--allow``
the proxy denies everything, so a harness run through it cannot send anything out. Only the host
name and port of a request are seen, never the content of a TLS stream.

A proxy only sees traffic whose client honours ``HTTP(S)_PROXY``. Traffic that ignores the
settings is invisible to it, so an empty log proves nothing; see the control run in the report.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import select
import socket
import socketserver
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit


class _Handler(socketserver.StreamRequestHandler):
    server: Proxy

    def handle(self) -> None:
        self.request.settimeout(30)
        try:
            line = self.rfile.readline(65537).decode("latin-1").strip()
            if not line:
                return
            method, target, _ = line.split(" ", 2)
            headers = []
            while (h := self.rfile.readline(65537)) not in (b"\r\n", b"\n", b""):
                headers.append(h)
            if method == "CONNECT":
                host, _, port = target.rpartition(":")
                self._connect(host, int(port or 443))
            else:
                u = urlsplit(target)
                self._plain(method, u.hostname or "", u.port or 80)
        except (ValueError, OSError):
            return

    def _decide(self, method: str, host: str, port: int) -> bool:
        allowed = host.lower() in self.server.allow
        self.server.record(
            {"t": time.time(), "method": method, "host": host, "port": port, "allowed": allowed}
        )
        return allowed

    def _plain(self, method: str, host: str, port: int) -> None:
        # absolute-URI HTTP: never forwarded, even when allowlisted (HTTPS only is needed)
        self._decide(method, host, port)
        self.wfile.write(
            b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        )

    def _connect(self, host: str, port: int) -> None:
        if not self._decide("CONNECT", host, port):
            self.wfile.write(
                b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            )
            return
        with socket.create_connection((host, port), timeout=15) as up:
            self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.wfile.flush()
            socks = [self.request, up]
            while True:
                r, _, _ = select.select(socks, [], [], 60)
                if not r:
                    return
                for s in r:
                    data = s.recv(65536)
                    if not data:
                        return
                    (up if s is self.request else self.request).sendall(data)


class Proxy(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, port: int = 0, allow: tuple[str, ...] = (), log: str | Path | None = None):
        super().__init__(("127.0.0.1", port), _Handler)
        self.allow = {a.lower() for a in allow}
        self.log = Path(log) if log else None
        self.events: list[dict] = []
        self._lock = threading.Lock()

    @property
    def port(self) -> int:
        return self.server_address[1]

    def record(self, event: dict) -> None:
        with self._lock:
            self.events.append(event)
            if self.log:
                with self.log.open("a") as f:
                    f.write(json.dumps(event) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.netproxy")
    ap.add_argument("--log", required=True)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--allow", nargs="*", default=[], help="hosts that may be connected to")
    ap.add_argument("--port-file", help="write the chosen port here once listening")
    a = ap.parse_args(argv)
    Path(a.log).parent.mkdir(parents=True, exist_ok=True)
    proxy = Proxy(a.port, tuple(a.allow), a.log)
    if a.port_file:
        Path(a.port_file).write_text(f"{proxy.port}\n")
    with contextlib.suppress(KeyboardInterrupt):
        proxy.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
