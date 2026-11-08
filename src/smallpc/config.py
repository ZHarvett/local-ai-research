"""Pydantic schemas and TOML loaders for the machine, model, server and sweep configs.

All models forbid unknown fields. Nothing here touches the file system beyond reading the TOML
file that was asked for: paths (for example the llama-server binary) are only checked at launch.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Profile = Literal["stock", "candidate", "tuned"]
OnOffAuto = Literal["on", "off", "auto"]
OnOff = Literal["on", "off"]
KvType = Literal["f32", "f16", "bf16", "q8_0", "q5_1", "q5_0", "q4_1", "q4_0", "iq4_nl"]
# Accepted values below are taken from `llama-server --help` of the pinned build (WP3,
# data/env/llama-server-help.txt); tests/test_flag_table.py fails if they drift apart.
SpecType = Literal[
    "none",
    "draft-simple",
    "draft-eagle3",
    "draft-mtp",
    "draft-dflash",
    "draft-dspark",
    "ngram-simple",
    "ngram-map-k",
    "ngram-map-k4v",
    "ngram-mod",
    "ngram-cache",
]
LoadMode = Literal["auto", "none", "mmap", "mlock", "mmap+mlock", "dio"]

PosInt = Annotated[int, Field(ge=1)]
NonNegInt = Annotated[int, Field(ge=0)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def repo_root() -> Path:
    """Repository root: $SMALLPC_ROOT, else two levels above ``src/smallpc``."""
    env = os.environ.get("SMALLPC_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def _load_toml(path: str | Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _absolute(value: str) -> str:
    if not os.path.isabs(value):
        raise ValueError(f"must be an absolute path, got {value!r}")
    return value


# --------------------------------------------------------------------------- machine


class MachinePaths(_Strict):
    # Existence is NOT checked here: the build may not exist yet. launch-server.sh checks it.
    llama_server: str
    models_dir: str
    slot_save_dir: str

    @field_validator("llama_server", "models_dir", "slot_save_dir")
    @classmethod
    def _must_be_absolute(cls, v: str) -> str:
        return _absolute(v)


class MachineServer(_Strict):
    host: str = "127.0.0.1"
    port: Annotated[int, Field(ge=1, le=65535)]


class MachineGpu(_Strict):
    index: NonNegInt = 0


class MachineBios(_Strict):
    """Manually recorded BIOS fields (see docs/environment.md)."""

    expo: str | None = None
    igpu: str | None = None
    pbo_eco_mode: str | None = None


class MachineConfig(_Strict):
    paths: MachinePaths
    server: MachineServer
    gpu: MachineGpu = MachineGpu()
    bios: MachineBios = MachineBios()


def load_machine(path: str | Path | None = None) -> MachineConfig:
    return MachineConfig.model_validate(_load_toml(path or repo_root() / "configs/machine.toml"))


# --------------------------------------------------------------------------- model


class SamplingSet(_Strict):
    """One set of sampling settings, with the model card's own wording and where it came from."""

    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    repeat_penalty: float | None = None
    wording: str | None = None  # exactly as the source states it
    source: str | None = None  # URL (with revision) of the source


class Sampling(_Strict):
    """Recommended sampling, one named set per context the source distinguishes.

    The model card gives ``general`` and ``benchmark`` (and no separate thinking, non-thinking or
    coding values); ``generation_config`` is the base repository's generation_config.json.
    """

    general: SamplingSet | None = None
    benchmark: SamplingSet | None = None
    generation_config: SamplingSet | None = None


class BaseRepo(_Strict):
    """The non-GGUF base repository (model card and chat template source)."""

    repo: str | None = None
    revision: str | None = None
    revision_date: str | None = None
    how_identified: str | None = None


class ChatTemplate(_Strict):
    file: str | None = None  # repository-relative path of the official template
    source: str | None = None  # URL (with revision) it was fetched from
    normalized_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    normalization: str | None = None
    embedded_note: str | None = None  # how the template embedded in the GGUF differs, if it does


class ModelConfig(_Strict):
    """Model identity and sampling. Every field is optional (tests use a minimal fixture)."""

    repo: str | None = None
    revision: str | None = None
    revision_date: str | None = None
    file: str | None = None
    size_bytes: PosInt | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    license: str | None = None
    license_source: str | None = None
    base: BaseRepo = BaseRepo()
    chat_template: ChatTemplate = ChatTemplate()
    sampling: Sampling = Sampling()


def load_model(path: str | Path | None = None) -> ModelConfig:
    return ModelConfig.model_validate(_load_toml(path or repo_root() / "configs/model.toml"))


# --------------------------------------------------------------------------- server

# Fields a stock config may set (step plan §3.1: only -m, -c, --host, --port, plus --metrics and
# logging, which do not change inference). Everything else is a validation error.
STOCK_ALLOWED_FIELDS = frozenset(
    {"profile", "model", "context", "host", "port", "metrics", "log_verbosity"}
)

# Sweep defaults (step plan §5.4). Applied to candidate and tuned configs only, never to stock.
SWEEP_DEFAULTS: dict[str, object] = {
    "cache_type_k": "q8_0",
    "cache_type_v": "q8_0",
    "flash_attn": "on",
    "parallel": 1,
}


class ServerConfig(_Strict):
    profile: Profile

    # Identity / endpoint. host, port and model fall back to machine.toml / model.toml.
    model: str | None = None  # file name inside machine models_dir, or an absolute path
    host: str | None = None
    port: Annotated[int, Field(ge=1, le=65535)] | None = None
    context: PosInt | None = None

    # Placement
    fit: OnOff | None = None
    fit_target: NonNegInt | None = None  # MiB
    cpu_moe: bool | None = None
    n_cpu_moe: NonNegInt | None = None
    moe_cache_mib: PosInt | None = None

    # Batching
    batch: PosInt | None = None
    ubatch: PosInt | None = None

    # KV cache and attention
    cache_type_k: KvType | None = None
    cache_type_v: KvType | None = None
    flash_attn: OnOffAuto | None = None
    parallel: PosInt | None = None

    # Speculative decoding
    spec_type: SpecType | None = None
    spec_draft_n_max: PosInt | None = None

    # Misc
    threads: PosInt | None = None
    load_mode: LoadMode | None = None
    metrics: bool | None = None
    slot_save_path: str | None = None
    log_verbosity: Annotated[int, Field(ge=0, le=5)] | None = None

    @field_validator("slot_save_path")
    @classmethod
    def _slot_path(cls, v: str | None) -> str | None:
        return None if v is None else _absolute(v)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.profile == "stock":
            extra = sorted(self.model_fields_set - STOCK_ALLOWED_FIELDS)
            if extra:
                raise ValueError(
                    "a stock config may set only "
                    f"{sorted(STOCK_ALLOWED_FIELDS - {'profile'})}; "
                    f"forbidden field(s) set: {extra}"
                )
        if self.cpu_moe and self.n_cpu_moe is not None:
            raise ValueError("cpu_moe and n_cpu_moe are mutually exclusive")
        if self.fit_target is not None and self.fit == "off":
            raise ValueError("fit_target has no effect with fit = 'off'")
        if self.batch is not None and self.ubatch is not None and self.ubatch > self.batch:
            raise ValueError("ubatch must not exceed batch")
        if self.spec_draft_n_max is not None and self.spec_type in (None, "none"):
            raise ValueError("spec_draft_n_max requires spec_type other than 'none'")
        return self

    def effective(self) -> ServerConfig:
        """Return the config with the §5.4 sweep defaults filled in for candidate/tuned.

        Stock is returned unchanged: it can never inherit a sweep default.
        """
        if self.profile == "stock":
            return self
        fill = {k: v for k, v in SWEEP_DEFAULTS.items() if getattr(self, k) is None}
        return self.model_copy(update=fill)


def load_server(path: str | Path) -> ServerConfig:
    return ServerConfig.model_validate(_load_toml(path))


# --------------------------------------------------------------------------- sweep spec


class SweepCell(_Strict):
    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    config: str = Field(min_length=1)  # path to a server TOML, relative to the repo root


class SweepSpec(_Strict):
    """Minimal sweep spec; WP9 extends it."""

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    cells: Annotated[list[SweepCell], Field(min_length=1)]
    repetitions: PosInt

    @model_validator(mode="after")
    def _unique_cells(self) -> Self:
        names = [c.name for c in self.cells]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate cell name(s): {dupes}")
        return self


def load_sweep(path: str | Path) -> SweepSpec:
    return SweepSpec.model_validate(_load_toml(path))
