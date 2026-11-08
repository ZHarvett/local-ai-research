"""Exact-length packing. Pure: the token counter is a callable, so tests use a fake tokenizer.

Token counts are not additive across joins (merges happen at boundaries, and the nonce costs a
varying number of tokens), so every decision is made on the count of the *complete* text."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

Count = Callable[[str], int]


class PackingError(RuntimeError):
    """The target length cannot be reached with the given units."""


@dataclass(frozen=True)
class Unit:
    """One packable line. ``whole`` is its full text (``prefix + body + suffix``); a partial cut
    of ``k`` characters keeps ``prefix + body[:k]``. The prefix and suffix carry a file header
    and a trailing separator, so a cut always maps back to (file, lines kept, characters)."""

    body: str
    prefix: str = ""
    suffix: str = ""

    @property
    def whole(self) -> str:
        return self.prefix + self.body + self.suffix

    def part(self, k: int) -> str:
        return self.prefix + self.body[:k]


def largest_fit(n_items: int, fits: Callable[[int], bool]) -> int:
    """Largest n in [0, n_items] with ``fits(n)`` true, by binary search (fits(0) assumed true)."""
    lo, hi, best = 1, n_items, 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if fits(mid):
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return best


def tail_text(units: Sequence[Unit], n: int, k: int = 0) -> str:
    """First ``n`` units whole, then ``k`` characters of the next one."""
    text = "".join(u.whole for u in units[:n])
    return text + units[n].part(k) if k else text


def pack_exact(
    units: Sequence[Unit],
    render: Callable[[str], str],
    count: Count,
    target: int,
    *,
    max_backoff: int = 6,
    window: int = 12,
) -> tuple[int, int]:
    """Choose ``(n_units, partial_chars)`` so that ``count(render(tail_text(units, n, k))) ==
    target`` exactly. ``render`` puts the tail into the complete text. Raises ``PackingError`` if
    no exact fit exists after ``max_backoff`` shorter unit counts."""

    def total(n: int, k: int = 0) -> int:
        return count(render(tail_text(units, n, k)))

    n = largest_fit(len(units), lambda m: total(m) <= target)
    for _ in range(max_backoff + 1):
        if total(n) == target:
            return n, 0
        if n >= len(units):
            break
        body_len = len(units[n].body)
        k = largest_fit(body_len - 1, lambda c, n=n: total(n, c) <= target)
        lo, hi = max(1, k - window), min(body_len - 1, k + window)
        for c in range(hi, lo - 1, -1):
            if total(n, c) == target:
                return n, c
        if n == 0:
            break
        n -= 1  # retry with a longer partial unit
    raise PackingError(f"cannot reach exactly {target} tokens")
