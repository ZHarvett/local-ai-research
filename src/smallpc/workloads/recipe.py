"""The workload recipe (``configs/workloads/recipe.toml``) and the pure policies derived from it:
lengths, depths, the variant policy, the context-fit check, nonces and sampling seeds."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..config import repo_root

RECIPE_PATH = "configs/workloads/recipe.toml"
MANIFEST_PATH = "configs/workloads/manifest.json"
CACHE_DIR = "data/cache/workloads"
RESERVE_VARIANT = 5  # warm-up, equivalence and sanity prompts: their own pool, not a sweep variant


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(_Strict):
    name: str
    url: str
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    spdx: str
    language: str
    extension: str
    clone_dir: str
    license_files: list[str]
    defs_pattern: str
    imports_pattern: str


class Exclusions(_Strict):
    special_tokens: str = "from_vocab"
    max_file_bytes: int
    min_file_bytes: int
    max_line_chars: int
    dir_names: list[str]
    name_substrings: list[str]
    generated_markers: list[str]


class Wording(_Strict):
    a: str
    b: str


class Tasks(_Strict):
    a: list[str]
    b: list[str]
    reserve_a: list[str]
    reserve_b: str


class AppendRecipe(_Strict):
    variant: int
    commands: list[list[str]]


class Prompt(_Strict):
    system: str
    assistant_stub: str


class Recipe(_Strict):
    schema_version: int = Field(alias="schema")
    seed: str
    K: int
    variants: int
    append_tokens: int
    n_predict_b: int
    short_gen_tokens: int
    lengths_k: list[int]
    depths_k: list[int]
    short_k: int
    warmup_k: int
    sanity_k: int
    equiv_k: list[int]
    contexts: dict[str, list[int]]
    tokenize: dict[str, bool]
    exclusions: Exclusions
    sources: list[Source]
    prompt: Prompt
    chosen: dict[str, list[str]]
    wordings: dict[str, Wording]
    tasks: Tasks
    appends: list[AppendRecipe]

    # -- derived
    def tokens(self, k: int) -> int:
        return k * self.K

    @property
    def depths(self) -> list[int]:
        return [self.tokens(k) for k in self.depths_k]

    def depths_for_context(self, context: int) -> list[int]:
        return [self.tokens(k) for k in self.contexts[str(context)]]

    def wording_for(self, variant: int) -> str:
        """Wording id chosen for a variant (the reserve variant uses variant 0's)."""
        return self.chosen["wording"][variant if variant < self.variants else 0]

    def instruction(self, side: str, variant: int, index: int = 0) -> str:
        """Instruction text. ``side`` is "a" (user message of the prompt) or "b" (Request B)."""
        wording = getattr(self.wordings[self.wording_for(variant)], side)
        if variant < self.variants:
            task = (self.tasks.a if side == "a" else self.tasks.b)[variant]
        elif side == "a":
            task = self.tasks.reserve_a[index % len(self.tasks.reserve_a)]
        else:
            task = self.tasks.reserve_b
        return wording.format(task=task)


def load_recipe(path: str | Path | None = None) -> Recipe:
    p = Path(path) if path else repo_root() / RECIPE_PATH
    with open(p, "rb") as f:
        return Recipe.model_validate(tomllib.load(f))


# ------------------------------------------------------------------------------ pure policies


def variant_for(repetition: int, variants: int = 5) -> int:
    """Variant policy: repetition r uses variant r mod 5."""
    return repetition % variants


def fits(d: int, context: int, append: int = 3000, n_predict: int = 400) -> bool:
    """Context-fit check: a depth-d pair needs d + 3,000 + 400 tokens."""
    return d + append + n_predict <= context


def _digest(seed: str, what: str, kind: str, variant: int, length: int, repetition: int) -> str:
    return hashlib.sha256(
        f"{seed}|{what}|{kind}|{variant}|{length}|{repetition}".encode()
    ).hexdigest()


def nonce(seed: str, kind: str, variant: int, length: int, repetition: int) -> str:
    """Per-request nonce: deterministic from the fixed seed and the request's kind, variant,
    length and repetition; unique for every distinct request of a sweep."""
    return f"[nonce {_digest(seed, 'nonce', kind, variant, length, repetition)[:16]}]"


def sampling_seed(seed: str, kind: str, variant: int, length: int, repetition: int) -> int:
    return int(_digest(seed, "seed", kind, variant, length, repetition)[:8], 16) % 2**31


def plan_sweep(recipe: Recipe, repetitions: int = 5) -> list[tuple[str, int, int, int]]:
    """Every fresh request of a full sweep as (kind, variant, length, repetition): per repetition
    the short point and a Request A per depth of every context, plus the two warm-up requests.
    Request B carries its A's nonce, so it is not a fresh request."""
    keys: list[tuple[str, int, int, int]] = []
    depths = sorted({d for c in recipe.contexts for d in recipe.depths_for_context(int(c))})
    for r in range(repetitions):
        v = variant_for(r, recipe.variants)
        keys.append(("short", v, recipe.tokens(recipe.short_k), r))
        keys.extend(("A", v, d, r) for d in depths)
    keys.extend(("warmup", RESERVE_VARIANT, recipe.tokens(recipe.warmup_k), r) for r in range(2))
    return keys


def depths_for_context(context: int) -> list[int]:
    """Depths (tokens) of the §5.3 table for a context size (32768, 65536 or 131072)."""
    return load_recipe().depths_for_context(context)
