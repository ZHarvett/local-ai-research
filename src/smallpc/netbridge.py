"""Forward loopback ports into a network-less sandbox through Unix sockets (WP7).

A harness inside ``scripts/_sandbox.sh --bridge PORT`` lives in a private network namespace with
only a loopback interface, so it can reach nothing but the ports bridged in. Two halves:

    python -m smallpc.netbridge host --sock FILE --target HOST:PORT
        outside: listens on the Unix socket FILE and forwards each connection to HOST:PORT
    python -m smallpc.netbridge run --bridge PORT:FILE [--bridge ...] -- COMMAND...
        inside the namespace: brings ``lo`` up, listens on 127.0.0.1:PORT, forwards each
        connection to the Unix socket FILE, runs COMMAND and exits with its status

Only bytes are forwarded; nothing is inspected or logged.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import socket
import struct
import subprocess
import sys
import threading
from pathlib import Path

SIOCGIFFLAGS, SIOCSIFFLAGS, IFF_UP = 0x8913, 0x8914, 0x1


def loopback_up() -> None:
    """Bring ``lo`` up in the current network namespace (needs CAP_NET_ADMIN there)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        req = struct.pack("16sH14s", b"lo", 0, b"")
        flags = struct.unpack("16sH14s", fcntl.ioctl(s, SIOCGIFFLAGS, req))[1]
        fcntl.ioctl(s, SIOCSIFFLAGS, struct.pack("16sH14s", b"lo", flags | IFF_UP, b""))


def _pump(a: socket.socket, b: socket.socket) -> None:
    try:
        while data := a.recv(65536):
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            with contextlib.suppress(OSError):
                s.shutdown(socket.SHUT_RDWR)


def _serve(listener: socket.socket, dial) -> None:
    while True:
        try:
            conn, _ = listener.accept()
        except OSError:
            return
        try:
            up = dial()
        except OSError:
            conn.close()
            continue
        threading.Thread(target=_pump, args=(conn, up), daemon=True).start()
        threading.Thread(target=_pump, args=(up, conn), daemon=True).start()


def serve_unix_to_tcp(sock_path: Path, host: str, port: int) -> socket.socket:
    sock_path.unlink(missing_ok=True)
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(str(sock_path))
    sock_path.chmod(0o600)
    srv.listen(64)
    dial = lambda: socket.create_connection((host, port), timeout=10)  # noqa: E731
    threading.Thread(target=_serve, args=(srv, dial), daemon=True).start()
    return srv


def serve_tcp_to_unix(port: int, sock_path: Path) -> socket.socket:
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(64)

    def dial() -> socket.socket:
        u = socket.socket(socket.AF_UNIX)
        u.connect(str(sock_path))
        return u

    threading.Thread(target=_serve, args=(srv, dial), daemon=True).start()
    return srv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.netbridge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("host")
    h.add_argument("--sock", required=True)
    h.add_argument("--target", required=True, help="HOST:PORT")
    r = sub.add_parser("run")
    r.add_argument("--bridge", action="append", default=[], help="PORT:SOCKFILE")
    r.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)

    if a.cmd == "host":
        host, _, port = a.target.rpartition(":")
        serve_unix_to_tcp(Path(a.sock), host, int(port))
        threading.Event().wait()
        return 0

    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
    if not cmd:
        ap.error("no command given")
    loopback_up()
    for spec in a.bridge:
        port, _, sock = spec.partition(":")
        serve_tcp_to_unix(int(port), Path(sock))
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
