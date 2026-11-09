"""Time estimates for cells and sweeps, from the WP8 live check (data/workloads/live-check-*.json).

Mean wall times per request on ``--fit`` with 8-bit KV at 128K, ``-np 1``. They are the only
measured input available before the first sweep; ``overheads`` can be replaced by measured values
(``python -m smallpc.sweep status`` does that once cells have finished).
"""

from __future__ import annotations

# depth -> (Request A wall s, Request B wall s)
LIVE = {
    8192: (9.40, 8.66),
    16384: (18.97, 8.96),
    24576: (28.80, 9.33),
    32768: (38.88, 9.69),
    49152: (59.60, 10.36),
    65536: (81.20, 11.09),
    98304: (127.26, 12.54),
}
SHORT_S = 7.05
WARMUP_S = 21.8  # two requests of 8K + 128 tokens
OVERHEAD_S = 60.0  # idle window, snapshot, launch and load, stop, log parse
DEPTHS = {
    32768: (8192, 16384, 24576),
    65536: (16384, 32768, 49152),
    131072: (32768, 65536, 98304),
}
LOAD_S = 25.0
STOP_S = 5.0


def repetition_s(depths) -> float:
    return SHORT_S + sum(LIVE[d][0] + LIVE[d][1] for d in depths)


def cell_s(
    context: int,
    repetitions: int,
    *,
    overhead: float = OVERHEAD_S,
    warmup: float = WARMUP_S,
    slowdown: float = 1.0,
) -> float:
    return overhead + warmup + repetitions * repetition_s(DEPTHS[context]) * slowdown


def probe_step_s(context: int, *, load: float = LOAD_S, stop: float = STOP_S) -> float:
    """One probing step: load, Request A at the deepest depth, a short Request B, stop."""
    d = DEPTHS[context][-1]
    return load + LIVE[d][0] + 4.8 + stop


def canary_s(
    repetitions: int = 3, *, overhead: float = OVERHEAD_S, warmup: float = WARMUP_S
) -> float:
    return overhead + warmup + repetitions * (SHORT_S + sum(LIVE[16384]))


def stage1_s(
    *,
    repetitions: int = 2,
    probe_steps: int = 3,
    slowdown_cpu_cells: float = 1.0,
    overhead: float = OVERHEAD_S,
    warmup: float = WARMUP_S,
    probe_load: float = LOAD_S,
    probe_stop: float = STOP_S,
) -> dict:
    """Seconds for the Stage 1 design: 3 contexts x (9 placements x 2 batch settings + stock)."""
    cells = probing = 0.0
    for ctx in DEPTHS:
        base = cell_s(ctx, repetitions, overhead=overhead, warmup=warmup)
        slow = cell_s(
            ctx, repetitions, overhead=overhead, warmup=warmup, slowdown=slowdown_cpu_cells
        )
        # per batch setting: P1-P5 and stock-like speed, P6-P9 (CPU experts) possibly slower
        cells += 2 * (5 * base + 4 * slow) + base  # + stock
        probing += 2 * probe_steps * probe_step_s(ctx, load=probe_load, stop=probe_stop)
    canaries = 2 * canary_s(overhead=overhead, warmup=warmup)
    return {
        "cells_s": cells,
        "probing_s": probing,
        "canaries_s": canaries,
        "total_s": cells + probing + canaries,
        "total_without_probing_s": cells + canaries,
    }


def spec_s(
    cells,
    repetitions: int,
    *,
    canary_repetitions: int = 0,
    probe_steps: int = 3,
    overhead: float = OVERHEAD_S,
    warmup: float = WARMUP_S,
    probe_load: float = LOAD_S,
    probe_stop: float = STOP_S,
) -> dict:
    """Seconds for the cells of a (possibly filtered) sweep spec: every cell at its context, the
    probing of each (context, batch) group that has a ``@max_fit`` token (``probe_steps`` steps
    of ``probe_step_s``), and a start and end canary when ``canary_repetitions`` is above zero.
    Cells are ``smallpc.sweep.spec.CellDef``s; the context comes from the cell's overrides."""
    cell_t = 0.0
    groups: set[tuple[int, str]] = set()
    for c in cells:
        ctx = int(c.overrides["context"])
        cell_t += cell_s(ctx, repetitions, overhead=overhead, warmup=warmup)
        if any(t.kind == "max_fit" for t in c.tokens.values()):
            groups.add((ctx, c.coords.get("batch", "")))
    probing = sum(
        probe_steps * probe_step_s(ctx, load=probe_load, stop=probe_stop) for ctx, _ in groups
    )
    canaries = (
        2 * canary_s(canary_repetitions, overhead=overhead, warmup=warmup)
        if canary_repetitions
        else 0.0
    )
    return {
        "cells_s": cell_t,
        "probing_s": probing,
        "canaries_s": canaries,
        "total_s": cell_t + probing + canaries,
        "probe_groups": len(groups),
    }
