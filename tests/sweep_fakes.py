"""Test doubles for the sweep runner: a synthetic workload provider, a fake telemetry sampler fed
by the mock server's VRAM file, and a builder for a sweep ``Env`` that runs the real launch and
stop scripts against tests/fixtures/mock_llama_server.py (CI-safe: no GPU, no model)."""

from __future__ import annotations

import contextlib
import csv
import json
import threading
import time
import zlib
from pathlib import Path

from conftest import FIXTURES, REPO
from smallpc import telemetry
from smallpc.config import load_machine, load_model
from smallpc.sweep.core import Env
from smallpc.sweep.server import ServerProc
from smallpc.workloads.api import Workload

MOCK = FIXTURES / "mock_llama_server.py"
DEPTHS = [1000, 2000, 3000]
APPEND = 300
N_PREDICT_B = 400


class SynthProvider:
    """Deterministic token arrays: a nonce prefix, then tokens that depend on the variant only (so
    different depths of one variant share a prefix, as the real prompts do). ``depths`` is small
    so a test sweep takes seconds."""

    def __init__(self, depths=None, append=APPEND):
        self.d, self.append = list(depths or DEPTHS), append
        self.calls: list[tuple] = []

    def depths(self, context: int) -> list[int]:
        return list(self.d)

    def fits(self, d: int, per_slot: int) -> bool:
        return d + self.append + N_PREDICT_B <= per_slot

    def get(self, kind: str, length: int, repetition: int = 0, base_url=None) -> Workload:
        self.calls.append((kind, length, repetition))
        variant = 5 if kind == "warmup" else repetition % 5
        nonce = f"{kind}-{length}-{repetition}"
        head = [(zlib.crc32(nonce.encode()) & 0xFFFF) + 100000 + i for i in range(40)]
        body = [(variant * 977 + i * 31) % 50000 for i in range(length)]
        a = (head + body)[:length]
        pair = kind == "pair"
        b = a + [(i * 17 + 3) % 50000 + 60000 for i in range(self.append)] if pair else None
        letter = "A" if pair else kind
        wid = f"{letter}-v{variant}-{length}-r{repetition}"
        exp = {
            "d": length,
            "append_n": self.append if pair else None,
            "max_cache_n_fresh": 32,
            "processed_plus_cached": {"A": length, "B": length + self.append} if pair
            else {"request": length},
        }  # fmt: skip
        if pair:
            exp["min_cache_n_B"] = -(-95 * length // 100)
            exp["predicted_n_B"] = N_PREDICT_B
        return Workload(wid, kind, length, variant, repetition, nonce, 1000 + repetition,
                        a, b, exp, "t", "t")  # fmt: skip


class FakeSampler:
    """Samples the mock server's VRAM file ten times a second; ``rows_hook(row)`` can edit a
    row (for thermal and paging tests)."""

    def __init__(self, out: Path, vram_file: Path | None, hook=None):
        self.out, self.vram_file, self.hook = Path(out), vram_file, hook
        self.rows: list[dict] = []
        self.error = None
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def start(self):
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def _loop(self):
        while not self._stop.is_set():
            used = None
            with contextlib.suppress(OSError, ValueError):
                used = float(self.vram_file.read_text()) if self.vram_file else None
            row = dict.fromkeys(telemetry.COLUMNS)
            row.update(t_epoch=time.time(), gpu_mem_used_mib=used, tctl_c=60.0, majflt=0.0,
                       pswpin=5.0, server_vmswap_kib=0.0, gpu_temp_c=55.0)  # fmt: skip
            for c in telemetry.COLUMNS:
                if c.startswith("reason_"):
                    row[c] = False
            if self.hook:
                self.hook(row)
            self.rows.append(row)
            time.sleep(0.05)

    def stop(self):
        self._stop.set()
        if self._t:
            self._t.join(2)
        with open(self.out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=telemetry.COLUMNS)
            w.writeheader()
            for r in self.rows:
                w.writerow({k: ("" if v is None else v) for k, v in r.items()})

    def overhead(self):
        return {"n_rows": len(self.rows)}


GOOD_PRE = {"ok": True, "aborts": [], "hard_aborts": [], "transient_aborts": [], "warnings": [],
            "values": {"idle": {"ok": True, "busy_pct": 1.0, "waited_s": 0.0},
                       "mem_available_gib": 26.0}}  # fmt: skip


def make_env(tmp_path: Path, port: int, behavior: dict | None = None, *, hook=None,
             total_mib: float = 16000.0, pre_fn=None, sleeps=None) -> Env:  # fmt: skip
    """An Env whose servers are mock servers started through the real launch/stop scripts."""
    behavior = dict(behavior or {})
    vram_file = tmp_path / "vram.txt"
    behavior.setdefault("vram_file", str(vram_file))
    machine = tmp_path / "machine.toml"
    machine.write_text(
        f'[paths]\nllama_server="{MOCK}"\nmodels_dir="{tmp_path}"\n'
        f'slot_save_dir="/dev/shm/local-ai-research-slots"\n[server]\nport={port}\n'
    )
    model = FIXTURES / "model.toml"
    log_root = tmp_path / "logs"
    env_vars = {
        "SMALLPC_GPU_LOCK_FILE": str(tmp_path / "locks/gpu.lock"),
        "MOCK_BEHAVIOR": json.dumps(behavior),
    }
    (tmp_path / "manifest.json").write_text("{}")
    sleeps = sleeps if sleeps is not None else []

    def sleep(s):
        sleeps.append(s)

    return Env(
        root=REPO,
        scripts_dir=REPO / "scripts",
        out_root=tmp_path / "raw",
        log_root=log_root,
        probe_cache=tmp_path / "probes/cache.jsonl",
        machine_path=machine,
        model_path=model,
        machine=load_machine(machine),
        model=load_model(model),
        llama_commit="c" * 40,
        model_sha={"sha256": "b" * 64, "verified": False},
        git={"commit": "a" * 40, "short": "a" * 10, "dirty": False, "dirty_paths": []},
        manifest_path=tmp_path / "manifest.json",
        server_factory=lambda: ServerProc(
            REPO / "scripts", log_root, machine, model, health_timeout=30, env=env_vars
        ),  # fmt: skip
        sampler_factory=lambda out, pidfile: FakeSampler(out, vram_file, hook),
        snapshot_fn=lambda: {"snapshot_id": "snap0000test0000", "identity": {}, "state": {}},
        preconditions_fn=pre_fn or (lambda idle: json.loads(json.dumps(GOOD_PRE))),
        provider=SynthProvider(),
        gpu_total_mib=lambda: total_mib,
        gpu_used_mib=lambda: 2.0,
        n_layer=lambda: 40,
        sleep=sleep,
        settle_s=0.0,
        check_inhibit=False,
    )


def write_spec(tmp_path: Path, text: str, name: str = "spec.toml") -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


MINI_SPEC = """
name = "t"
repetitions = {reps}
shuffle_seed = 7
max_restarts = {restarts}
[defaults]
metrics = true
log_verbosity = 4
[stock_defaults]
metrics = true
log_verbosity = 4
[axes.context]
"32K" = {{ context = 32768 }}
[axes.placement]
Pa = {{ fit = "on" }}
Pb = {{ fit = "on", fit_target = 256 }}
[[cells]]
name = "{{placement}}-{{context}}"
profile = "candidate"
product = {{ placement = ["Pa", "Pb"], context = ["32K"] }}
[[cells]]
name = "stock-{{context}}"
profile = "stock"
product = {{ context = ["32K"] }}
{canary}
"""

CANARY = """
[canary]
cell = { profile = "candidate", context = 32768, fit = "on", metrics = true, log_verbosity = 4 }
repetitions = 2
points = ["short", "1K"]
"""


def mini_spec(tmp_path: Path, reps=2, restarts=2, canary=False) -> Path:
    return write_spec(tmp_path, MINI_SPEC.format(reps=reps, restarts=restarts,
                                                 canary=CANARY if canary else ""))  # fmt: skip


def read_records(sess) -> tuple[list[dict], list[dict]]:
    ld = sess.store.load()
    return ld.requests, ld.cells


def events(sess) -> list[dict]:
    f = sess.dir / "events.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []
