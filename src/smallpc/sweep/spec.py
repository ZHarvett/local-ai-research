"""Expansion of a sweep spec into cells, placement tokens, filters and the cell order.

A spec (``smallpc.config.SweepSpec``) holds cell blocks. ``expand`` turns them into ``CellDef``s:

* ``[defaults]`` are merged into candidate/tuned cells, ``[stock_defaults]`` into stock cells.
  The section 5.4 sweep defaults (8-bit KV, ``-fa on``, ``-np 1``) are applied at render time by
  ``ServerConfig.effective()``, and the explicit ``--port`` comes from machine.toml; stock never
  inherits either (tests/test_sweep_spec.py checks the rendered argv of every cell).
* Merge order: defaults, then the axes of a product in the order listed, then ``set``. Two axes
  setting the same field is an error.
* Placement tokens (``@max_fit``, ``@max_fit-2048``, ``@n_fit(P1)``, ``@n_fit(P1)-2``) are allowed
  only in ``moe_cache_mib`` and ``n_cpu_moe``. They are resolved at run time
  (``smallpc.sweep.session``, with ``smallpc.sweep.probe``).
  ``@n_fit(P1)`` names the sibling cell found by putting ``P1`` into the name template.
"""

from __future__ import annotations

import hashlib
import random
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..config import ServerConfig, SweepSpec, repo_root

FILTER_AXES = ("context", "batch")  # `--only` may filter on these axes only
TOKEN_FIELDS = ("moe_cache_mib", "n_cpu_moe")
_MAXFIT = re.compile(r"^@max_fit(?:-(\d+))?$")
_NFIT = re.compile(r"^@n_fit\(([A-Za-z0-9._-]+)\)(?:-(\d+))?$")
PLACEMENT_AXIS = "placement"


class SpecError(ValueError):
    """A spec that cannot be expanded or filtered; the message says what to change."""


@dataclass(frozen=True)
class Token:
    kind: str  # "max_fit" or "n_fit"
    offset: int  # subtracted from the resolved value
    ref: str | None = None  # n_fit: the placement whose P1-style cell provides N_fit


def parse_token(value: Any) -> Token | None:
    """A placement token, or None if ``value`` is not a string starting with ``@``."""
    if not (isinstance(value, str) and value.startswith("@")):
        return None
    if m := _MAXFIT.match(value):
        return Token("max_fit", int(m[1] or 0))
    if m := _NFIT.match(value):
        return Token("n_fit", int(m[2] or 0), m[1])
    raise SpecError(f"unknown placement token {value!r}")


@dataclass(frozen=True)
class CellDef:
    name: str
    profile: str
    overrides: dict[str, Any]  # server-config fields; values may be Tokens-as-strings
    coords: dict[str, str] = field(default_factory=dict)  # product axis -> value key
    template: str | None = None
    config_path: str | None = None  # reference cells

    @property
    def tokens(self) -> dict[str, Token]:
        return {k: t for k, v in self.overrides.items() if (t := parse_token(v)) is not None}

    @property
    def deps(self) -> tuple[str, ...]:
        """Names of the cells whose run-time results this cell needs (``@n_fit(Pn)``)."""
        out = []
        for t in self.tokens.values():
            if t.kind == "n_fit":
                if self.template is None or PLACEMENT_AXIS not in self.coords:
                    raise SpecError(
                        f"cell {self.name!r}: @n_fit({t.ref}) needs a product cell with a "
                        f"{PLACEMENT_AXIS!r} axis"
                    )
                out.append(self.template.format(**{**self.coords, PLACEMENT_AXIS: t.ref}))
        return tuple(sorted(set(out)))


def _product_combos(product: dict[str, list[str]]) -> list[dict[str, str]]:
    combos: list[dict[str, str]] = [{}]
    for axis, values in product.items():
        combos = [{**c, axis: v} for c in combos for v in values]
    return combos


def _merge(parts: list[tuple[str, dict]], cell: str) -> dict:
    out: dict = {}
    owner: dict[str, str] = {}
    for label, fields in parts:
        for k, v in fields.items():
            if k in out and owner[k].startswith("axis") and label.startswith("axis"):
                raise SpecError(f"cell {cell!r}: field {k!r} is set by both {owner[k]} and {label}")
            out[k] = v
            owner[k] = label
    return out


def _load_ref(root: Path, rel: str) -> tuple[str, dict]:
    with open(root / rel, "rb") as f:
        data = tomllib.load(f)
    profile = data.pop("profile")
    return profile, data


def expand(spec: SweepSpec, root: Path | None = None) -> list[CellDef]:
    """All cells of the spec, in spec order. Raises ``SpecError`` for anything inconsistent."""
    root = root or repo_root()
    cells: list[CellDef] = []
    for block in spec.cells:
        if block.config is not None:
            profile, fields = _load_ref(root, block.config)
            cells.append(CellDef(block.name, profile, fields, config_path=block.config))
            continue
        base = spec.stock_defaults if block.profile == "stock" else spec.defaults
        for combo in _product_combos(block.product):
            parts = [("defaults", dict(base))]
            parts += [(f"axis {a}={v}", dict(spec.axes[a][v])) for a, v in combo.items()]
            parts.append(("set", dict(block.set)))
            name = block.name.format(**combo) if block.product else block.name
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
                raise SpecError(f"cell name {name!r} is not a valid name")
            cells.append(
                CellDef(
                    name,
                    block.profile or "candidate",
                    _merge(parts, name),
                    coords=combo,
                    template=block.name if block.product else None,
                )
            )
    names = [c.name for c in cells]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise SpecError(f"duplicate cell name(s) after expansion: {dupes}")
    return cells


def validate_cells(cells: list[CellDef]) -> None:
    """Each cell must be a valid ``ServerConfig`` (tokens replaced by 1) with ``-lv 4``, and every
    ``@n_fit`` dependency must name a cell of the sweep."""
    names = {c.name for c in cells}
    for c in cells:
        fields = {k: (1 if parse_token(v) else v) for k, v in c.overrides.items()}
        for k in c.tokens:
            if k not in TOKEN_FIELDS:
                raise SpecError(f"cell {c.name!r}: placement tokens are not allowed in {k!r}")
        try:
            cfg = ServerConfig.model_validate({"profile": c.profile, **fields})
        except ValidationError as e:
            raise SpecError(f"cell {c.name!r} is not a valid server config: {e}") from e
        if cfg.log_verbosity != 4:
            raise SpecError(f"cell {c.name!r}: every sweep cell runs with log_verbosity = 4")
        for d in c.deps:
            if d not in names:
                raise SpecError(f"cell {c.name!r} depends on {d!r}, which is not in the sweep")


def parse_only(items: list[str]) -> dict[str, str]:
    """``["context=32K", "batch=b2048"]`` -> ``{"context": "32K", "batch": "b2048"}``."""
    out: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not value:
            raise SpecError(f"--only needs axis=value, got {item!r}")
        if key not in FILTER_AXES:
            raise SpecError(f"--only allows only {list(FILTER_AXES)}, not {key!r}")
        if key in out:
            raise SpecError(f"--only {key} given twice")
        out[key] = value
    return out


def apply_filter(cells: list[CellDef], only: dict[str, str]) -> list[CellDef]:
    """Keep the cells whose coordinates match every filter. Cells without a coordinate on a
    filtered axis are dropped. Fails if nothing is left or a kept cell loses a dependency."""
    if not only:
        return cells
    kept = [c for c in cells if all(c.coords.get(k) == v for k, v in only.items())]
    if not kept:
        raise SpecError(f"--only {only} matches no cell")
    names = {c.name for c in kept}
    for c in kept:
        for d in c.deps:
            if d not in names:
                raise SpecError(
                    f"--only {only} removes {d!r}, which cell {c.name!r} needs for its @n_fit token"
                )
    return kept


def order_cells(cells: list[CellDef], seed: int) -> list[CellDef]:
    """A seeded shuffle that respects dependencies: a cell is picked at random among the cells
    whose dependencies are already placed. Deterministic for a given set of cells and seed."""
    rng = random.Random(f"{seed}|cell-order")
    pending = sorted(cells, key=lambda c: c.name)  # canonical start, independent of spec order
    placed: list[CellDef] = []
    done: set[str] = set()
    while pending:
        ready = [c for c in pending if all(d in done for d in c.deps)]
        if not ready:
            raise SpecError("cyclic @n_fit dependencies: " + ", ".join(c.name for c in pending))
        pick = ready[rng.randrange(len(ready))]
        placed.append(pick)
        done.add(pick.name)
        pending.remove(pick)
    return placed


def depth_order(seed: int, cell: str, repetition: int, depths: list[int]) -> list[int]:
    """Depth order of one repetition: a shuffle seeded by (seed, cell name, repetition)."""
    digest = hashlib.sha256(f"{seed}|{cell}|{repetition}".encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    out = list(depths)
    rng.shuffle(out)
    return out


def spec_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render_toml(profile: str, fields: dict[str, Any]) -> str:
    """A server TOML for a profile and flat fields (str, int, bool)."""
    lines = [f'profile = "{profile}"']
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, int | float):
            lines.append(f"{k} = {v}")
        else:
            lines.append(f'{k} = "{v}"')
    return "\n".join(lines) + "\n"
