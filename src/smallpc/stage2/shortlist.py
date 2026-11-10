"""The Stage 1 shortlist as the Stage 2 tools read it.

Cell names come from ``data/analysis/select-screening.json`` (rank order per context); their
placement, context and batch are read from the committed Stage 1 spec
(``configs/sweeps/stage1.toml``) through ``smallpc.sweep.spec.expand``, never parsed from the names.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ..config import load_sweep, repo_root
from ..sweep import spec as sp

SELECT_JSON = "data/analysis/select-screening.json"
STAGE1_SPEC = "configs/sweeps/stage1.toml"


class ShortlistError(ValueError):
    """The shortlist or the Stage 1 spec cannot be used; the message says what is wrong."""


@dataclass(frozen=True)
class Entry:
    cell: str  # Stage 1 cell name, e.g. "P6-64K-b4096"
    placement: str  # axis value in the Stage 1 spec, e.g. "P6"
    context: str  # axis value, e.g. "64K"
    batch: str  # axis value, e.g. "b4096"


@dataclass(frozen=True)
class Shortlist:
    path: str
    sha256: str
    spec_path: str
    spec_sha256: str
    contexts: dict[str, tuple[Entry, Entry]]  # context -> (top, second), Stage 1 order
    spec: object  # the parsed Stage 1 SweepSpec (axes, canary)

    def top(self, context: str) -> Entry:
        return self.contexts[context][0]

    def second(self, context: str) -> Entry:
        return self.contexts[context][1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_shortlist(
    root: Path | None = None, select_json: str = SELECT_JSON, stage1_spec: str = STAGE1_SPEC
) -> Shortlist:
    root = Path(root) if root else repo_root()
    jpath, spath = root / select_json, root / stage1_spec
    if not jpath.exists():
        raise ShortlistError(f"no shortlist file {select_json}")
    data = json.loads(jpath.read_text())
    if data.get("mode") != "screening":
        raise ShortlistError(f"{select_json} is not a screening result (mode {data.get('mode')!r})")
    spec = load_sweep(spath)
    by_name = {c.name: c for c in sp.expand(spec, root)}
    contexts: dict[str, tuple[Entry, Entry]] = {}
    for key, block in data["contexts"].items():
        names = block.get("shortlist") or []
        if len(names) != 2:
            raise ShortlistError(f"context {key}: the shortlist must hold two cells, got {names}")
        entries = []
        for name in names:
            cell = by_name.get(name)
            if cell is None:
                raise ShortlistError(f"shortlisted cell {name!r} is not in {stage1_spec}")
            missing = [a for a in ("placement", "context", "batch") if a not in cell.coords]
            if missing:
                raise ShortlistError(f"cell {name!r} has no {missing} coordinate in the spec")
            if cell.deps:
                raise ShortlistError(
                    f"cell {name!r} needs {list(cell.deps)} for its @n_fit token; Stage 2 has "
                    "no P1 sibling, so a P8/P9 placement cannot be built from this shortlist"
                )
            if cell.coords["context"] != key:
                raise ShortlistError(
                    f"cell {name!r} is in context {cell.coords['context']} in the spec but "
                    f"under {key} in the shortlist"
                )
            entries.append(
                Entry(name, cell.coords["placement"], cell.coords["context"], cell.coords["batch"])
            )
        contexts[key] = (entries[0], entries[1])
    return Shortlist(select_json, _sha256(jpath), stage1_spec, _sha256(spath), contexts, spec)
