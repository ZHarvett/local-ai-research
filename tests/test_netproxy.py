"""smallpc.netproxy: deny-by-default logging proxy. Local sockets only, no real network."""

from __future__ import annotations

import socket
import threading

from smallpc.netproxy import Proxy


def _serve(proxy: Proxy) -> None:
    threading.Thread(target=proxy.serve_forever, daemon=True).start()


def _connect(proxy: Proxy, target: str) -> bytes:
    with socket.create_connection(("127.0.0.1", proxy.port), timeout=5) as s:
        s.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
        return s.recv(4096)


def test_denies_everything_by_default_and_logs_each_attempt(tmp_path):
    log = tmp_path / "net.jsonl"
    p = Proxy(0, (), log)
    _serve(p)
    try:
        assert _connect(p, "models.dev:443").startswith(b"HTTP/1.1 403")
        assert _connect(p, "registry.npmjs.org:443").startswith(b"HTTP/1.1 403")
    finally:
        p.shutdown()
    assert [(e["host"], e["port"], e["allowed"]) for e in p.events] == [
        ("models.dev", 443, False),
        ("registry.npmjs.org", 443, False),
    ]
    assert len(log.read_text().splitlines()) == 2


def test_allowlisted_host_is_tunnelled_and_others_stay_denied():
    with socket.socket() as up:  # a local "upstream" standing in for an allowed host
        up.bind(("127.0.0.1", 0))
        up.listen(1)
        up_port = up.getsockname()[1]

        def echo():
            c, _ = up.accept()
            c.sendall(b"hello from upstream")
            c.close()

        threading.Thread(target=echo, daemon=True).start()
        p = Proxy(0, ("127.0.0.1",))
        _serve(p)
        try:
            with socket.create_connection(("127.0.0.1", p.port), timeout=5) as s:
                s.sendall(f"CONNECT 127.0.0.1:{up_port} HTTP/1.1\r\n\r\n".encode())
                buf = b""
                while b"hello from upstream" not in buf:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
            assert b"200 Connection Established" in buf and b"hello from upstream" in buf
            assert _connect(p, "example.com:443").startswith(b"HTTP/1.1 403")
        finally:
            p.shutdown()
    assert [e["allowed"] for e in p.events] == [True, False]


def test_plain_http_is_never_forwarded():
    p = Proxy(0, ("example.com",))
    _serve(p)
    try:
        with socket.create_connection(("127.0.0.1", p.port), timeout=5) as s:
            s.sendall(b"GET http://example.com/x HTTP/1.1\r\nHost: example.com\r\n\r\n")
            assert s.recv(4096).startswith(b"HTTP/1.1 403")
    finally:
        p.shutdown()
