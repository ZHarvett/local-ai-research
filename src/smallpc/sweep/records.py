"""Record schema and the append-only store of a sweep session.

``records.jsonl`` holds two record types, one JSON object per line:

* ``request``: one line per request (warm-up, short point, Request A, Request B, canary requests);
* ``cell``: one line per cell attempt, so a cell that did not fit is visible in the same file.

The unit of commit is a *batch*: the warm-up (two requests), one repetition (the short point plus
every pair) or one cell record. A batch is appended with a single ``write`` call, and every line
carries ``batch_id``, ``batch_index`` and ``batch_size``. The reader accepts a batch only when all
its lines are present, and it skips unparsable lines (a torn last line after a hard kill), so a
kill can never leave half a repetition that a resume would then duplicate. The reader reports what
it skipped. Nothing here ever rewrites or deletes a line.
"""

from __future__ import annotations

import json
import os
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA = 1
Role = Literal["measured", "warmup", "canary_start", "canary_end"]
Kind = Literal["short", "A", "B", "warmup"]
CellStatus = Literal[
    "complete", "did_not_fit", "not_applicable", "interrupted", "server_died", "failed"
]
FINAL_STATUSES = frozenset({"complete", "did_not_fit", "not_applicable"})
REQUEST_FLAGS = ("warm_prefill", "cache_miss", "short_gen", "accounting")
WINDOW_FLAGS = ("thermal", "paging")
RERUN_FLAGS = ("warm_prefill", "cache_miss", "accounting", "thermal", "paging")  # not short_gen


class _Rec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Client(_Rec):
    t_start_epoch: float
    t_end_epoch: float
    wall_s: float
    ttft_s: float | None = None  # streaming requests (Request B)
    http_status: int | None = None


class TelemetryRef(_Rec):
    file: str | None = None  # gzip CSV, relative to the session directory
    t0_epoch: float | None = None
    t1_epoch: float | None = None


class RequestRecord(_Rec):
    schema_version: Literal[1] = Field(default=SCHEMA, alias="schema")
    record_type: Literal["request"] = "request"
    session_id: str
    cell: str
    config_hash: str = Field(pattern=r"^[0-9a-f]{16}$")
    attempt: Literal[1, 2] = 1
    server_run_id: str
    server_instance: int = Field(ge=0)
    code_commit: str
    utc: str

    role: Role
    warmup: bool
    kind: Kind

    workload_id: str
    workload_kind: str
    depth: int | None = None  # d of a pair; the prompt length of other kinds
    variant: int
    repetition: int
    nonce: str
    seed: int
    position: int  # index of the request within its repetition (0 = short point)
    depth_order: list[int] = []
    window_id: str | None = None

    n_predict: int
    stream: bool
    cache_prompt: bool = True
    sampling: dict[str, Any]
    expected: dict[str, Any]

    timings: dict[str, Any]
    cache_n: int | None = None
    prompt_n: int | None = None
    prompt_ms: float | None = None
    prompt_per_second: float | None = None
    predicted_n: int | None = None
    predicted_ms: float | None = None
    predicted_per_second: float | None = None
    draft_n: int | None = None  # MTP / speculative cells only
    draft_n_accepted: int | None = None
    stop_type: str | None = None
    truncated: bool | None = None
    tokens_evaluated: int | None = None
    tokens_cached: int | None = None
    id_slot: int | None = None  # the slot the server reports (null if the response lacks it)

    client: Client
    snapshot_id: str | None = None
    telemetry: TelemetryRef = TelemetryRef()
    free_vram_min_mib: float | None = None

    flags: list[str] = []
    flag_detail: dict[str, Any] = {}

    batch_id: str
    batch_index: int
    batch_size: int

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CellRecord(_Rec):
    schema_version: Literal[1] = Field(default=SCHEMA, alias="schema")
    record_type: Literal["cell"] = "cell"
    session_id: str
    cell: str
    config_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    role: Role = "measured"
    status: CellStatus
    final: bool
    reason: str | None = None
    flags: list[str] = []
    server_instance: int | None = None
    exit_code: int | None = None
    attempt: Literal[1, 2] = 1
    repetitions_done: list[int] = []
    n_requests: int = 0
    load_time_s: float | None = None
    summary_file: str | None = None
    code_commit: str
    utc: str
    batch_id: str
    batch_index: int = 0
    batch_size: int = 1

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def new_batch_id() -> str:
    return uuid.uuid4().hex[:12]


def stamp_batch(records: list[dict]) -> list[dict]:
    """Give every record of one batch the same ``batch_id`` and its index and size."""
    bid = new_batch_id()
    for i, r in enumerate(records):
        r.update(batch_id=bid, batch_index=i, batch_size=len(records))
    return records


def dump_line(rec: BaseModel | dict) -> str:
    data = rec.model_dump(by_alias=True) if isinstance(rec, BaseModel) else rec
    return json.dumps(data, separators=(",", ":"), sort_keys=False)


@dataclass
class Loaded:
    requests: list[dict] = field(default_factory=list)
    cells: list[dict] = field(default_factory=list)
    torn_lines: int = 0  # lines that did not parse
    incomplete_batches: int = 0  # batches missing lines (their lines are ignored)


class Store:
    """``records.jsonl`` of one session."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def append_batch(self, records: Iterable[BaseModel | dict]) -> int:
        """Validate and append all records with one ``write``; returns the number written."""
        lines = [dump_line(r) for r in records]
        if not lines:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = ("\n".join(lines) + "\n").encode()
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            self._close_torn_line(fd)
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        return len(lines)

    def _close_torn_line(self, fd: int) -> None:
        """If a hard kill left a last line without a newline, end it so it stays one bad line."""
        size = os.fstat(fd).st_size
        if size == 0:
            return
        with open(self.path, "rb") as f:
            f.seek(size - 1)
            if f.read(1) != b"\n":
                os.write(fd, b"\n")

    def load(self) -> Loaded:
        out = Loaded()
        if not self.path.exists():
            return out
        groups: dict[str, list[dict]] = {}
        for line in self.path.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                bid, size = obj["batch_id"], obj["batch_size"]
            except (ValueError, KeyError, TypeError):
                out.torn_lines += 1
                continue
            groups.setdefault(bid, []).append(obj)
            obj["_batch_size"] = size
        for objs in groups.values():
            idx = {o["batch_index"] for o in objs}
            if len(objs) != objs[0]["_batch_size"] or len(idx) != len(objs):
                out.incomplete_batches += 1
                continue
            for o in objs:
                o.pop("_batch_size", None)
                (out.requests if o.get("record_type") == "request" else out.cells).append(o)
        return out


# ------------------------------------------------------------------------------ resume index


def measured_key(r: dict) -> tuple:
    """The identity of one measured or canary request: what resume and the duplicate check use."""
    return (r["config_hash"], r["role"], r["workload_id"], r["repetition"], r["attempt"], r["kind"])


def find_duplicates(requests: list[dict]) -> list[tuple]:
    """Keys that occur more than once. Warm-ups are excluded: every server start has its own
    (they are keyed by ``server_run_id`` instead)."""
    keys = Counter(measured_key(r) for r in requests if r["role"] != "warmup")
    keys.update((*measured_key(r), r["server_run_id"]) for r in requests if r["role"] == "warmup")
    return sorted(k for k, n in keys.items() if n > 1)


@dataclass
class Index:
    """What a session has already done, from its records."""

    loaded: Loaded

    def done_repetitions(self, config_hash: str, role: str, attempt: int = 1) -> set[int]:
        return {
            r["repetition"]
            for r in self.loaded.requests
            if r["config_hash"] == config_hash and r["role"] == role and r["attempt"] == attempt
        }

    def final_cell(self, config_hash: str | None, name: str, role: str = "measured") -> dict | None:
        for c in reversed(self.loaded.cells):
            if (
                c["cell"] == name
                and c["role"] == role
                and c["final"]
                and (config_hash is None or c["config_hash"] in (None, config_hash))
            ):
                return c
        return None

    def requests_of(self, config_hash: str, role: str | None = None) -> list[dict]:
        return [
            r
            for r in self.loaded.requests
            if r["config_hash"] == config_hash and (role is None or r["role"] == role)
        ]

    def flagged_repetitions(self) -> dict[tuple[str, int], list[str]]:
        """(config_hash, repetition) -> the section 5.6 flags that call for a re-run, for the
        measured attempt-1 requests. ``short_gen`` never does."""
        out: dict[tuple[str, int], set[str]] = {}
        for r in self.loaded.requests:
            if r["role"] != "measured" or r["attempt"] != 1:
                continue
            hit = [f for f in r.get("flags", []) if f in RERUN_FLAGS]
            if hit:
                out.setdefault((r["config_hash"], r["repetition"]), set()).update(hit)
        return {k: sorted(v) for k, v in out.items()}
