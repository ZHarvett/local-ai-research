"""Builds prompts and Request A / Request B pairs from the recipe, and regenerates them from the
manifest records. The same text-assembly functions serve both, so ``verify`` reproduces what
``build`` wrote.

Prompt text (ChatML, as the embedded template renders it; checked against the real renderer):

    <|im_start|>system\\n{nonce}\\n{system prompt}<|im_end|>\\n
    <|im_start|>user\\n{files}\\n{instruction}<|im_end|>\\n
    [<|im_start|>assistant\\n<think>\\n]     single-turn kinds only (the generation prompt)

Request B appends an assistant stub, the tool-like output (a ``tool`` message) and a final user
instruction, then the generation prompt, so that exactly ``append_tokens`` tokens are added.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .manifest import (
    AppendRecord,
    FileUse,
    PromptRecord,
    append_id,
    prompt_id,
)
from .packing import PackingError, Unit, largest_fit, pack_exact, tail_text
from .recipe import Recipe, nonce, sampling_seed
from .sources import (
    N_POOLS,
    Corpus,
    FileInfo,
    command_lines,
    file_units,
    repo_header,
)
from .tokens import SENT_SYS, SENT_TOOL, SENT_USER, Renderer, Tokenizer, tokens_sha256

GEN_KINDS = {
    "short",
    "warmup",
    "sanity",
    "equiv",
}  # single-turn kinds end with the generation prompt
RESERVE_KINDS = {"warmup", "sanity", "equiv"}
RETRY_SECTIONS = 8  # shrink the first section by up to this many units if the second cannot fit
SLACK = 1.3  # candidate lines per section: this factor times the estimated need


def reserve_index_for(kind: str, repetition: int) -> int:
    """Which reserve task a warm-up, equivalence or sanity prompt uses (sanity prompts differ)."""
    return repetition if kind == "sanity" else 0


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def join_sections(first: str, second: str) -> str:
    """Join the two repository sections (a blank line between them)."""
    return first + "\n" + second if first and second else first or second


def user_text(files: str, instruction: str) -> str:
    """The user message: files, a blank line, then the instruction."""
    return files + ("" if files.endswith("\n") or not files else "\n") + "\n" + instruction


def _split_around(text: str, sentinels: list[str]) -> list[str]:
    parts = []
    for s in sentinels:
        if text.count(s) != 1:
            raise ValueError(
                f"sentinel {s!r} appears {text.count(s)} times in the rendered template"
            )
        head, text = text.split(s)
        parts.append(head)
    return [*parts, text]


@dataclass
class Skeleton:
    """Rendered chat template split around the content slots, so packing can assemble text
    locally (and the result is compared with the real renderer once per prompt)."""

    plain: list[str]  # [p0, p1, p2]: p0 + system + p1 + user + p2, no generation prompt
    gen: list[str]  # the same with the generation prompt
    b: dict[int, list[str]] = field(
        default_factory=dict
    )  # variant -> [q0..q3] around system, user, tool

    @classmethod
    def probe(cls, renderer: Renderer, recipe: Recipe) -> Skeleton:
        base = [{"role": "system", "content": SENT_SYS}, {"role": "user", "content": SENT_USER}]
        skel = cls(
            plain=_split_around(renderer.render(base, False), [SENT_SYS, SENT_USER]),
            gen=_split_around(renderer.render(base, True), [SENT_SYS, SENT_USER]),
        )
        for v in range(recipe.variants):
            msgs = [
                *base,
                {"role": "assistant", "content": recipe.prompt.assistant_stub},
                {"role": "tool", "content": SENT_TOOL},
                {"role": "user", "content": recipe.instruction("b", v)},
            ]
            skel.b[v] = _split_around(renderer.render(msgs, True), [SENT_SYS, SENT_USER, SENT_TOOL])
        return skel

    def prompt_text(self, system: str, user: str, gen: bool) -> str:
        p = self.gen if gen else self.plain
        return p[0] + system + p[1] + user + p[2]

    def append_text(self, variant: int, tool: str) -> str:
        """Text B adds after Request A's text (A has no generation prompt)."""
        q, p = self.b[variant], self.plain
        if q[0] != p[0] or q[1] != p[1] or not q[2].startswith(p[2]):
            raise ValueError("Request A's text is not a prefix of Request B's rendering")
        return q[2][len(p[2]) :] + tool + q[3]


@dataclass
class BuiltPrompt:
    record: PromptRecord
    text: str
    tokens: list[int]
    system: str = ""  # message contents, kept for the real-renderer checks
    user: str = ""


@dataclass
class BuiltAppend:
    record: AppendRecord
    text: str
    tokens: list[int]
    tool: str = ""


@dataclass
class Pair:
    a: BuiltPrompt
    append: BuiltAppend
    b_record: PromptRecord
    b_text: str
    b_tokens: list[int]


class Builder:
    def __init__(
        self,
        recipe: Recipe,
        corpus: Corpus,
        tok: Tokenizer,
        renderer: Renderer,
        pools: dict[str, list[list[FileInfo]]],
        specials: list[str],
    ):
        self.recipe, self.corpus, self.tok, self.renderer = recipe, corpus, tok, renderer
        self.pools, self.specials = pools, specials
        self.skeleton = Skeleton.probe(renderer, recipe)
        self.names = [s.name for s in recipe.sources]

    # ------------------------------------------------------------------ text from file uses
    def section_text(self, name: str, uses: list[FileUse]) -> str:
        """Text of one repository section from its file list (header on the first file)."""
        src = self.corpus.sources[name]
        text = ""
        for i, u in enumerate(uses):
            units = file_units(
                u.path, self.corpus.lines(name, u.path), repo_header(src) if i == 0 else ""
            )
            text += tail_text(units, u.lines, u.partial_chars)
        return text

    def files_text(self, files: dict[str, list[FileUse]]) -> str:
        parts = [self.section_text(n, files[n]) if files.get(n) else "" for n in self.names]
        return join_sections(parts[0], parts[1])

    def system_text(self, nonce_text: str) -> str:
        return nonce_text + "\n" + self.recipe.prompt.system

    def instruction_for(self, variant: int, index: int) -> str:
        return self.recipe.instruction("a", variant, index)

    # ------------------------------------------------------------------------- packing
    def _candidates(
        self, name: str, pool: list[FileInfo], start: int, need_tokens: int
    ) -> tuple[list[Unit], list[tuple[str, int]]]:
        """Units of whole pool files from ``start`` until about ``need_tokens`` tokens, and the
        (path, file index) owner of each unit."""
        src = self.corpus.sources[name]
        units, owners, total = [], [], 0
        for idx in range(start, len(pool)):
            fi = pool[idx]
            fu = file_units(
                fi.path, self.corpus.lines(name, fi.path), repo_header(src) if not units else ""
            )
            units.extend(fu)
            owners.extend([(fi.path, idx)] * len(fu))
            total += fi.tokens
            if total >= need_tokens:
                break
        return units, owners

    @staticmethod
    def _uses(owners: list[tuple[str, int]], n: int, k: int) -> tuple[list[FileUse], int]:
        """File uses for the first ``n`` units plus ``k`` characters of the next, and the index of
        the last pool file touched."""
        counts: dict[str, int] = {}
        order: list[str] = []
        last = -1
        for path, idx in owners[:n]:
            if path not in counts:
                order.append(path)
                counts[path] = 0
            counts[path] += 1
            last = idx
        uses = [FileUse(path=p, lines=counts[p]) for p in order]
        if k:
            path, idx = owners[n]
            last = idx
            if uses and uses[-1].path == path:
                uses[-1] = FileUse(path=path, lines=counts[path], partial_chars=k)
            else:
                uses.append(FileUse(path=path, lines=0, partial_chars=k))
        return uses, last

    def _pack_files(
        self, variant_pool: int, starts: dict[str, int], target: int, render, count
    ) -> tuple[dict[str, list[FileUse]], dict[str, int]]:
        """Pick files from the two repositories (about half each) so that
        ``count(render(files_text)) == target``. Returns the file uses and the next free file
        index per repository."""
        first, second = self.names
        base = count(render(""))
        half = max((target - base) // 2, 1)
        need0 = int(half * SLACK) + 64
        u0, o0 = self._candidates(
            first, self.pools[first][variant_pool], starts.get(first, 0), need0
        )
        n0_max = largest_fit(len(u0), lambda m: count(render(tail_text(u0, m))) - base <= half)
        for n0 in range(n0_max, max(n0_max - RETRY_SECTIONS, -1), -1):
            uses0, last0 = self._uses(o0, n0, 0)
            s0 = tail_text(u0, n0)
            used0 = count(render(s0)) - base
            need1 = int((target - base - used0) * SLACK) + 64
            u1, o1 = self._candidates(
                second, self.pools[second][variant_pool], starts.get(second, 0), need1
            )
            if n0 < 1:
                break  # both repositories must appear in every prompt
            try:
                n1, k1 = pack_exact(
                    u1, lambda t, s0=s0: render(join_sections(s0, t)), count, target
                )
            except PackingError:
                continue  # give the second section more room by shrinking the first
            if n1 == 0 and k1 == 0:
                continue
            uses1, last1 = self._uses(o1, n1, k1)
            return {first: uses0, second: uses1}, {first: last0 + 1, second: last1 + 1}
        raise PackingError(f"cannot reach exactly {target} tokens")

    # --------------------------------------------------------------------- prompts
    def build_prompt(
        self,
        kind: str,
        variant: int,
        length: int,
        repetition: int,
        *,
        reserve_index: int = 0,
        starts: dict[str, int] | None = None,
    ) -> tuple[BuiltPrompt, dict[str, int]]:
        """Build one prompt of exactly ``length`` tokens. Returns it and the next free pool file
        index per repository (used to place later reserve prompts on different files)."""
        r = self.recipe
        gen = kind in GEN_KINDS
        n = nonce(r.seed, kind, variant, length, repetition)
        system = self.system_text(n)
        instruction = self.instruction_for(variant, reserve_index)
        pool = N_POOLS - 1 if kind in RESERVE_KINDS else variant

        def render(files: str) -> str:
            return self.skeleton.prompt_text(system, user_text(files, instruction), gen)

        uses, nxt = self._pack_files(pool, starts or {}, length, render, self.tok.count)
        text = render(self.files_text(uses))
        tokens = self.tok.tokenize(text)
        if len(tokens) != length:
            raise PackingError(f"{kind} v{variant} {length}: built {len(tokens)} tokens")
        user = user_text(self.files_text(uses), instruction)
        self._check_real_render(system, user, gen, text)
        rec = PromptRecord(
            id=prompt_id(kind, variant, length, repetition),
            kind=kind,
            variant=variant,
            length=length,
            repetition=repetition,
            nonce=n,
            seed=sampling_seed(r.seed, kind, variant, length, repetition),
            wording=r.wording_for(variant),
            instruction_sha256=sha256_text(instruction),
            generation_prompt=gen,
            files=uses,
            pool=pool,
            start_file=dict(starts) if starts else None,
            token_count=len(tokens),
            text_sha256=sha256_text(text),
            tokens_sha256=tokens_sha256(tokens),
        )
        return BuiltPrompt(rec, text, tokens, system, user), nxt

    def _check_real_render(self, system: str, user: str, gen: bool, text: str) -> None:
        real = self.renderer.render(
            [{"role": "system", "content": system}, {"role": "user", "content": user}], gen
        )
        if real != text:
            raise ValueError("locally assembled text differs from the chat template's rendering")

    def regenerate_prompt(self, rec: PromptRecord) -> tuple[str, str, str]:
        """(text, system, user) of a manifest prompt record, from its file list (no packing)."""
        system = self.system_text(rec.nonce or "")
        index = reserve_index_for(rec.kind, rec.repetition)
        instruction = self.recipe.instruction("a", rec.variant, index)
        user = user_text(self.files_text(rec.files or {}), instruction)
        return self.skeleton.prompt_text(system, user, bool(rec.generation_prompt)), system, user

    def regenerate_prompt_text(self, rec: PromptRecord) -> str:
        return self.regenerate_prompt(rec)[0]

    # --------------------------------------------------------------------- appends
    def build_append(self, variant: int) -> BuiltAppend:
        r = self.recipe
        recipe_cmds = next(a for a in r.appends if a.variant == variant).commands
        max_line = r.exclusions.max_line_chars
        per_repo: dict[str, list[Unit]] = {}
        dropped = 0
        for name in self.names:
            lines, d = command_lines(
                self.corpus, self.corpus.sources[name], recipe_cmds, self.specials, max_line
            )
            dropped += d
            per_repo[name] = [Unit(body=ln if ln.endswith("\n") else ln + "\n") for ln in lines]
        target = r.append_tokens

        def render(tool: str) -> str:
            return self.skeleton.append_text(variant, tool)

        def count(text: str) -> int:
            return self.tok.count(text, bos=False)

        first, second = self.names
        base = count(render(""))
        half = max((target - base) // 2, 1)
        u0, u1 = per_repo[first], per_repo[second]
        n0_max = largest_fit(len(u0), lambda m: count(render(tail_text(u0, m))) - base <= half)
        for n0 in range(n0_max, max(n0_max - RETRY_SECTIONS, -1), -1):
            s0 = tail_text(u0, n0)
            try:
                n1, k1 = pack_exact(
                    u1, lambda t, s0=s0: render(join_sections(s0, t)), count, target
                )
                break
            except PackingError:
                continue
        else:
            raise PackingError(f"append v{variant}: cannot reach exactly {target} tokens")
        files = {
            first: [FileUse(path="commands", lines=n0)],
            second: [FileUse(path="commands", lines=n1, partial_chars=k1)],
        }
        tool = self.append_tool_text(variant, files)
        text = render(tool)
        tokens = self.tok.tokenize(text, bos=False)
        if len(tokens) != target:
            raise PackingError(f"append v{variant}: built {len(tokens)} tokens, expected {target}")
        instruction = r.instruction("b", variant)
        rec = AppendRecord(
            id=append_id(variant),
            variant=variant,
            commands=recipe_cmds,
            files=files,
            wording=r.wording_for(variant),
            instruction_sha256=sha256_text(instruction),
            dropped_lines=dropped,
            token_count=len(tokens),
            text_sha256=sha256_text(text),
            tokens_sha256=tokens_sha256(tokens),
        )
        return BuiltAppend(rec, text, tokens, tool)

    def append_tool_text(self, variant: int, files: dict[str, list[FileUse]]) -> str:
        """Tool-output text of an append record: command output lines of both repositories."""
        r = self.recipe
        cmds = next(a for a in r.appends if a.variant == variant).commands
        parts = []
        for name in self.names:
            lines, _ = command_lines(
                self.corpus,
                self.corpus.sources[name],
                cmds,
                self.specials,
                r.exclusions.max_line_chars,
            )
            units = [Unit(body=ln if ln.endswith("\n") else ln + "\n") for ln in lines]
            use = files[name][0]
            parts.append(tail_text(units, use.lines, use.partial_chars))
        return join_sections(parts[0], parts[1])

    def regenerate_append(self, rec: AppendRecord) -> tuple[str, str]:
        """(text, tool output) of a manifest append record."""
        tool = self.append_tool_text(rec.variant, rec.files)
        return self.skeleton.append_text(rec.variant, tool), tool

    def regenerate_append_text(self, rec: AppendRecord) -> str:
        return self.regenerate_append(rec)[0]

    # ---------------------------------------------------------------------- pairs
    def make_pair(self, a: BuiltPrompt, append: BuiltAppend) -> Pair:
        """Request B = Request A's tokens + the append tokens, with the prefix property checked
        on the real renderer and the whole-text tokenization."""
        b_text = a.text + append.text
        b_tokens = a.tokens + append.tokens
        self._check_pair(a, append, b_text, b_tokens)
        rec = a.record
        length = rec.length
        b_rec = PromptRecord(
            id=prompt_id("B", rec.variant, length, rec.repetition),
            kind="B",
            variant=rec.variant,
            length=length + self.recipe.append_tokens,
            repetition=rec.repetition,
            nonce=rec.nonce,
            seed=sampling_seed(self.recipe.seed, "B", rec.variant, length, rec.repetition),
            wording=self.recipe.wording_for(rec.variant),
            generation_prompt=True,
            a_id=rec.id,
            append_id=append.record.id,
            token_count=len(b_tokens),
            text_sha256=sha256_text(b_text),
            tokens_sha256=tokens_sha256(b_tokens),
        )
        return Pair(a, append, b_rec, b_text, b_tokens)

    def _check_pair(
        self, a: BuiltPrompt, append: BuiltAppend, b_text: str, b_tokens: list[int]
    ) -> None:
        r = self.recipe
        v = a.record.variant
        real_b = self.renderer.render(
            [
                {"role": "system", "content": a.system},
                {"role": "user", "content": a.user},
                {"role": "assistant", "content": r.prompt.assistant_stub},
                {"role": "tool", "content": append.tool},
                {"role": "user", "content": r.instruction("b", v)},
            ],
            True,
        )
        if real_b != b_text:
            raise PackingError("the real renderer's text for B differs from A's text + the append")
        d = a.record.length
        if len(a.tokens) != d or len(append.tokens) != self.recipe.append_tokens:
            raise PackingError("pair lengths are not d and the append size")
        if b_tokens[:d] != a.tokens:
            raise PackingError("Request A's tokens are not a prefix of Request B's")
        whole = self.tok.tokenize(b_text)
        if whole != b_tokens:
            raise PackingError(
                f"tokenizing B whole ({len(whole)} tokens) differs from A + append "
                f"({len(b_tokens)} tokens)"
            )
