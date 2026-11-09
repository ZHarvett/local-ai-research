"""HTTP client for llama-server's ``/completion``: plain and streaming requests with timeouts that
scale with the prompt. Raises ``RequestTimeout`` or ``ServerGone``; never retries."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import httpx

# Timeout = BASE + prompt_tokens / PREFILL_FLOOR + n_predict / DECODE_FLOOR. The floors are far
# below the measured speeds (770-880 tok/s prefill, 50-85 tok/s decode), so a slow config is not
# mistaken for a hung server, and a 96K Request A gets about ten minutes. The prompt length used is
# the whole prompt, so a Request B that misses its cache cannot time out falsely.
TIMEOUT_BASE_S = 120.0
PREFILL_FLOOR_TPS = 200.0
DECODE_FLOOR_TPS = 10.0


def timeout_s(n_prompt: int, n_predict: int) -> float:
    return TIMEOUT_BASE_S + n_prompt / PREFILL_FLOOR_TPS + max(n_predict, 1) / DECODE_FLOOR_TPS


class RequestTimeout(RuntimeError):
    """The request did not finish within its timeout."""

    def __init__(self, msg: str, elapsed_s: float, partial: dict | None = None):
        super().__init__(msg)
        self.elapsed_s = elapsed_s
        self.partial = partial or {}


class ServerGone(RuntimeError):
    """The connection failed or was dropped: the server died or is not reachable."""


@dataclass
class Completion:
    body: dict  # the final response (the last chunk of a stream carries the same fields)
    t_start_epoch: float
    t_end_epoch: float
    wall_s: float
    ttft_s: float | None = None
    http_status: int | None = None
    chunks: int = 0
    content: str = field(default="", repr=False)


class Client:
    def __init__(self, base_url: str, http: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.Client(base_url=self.base_url, timeout=30.0)

    def close(self) -> None:
        self.http.close()

    def get_json(self, path: str, timeout: float = 30.0) -> dict:
        try:
            r = self.http.get(path, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException as e:
            raise RequestTimeout(f"GET {path} timed out", timeout) from e
        except httpx.TransportError as e:
            raise ServerGone(f"GET {path}: {e!r}") from e

    def healthy(self, timeout: float = 5.0) -> bool:
        try:
            return self.http.get("/health", timeout=timeout).status_code == 200
        except httpx.HTTPError:
            return False

    def completion(
        self,
        tokens: list[int],
        n_predict: int,
        sampling: dict,
        *,
        seed: int,
        stream: bool,
        cache_prompt: bool = True,
        timeout: float | None = None,
    ) -> Completion:
        total = timeout if timeout is not None else timeout_s(len(tokens), n_predict)
        body = {
            "prompt": tokens,
            "n_predict": n_predict,
            "cache_prompt": cache_prompt,
            "stream": stream,
            "seed": seed,
            **sampling,
        }
        t_epoch, t0 = time.time(), time.monotonic()
        try:
            if stream:
                return self._stream(body, total, t_epoch, t0)
            r = self.http.post(
                "/completion",
                json=body,
                timeout=httpx.Timeout(connect=10.0, read=total, write=120.0, pool=10.0),
            )
            t1 = time.monotonic()
            if r.status_code != 200:
                raise ServerGone(f"/completion returned HTTP {r.status_code}: {r.text[:200]}")
            return Completion(r.json(), t_epoch, time.time(), t1 - t0, None, r.status_code)
        except httpx.TimeoutException as e:
            raise RequestTimeout(
                f"/completion timed out after {time.monotonic() - t0:.0f} s (limit {total:.0f} s)",
                time.monotonic() - t0,
            ) from e
        except httpx.TransportError as e:
            raise ServerGone(f"/completion: {e!r}") from e

    def _stream(self, body: dict, total: float, t_epoch: float, t0: float) -> Completion:
        ttft = None
        chunks = 0
        parts: list[str] = []
        last: dict = {}
        timeout = httpx.Timeout(connect=10.0, read=total, write=120.0, pool=10.0)
        with self.http.stream("POST", "/completion", json=body, timeout=timeout) as r:
            if r.status_code != 200:
                r.read()
                raise ServerGone(f"/completion returned HTTP {r.status_code}: {r.text[:200]}")
            status = r.status_code
            for line in r.iter_lines():
                now = time.monotonic()
                if now - t0 > total:
                    raise RequestTimeout(
                        f"stream exceeded {total:.0f} s",
                        now - t0,
                        {"chunks": chunks, "ttft_s": ttft},
                    )
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except ValueError:
                    continue
                chunks += 1
                text = obj.get("content") or ""
                if ttft is None and (text or obj.get("stop")):
                    ttft = now - t0
                parts.append(text)
                last = obj
                if obj.get("stop"):
                    break
        t1 = time.monotonic()
        if not last.get("stop"):
            raise ServerGone("the stream ended without a final chunk (server died?)")
        return Completion(last, t_epoch, time.time(), t1 - t0, ttft, status, chunks, "".join(parts))
