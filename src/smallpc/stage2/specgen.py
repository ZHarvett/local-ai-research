"""Stage 2 sweep specs (plan v1.6 section 5.4), generated from the Stage 1 shortlist.

``python -m smallpc.stage2 spec --stage 2f|2a|2a2|2b|2c|2d --out configs/sweeps/<name>.toml``

The output is an ordinary sweep spec (the format of ``configs/sweeps/stage1.toml``): ``python -m
smallpc.sweep check`` and ``scripts/run-sweep.sh`` work on it unchanged. The Stage 1 ``context``,
``batch`` and ``placement`` axes are copied from the Stage 1 spec; the Stage 2 settings are new axes
(plain override dicts, so the config schema needs nothing new):

* ``mtp``:  ``mtp0 = {}``, ``mtp1..3 = {spec_type = "draft-mtp", spec_draft_n_max = N}``
* ``cram``: ``cram8192 = {cache_ram = 8192}`` ...
* ``kv``:   ``kvq8 = {}`` (8-bit KV is the section 5.4 sweep default, applied at render time) and
            ``kvf16 = {cache_type_k = "f16", cache_type_v = "f16"}`` (explicit: the argv says
            ``-ctk f16 -ctv f16``)
* ``load``: ``lmauto`` and ``lm<LOAD_MODE_ALT>``
* ``thr``:  ``t8 = {threads = 8}`` and ``tdef = {}``

Cell names are ``s2<stage>-<placement>-<context>-<batch>-mtp<n>[-<changed setting>]``; they never
equal a Stage 1 name and are unique within a spec. A spec written for functional tests carries the
``ft-`` prefix in its name and a "FUNCTIONAL-TEST" line in its header;
``smallpc.stage2.decide`` refuses such sessions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import repo_root
from . import rules
from .shortlist import Entry, Shortlist, load_shortlist

FT_PREFIX = "ft-"  # session id and spec name prefix of functional-test runs
FT_LINE = "FUNCTIONAL-TEST SPEC: a check of the tooling, never a result."
REPETITIONS = 5
CRAM_2F = {"128K": (8192, 4096, 2048, 0), "64K": (8192, 2048)}
CRAM_DEFAULT = 8192  # llama-server's --cache-ram default (help text of the pinned build)
DRAFT_LENGTHS = (1, 2, 3)
# 2c: the one alternative to `--load-mode auto` (chosen in WP12 part 1, docs/decisions.md;
# pinned by tests/test_stage2_spec.py)
LOAD_MODE_ALT = "dio"
THREADS_EXPLICIT = 8
NO_VALUE = "default"  # --cache-ram default: do not set the flag


class SpecGenError(ValueError):
    """The spec cannot be generated from the given inputs; the message says what to supply."""


class NotNeeded(SpecGenError):
    """The stage is not needed (2d with the default thread count); the command exits with 3."""


@dataclass
class SpecPlan:
    name: str
    header: list[str]
    repetitions: int
    shuffle_seed: int
    max_restarts: int
    defaults: dict[str, Any]
    axes: dict[str, dict[str, dict[str, Any]]]
    blocks: list[dict[str, Any]]
    canary: dict[str, Any] | None
    expect_cells: int = 0


@dataclass(frozen=True)
class CachePolicy:
    """The chosen ``--cache-ram``: ``value`` None means the default stays (flag not set)."""

    value: int | None
    source: str

    def text(self) -> str:
        v = (
            f"{self.value} MiB (explicit --cache-ram)"
            if self.value is not None
            else (f"not set (llama-server default {CRAM_DEFAULT} MiB)")
        )
        return f"{v}; source: {self.source}"


# ----------------------------------------------------------------------------- TOML emitter


def _val(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list | tuple):
        return "[" + ", ".join(_val(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {_val(x)}" for k, x in v.items()) + " }" if v else "{}"
    raise TypeError(f"cannot write {v!r} as TOML")


def emit(plan: SpecPlan) -> str:
    out = [f"# {line}" if line else "#" for line in plan.header]
    out += [
        f"name = {_val(plan.name)}",
        f"repetitions = {plan.repetitions}",
        f"shuffle_seed = {plan.shuffle_seed}",
        f"max_restarts = {plan.max_restarts}",
        f"expect_cells = {plan.expect_cells}",
        "",
        "# Candidate cells get [defaults]; the section 5.4 sweep defaults (-ctk/-ctv q8_0, -fa on,",
        "# -np 1) are applied by ServerConfig.effective() when the argv is rendered; --port comes",
        "# from machine.toml.",
        "[defaults]",
    ]
    out += [f"{k} = {_val(v)}" for k, v in plan.defaults.items()]
    out += ["[stock_defaults]", "metrics = true", "log_verbosity = 4", ""]
    for axis, values in plan.axes.items():
        out.append(f"[axes.{axis}]")
        width = max(len(k) for k in values)
        out += [f"{k.ljust(width)} = {_val(v)}" for k, v in values.items()]
    out.append("")
    for b in plan.blocks:
        if b.get("comment"):
            out += [f"# {line}" for line in b["comment"]]
        out += [
            "[[cells]]",
            f"name = {_val(b['name'])}",
            f"profile = {_val(b['profile'])}",
            "product = { " + ", ".join(f"{a} = {_val(v)}" for a, v in b["product"].items()) + " }",
            "",
        ]
    if plan.canary:
        c = plan.canary
        out += [
            "[canary]",
            f"cell = {_val(c['cell'])}",
            f"repetitions = {c['repetitions']}",
            f"points = {_val(c['points'])}",
        ]
    return "\n".join(out).rstrip("\n") + "\n"


# ----------------------------------------------------------------------------- building blocks


def _stage1_axes(sl: Shortlist, entries: list[Entry]) -> dict[str, dict[str, dict[str, Any]]]:
    """The Stage 1 context, batch and placement axis values the entries use, copied verbatim."""
    axes = sl.spec.axes  # type: ignore[attr-defined]
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for axis, attr in (("context", "context"), ("batch", "batch"), ("placement", "placement")):
        used = sorted({getattr(e, attr) for e in entries})
        order = list(axes[axis])  # keep the Stage 1 order
        out[axis] = {k: dict(axes[axis][k]) for k in order if k in used}
    return out


def _mtp_axis(ns: list[int]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {"mtp0": {}}
    for n in ns:
        if n:
            out[f"mtp{n}"] = {"spec_type": "draft-mtp", "spec_draft_n_max": n}
    return out


def _block(
    stage: str,
    entry: Entry,
    mtps: list[str],
    extra: dict[str, list[str]] | None = None,
    comment: list[str] | None = None,
) -> dict[str, Any]:
    extra = extra or {}
    template = f"s{stage}-{{placement}}-{{context}}-{{batch}}-{{mtp}}" + "".join(
        f"-{{{a}}}" for a in extra
    )
    return {
        "name": template,
        "profile": "candidate",
        "product": {
            "placement": [entry.placement],
            "context": [entry.context],
            "batch": [entry.batch],
            "mtp": mtps,
            **extra,
        },
        "comment": comment,
    }


def cell_name(stage: str, entry: Entry, mtp: int, changed: str | None = None) -> str:
    return f"s{stage}-{entry.placement}-{entry.context}-{entry.batch}-mtp{mtp}" + (
        f"-{changed}" if changed else ""
    )


def _header(
    sl: Shortlist, root: Path, stage: str, title: str, cache: CachePolicy | None,
    command: str, extra: list[str] | None = None, ft: bool = False,
) -> list[str]:  # fmt: skip
    h = [f"Stage 2 {title} (plan v{rules.plan_version(root)}, WP12), generated by `{command}`."]
    h.append("Generated file: change the inputs and regenerate; never edit by hand.")
    if ft:
        h.append(FT_LINE)
    h += [
        f"Shortlist: {sl.path} sha256 {sl.sha256}",
        f"Stage 1 spec (axes, canary): {sl.spec_path} sha256 {sl.spec_sha256}",
        f"cache_ram: {cache.text() if cache else 'varied by the cells of this stage (2f)'}",
    ]
    h += extra or []
    h.append("Rules applied by `python -m smallpc.stage2 decide` (plan text, verbatim):")
    for text in rules.RULES_BY_STAGE[stage]:
        h += [f"  {line}" if line else "" for line in text.split("\n")]
    return h


def _defaults(cache: CachePolicy | None) -> dict[str, Any]:
    d: dict[str, Any] = {"metrics": True, "log_verbosity": 4}
    if cache is not None and cache.value is not None:
        d["cache_ram"] = cache.value
    return d


def _finish(sl: Shortlist, plan: SpecPlan, ft: bool) -> SpecPlan:
    c = sl.spec.canary  # type: ignore[attr-defined]
    plan.canary = (
        None
        if ft
        else {"cell": dict(c.cell), "repetitions": c.repetitions, "points": list(c.points)}
    )
    return plan


def _count(plan: SpecPlan) -> int:
    n = 0
    for b in plan.blocks:
        k = 1
        for v in b["product"].values():
            k *= len(v)
        n += k
    return n


def _new_plan(
    sl: Shortlist, ft: bool, stage: str, header: list[str], defaults, axes, blocks
) -> SpecPlan:
    s1 = sl.spec
    plan = SpecPlan(
        name=("ft-" if ft else "stage2-") + stage,
        header=header,
        repetitions=1 if ft else REPETITIONS,
        shuffle_seed=s1.shuffle_seed,  # type: ignore[attr-defined]
        max_restarts=s1.max_restarts,  # type: ignore[attr-defined]
        defaults=defaults,
        axes=axes,
        blocks=blocks,
        canary=None,
    )
    plan.expect_cells = _count(plan)
    return _finish(sl, plan, ft)


# ----------------------------------------------------------------------------- stages


def build_2f(sl: Shortlist, root: Path, command: str, ft: bool = False) -> SpecPlan:
    """The host prompt cache: the top placement at 128K (8192, 4096, 2048, 0) and at 64K (8192,
    2048), MTP off, ``--cache-ram`` explicit on every cell."""
    table = {"32K": (8192, 0)} if ft else CRAM_2F
    entries = [sl.top(ctx) for ctx in table]
    values = sorted({v for vs in table.values() for v in vs}, reverse=True)
    axes = _stage1_axes(sl, entries)
    axes["mtp"] = {"mtp0": {}}
    axes["cram"] = {f"cram{v}": {"cache_ram": v} for v in values}
    blocks = [
        _block("2f", sl.top(ctx), ["mtp0"], {"cram": [f"cram{v}" for v in vs]})
        for ctx, vs in table.items()
    ]
    header = _header(sl, root, "2f", "2f host prompt cache (--cache-ram)", None, command, ft=ft)
    return _new_plan(sl, ft, "2f", header, _defaults(None), axes, blocks)


def build_2a(
    sl: Shortlist, root: Path, cache: CachePolicy, command: str, ft: bool = False
) -> SpecPlan:
    """MTP: per context both shortlisted placements with MTP off, and the top placement with draft
    lengths 1, 2 and 3 (five cells per context). Functional-test preset: 32K, top placement at
    draft lengths 1 and 3, plus a P6 cell at draft length 2 if the top placement is not P6."""
    contexts = ["32K"] if ft else list(sl.contexts)
    ns = (1, 3) if ft else DRAFT_LENGTHS
    entries: list[Entry] = []
    blocks: list[dict[str, Any]] = []
    p6_extra = False
    for ctx in contexts:
        top, second = sl.top(ctx), sl.second(ctx)
        entries += [top] if ft else [top, second]
        mt = ["mtp0"] * (0 if ft else 1) + [f"mtp{n}" for n in ns]
        blocks.append(_block("2a", top, mt))
        if not ft:
            blocks.append(_block("2a", second, ["mtp0"]))
        elif top.placement != "P6":
            p6 = _p6_entry(sl, ctx)
            p6_extra = True
            entries.append(p6)
            blocks.append(
                _block(
                    "2a",
                    p6,
                    ["mtp2"],
                    comment=["functional test: exercises the max-fit probe with MTP on"],
                )
            )
    axes = _stage1_axes(sl, entries)
    axes["mtp"] = _mtp_axis(sorted(set(ns) | ({2} if p6_extra else set())))
    header = _header(sl, root, "2a", "2a MTP (draft lengths 1 to 3)", cache, command, ft=ft)
    return _new_plan(sl, ft, "2a", header, _defaults(cache), axes, blocks)


def _p6_entry(sl: Shortlist, ctx: str) -> Entry:
    for e in (*sl.contexts[ctx],):
        if e.placement == "P6":
            return e
    axes = sl.spec.axes  # type: ignore[attr-defined]
    if "P6" not in axes["placement"]:
        raise SpecGenError("the Stage 1 spec has no P6 placement")
    return Entry(f"P6-{ctx}-{sl.top(ctx).batch}", "P6", ctx, sl.top(ctx).batch)


@dataclass(frozen=True)
class ContextResult:
    """One context of a 2a result, as ``decide --stage 2a`` writes it (the 2a2 input)."""

    context: str
    top: Entry
    second: Entry
    top_mtp: int  # draft length of the top placement's 2a-best configuration (0 = MTP off)
    second_mtp: int | None  # draft length of the second placement's MTP cell (None: no MTP cell)
    # draft lengths the second placement is tested at besides MTP off: the best draft length of
    # this context, or (no eligible MTP cell in the top placement) those borrowed from others
    second_mtps: tuple[int, ...] = ()
    borrowed: bool = False


def read_2a_result(path: Path, sl: Shortlist) -> dict[str, ContextResult]:
    data = json.loads(Path(path).read_text())
    if data.get("stage") != "2a" or "contexts" not in data:
        raise SpecGenError(f"{path} is not a 2a decision file (stage {data.get('stage')!r})")
    out: dict[str, ContextResult] = {}
    for ctx, block in data["contexts"].items():
        inp = block.get("input_2a2")
        if not inp:
            raise SpecGenError(
                f"{path}: context {ctx} has no 2a2 input (the 2a decision was incomplete)"
            )
        top, second = sl.top(ctx), sl.second(ctx)
        if (inp["top_cell"], inp["second_cell"]) != (top.cell, second.cell):
            raise SpecGenError(
                f"{path}: context {ctx} was decided for {inp['top_cell']}/{inp['second_cell']}, "
                f"but the shortlist now says {top.cell}/{second.cell}"
            )
        if "second_mtps" in inp:
            mtps = tuple(int(n) for n in inp["second_mtps"])
        else:  # a 2a result written before the borrowing rule
            mtps = (int(inp["second_mtp"]),) if inp.get("second_mtp") else ()
        borrowed = bool(inp.get("borrowed_draft_lengths"))
        if inp.get("best_n_reason") and not mtps:
            raise SpecGenError(
                f"{path}: context {ctx} has no eligible MTP cell and no draft length to borrow"
            )
        out[ctx] = ContextResult(
            ctx, top, second, int(inp["top_mtp"]), inp.get("second_mtp"), mtps, borrowed
        )
    return out


def build_2a2(
    sl: Shortlist, root: Path, cache: CachePolicy, result: dict[str, ContextResult], command: str,
    anchor: bool = True,
) -> SpecPlan:  # fmt: skip
    """The second placement with MTP off and with the best draft length of its context, plus (the
    anchor) the top placement's 2a-best configuration re-run, so the comparisons are inside one
    session."""
    entries: list[Entry] = []
    blocks: list[dict[str, Any]] = []
    ns: set[int] = set()
    for r in result.values():
        entries += [r.top, r.second]
        mt = ["mtp0"] + [f"mtp{n}" for n in r.second_mtps if n]
        ns |= {*r.second_mtps, r.top_mtp, 0}
        blocks.append(
            _block(
                "2a2",
                r.second,
                mt,
                comment=(
                    [
                        f"{r.top.cell} has no eligible MTP cell: the draft lengths that won in the "
                        f"other contexts are borrowed: {list(r.second_mtps)}"
                    ]
                    if r.borrowed
                    else None
                ),
            )
        )
        if anchor:
            what = (
                "the top placement with MTP off (it has no eligible MTP cell)"
                if r.borrowed
                else "the 2a-best configuration"
            )
            blocks.append(
                _block(
                    "2a2",
                    r.top,
                    [f"mtp{r.top_mtp}"],
                    comment=[f"anchor: {what} of {r.top.cell}, re-run in this session"],
                )
            )
    axes = _stage1_axes(sl, entries)
    axes["mtp"] = _mtp_axis(sorted(ns))
    extra = [
        "2a input: second placement draft length per context: "
        + ", ".join(
            f"{c}={','.join(map(str, r.second_mtps)) or 'none'}"
            + (" (borrowed)" if r.borrowed else "")
            for c, r in result.items()
        ),
        f"anchor cells: {'yes' if anchor else 'no'}",
    ]
    header = _header(
        sl,
        root,
        "2a2",
        "2a2 (second placement with MTP, and its comparators)",
        cache,
        command,
        extra,
    )
    return _new_plan(sl, False, "2a2", header, _defaults(cache), axes, blocks)


@dataclass(frozen=True)
class Winner:
    context: str
    cell: str
    entry: Entry
    mtp: int


def read_winner(path: Path, sl: Shortlist, context: str = "64K") -> Winner:
    data = json.loads(Path(path).read_text())
    if data.get("stage") != "2a2" or "winners" not in data:
        raise SpecGenError(f"{path} is not a 2a2 decision file (stage {data.get('stage')!r})")
    w = data["winners"].get(context)
    if not w:
        raise SpecGenError(f"{path}: no winner for context {context}")
    for e in sl.contexts[context]:
        if e.placement == w["placement"] and e.batch == w["batch"]:
            return Winner(context, w["cell"], e, int(w["mtp"]))
    raise SpecGenError(
        f"{path}: winner {w['cell']} is not one of the shortlisted placements of {context}"
    )


def _pair_stage(
    sl: Shortlist, root: Path, stage: str, title: str, cache: CachePolicy,
    wins: Winner | list[Winner], axis: str, values: dict[str, dict[str, Any]], command: str,
    extra: list[str] | None = None,
) -> SpecPlan:  # fmt: skip
    wins = [wins] if isinstance(wins, Winner) else list(wins)
    axes = _stage1_axes(sl, [w.entry for w in wins])
    axes["mtp"] = _mtp_axis(sorted({w.mtp for w in wins}))
    axes[axis] = values
    blocks = [_block(stage, w.entry, [f"mtp{w.mtp}"], {axis: list(values)}) for w in wins]
    header = _header(
        sl,
        root,
        stage,
        title,
        cache,
        command,
        [f"2a2 winner at {w.context}: {w.cell} (mtp {w.mtp})" for w in wins] + list(extra or []),
    )
    return _new_plan(sl, False, stage, header, _defaults(cache), axes, blocks)


def build_2b(sl, root, cache, win, command) -> SpecPlan:
    kv = {"kvq8": {}, "kvf16": {"cache_type_k": "f16", "cache_type_v": "f16"}}
    note = [
        "kvq8 sets nothing: 8-bit KV is the section 5.4 sweep default; "
        "kvf16 is explicit (-ctk f16 -ctv f16)"
    ]
    return _pair_stage(
        sl, root, "2b", "2b KV type (8-bit against FP16)", cache, win, "kv", kv, command, note
    )


def build_2c(sl, root, cache, win, command) -> SpecPlan:
    load = {
        "lmauto": {"load_mode": "auto"},
        f"lm{_slug(LOAD_MODE_ALT)}": {"load_mode": LOAD_MODE_ALT},
    }
    return _pair_stage(
        sl,
        root,
        "2c",
        "2c load mode (auto against the alternative)",
        cache,
        win,
        "load",
        load,
        command,
    )


def build_2d(sl, root, cache, win, default_threads: int | None, command) -> SpecPlan:
    if default_threads is None:
        raise SpecGenError(
            "2d needs --default-threads N (the n_threads the server uses by default)"
        )
    if default_threads == THREADS_EXPLICIT:
        raise NotNeeded(
            f"2d is not needed: the default thread count is {default_threads}, "
            f"the same as -t {THREADS_EXPLICIT}"
        )
    thr = {f"t{THREADS_EXPLICIT}": {"threads": THREADS_EXPLICIT}, "tdef": {}}
    return _pair_stage(
        sl,
        root,
        "2d",
        "2d threads",
        cache,
        win,
        "thr",
        thr,
        command,
        [f"default n_threads: {default_threads}"],
    )


def _slug(mode: str) -> str:
    return "".join(ch for ch in mode if ch.isalnum())


# ----------------------------------------------------------------------------- inputs


def read_cache_policy(arg: str | None, from_2f: Path | None) -> CachePolicy:
    """``--cache-ram N|default`` or the ``chosen_cache_ram`` of a decided 2f file. Never guessed."""
    if arg is not None and from_2f is not None:
        raise SpecGenError("give --cache-ram or --from-2f, not both")
    if arg is not None:
        if arg == NO_VALUE:
            return CachePolicy(None, "--cache-ram default (the llama-server default stays)")
        try:
            v = int(arg)
        except ValueError:
            raise SpecGenError(f"--cache-ram needs an integer or 'default', got {arg!r}") from None
        if v < -1:
            raise SpecGenError("--cache-ram must be -1 (no limit), 0 (disabled) or a size in MiB")
        return CachePolicy(v, "--cache-ram on the command line")
    if from_2f is None:
        raise SpecGenError(
            "the chosen cache_ram is needed: pass --cache-ram N|default or "
            "--from-2f <2f decision json>"
        )
    data = json.loads(Path(from_2f).read_text())
    if data.get("stage") != "2f":
        raise SpecGenError(f"{from_2f} is not a 2f decision file")
    if data.get("status") != "decided":
        raise SpecGenError(
            f"{from_2f}: the 2f decision is {data.get('status')!r}, not 'decided'; "
            "a human decides, then pass --cache-ram explicitly"
        )
    v = data.get("chosen_cache_ram")
    return CachePolicy(v, f"{from_2f} (2f decision, plan rule)")


def generate(
    stage: str,
    *,
    root: Path | None = None,
    preset: str | None = None,
    cache_ram: str | None = None,
    from_2f: Path | None = None,
    from_2a: Path | None = None,
    winner_from: Path | None = None,
    contexts: list[str] | None = None,
    anchor: bool = True,
    default_threads: int | None = None,
    command: str | None = None,
) -> str:
    """The text of the spec for ``stage``. Raises ``SpecGenError`` (or ``NotNeeded``)."""
    root = Path(root) if root else repo_root()
    if preset not in (None, "functional-test"):
        raise SpecGenError(f"unknown preset {preset!r}")
    ft = preset == "functional-test"
    if ft and stage not in ("2f", "2a"):
        raise SpecGenError("the functional-test preset exists for 2f and 2a only")
    command = command or f"python -m smallpc.stage2 spec --stage {stage}"
    sl = load_shortlist(root)
    if stage == "2f":
        return emit(build_2f(sl, root, command, ft))
    cache = (
        read_cache_policy(cache_ram, from_2f)
        if not (ft and stage == "2a")
        else CachePolicy(None, "functional test: the llama-server default")
    )
    if stage == "2a":
        return emit(build_2a(sl, root, cache, command, ft))
    if stage == "2a2":
        if from_2a is None:
            raise SpecGenError("2a2 needs --from-2a <2a decision json>")
        return emit(build_2a2(sl, root, cache, read_2a_result(from_2a, sl), command, anchor))
    if stage in ("2b", "2c", "2d"):
        if winner_from is None:
            raise SpecGenError(f"{stage} needs --winner-from <2a2 decision json>")
        ctxs = list(dict.fromkeys(contexts or ["64K"]))
        if stage != "2b" and ctxs != ["64K"]:
            raise SpecGenError(f"{stage} is generated for 64K only; --context is for 2b")
        wins = [read_winner(winner_from, sl, c) for c in ctxs]
        win = wins[0]
        if stage == "2b":
            return emit(build_2b(sl, root, cache, wins, command))
        if stage == "2c":
            return emit(build_2c(sl, root, cache, win, command))
        return emit(build_2d(sl, root, cache, win, default_threads, command))
    raise SpecGenError(f"unknown stage {stage!r}")


__all__ = [
    "CRAM_2F", "DRAFT_LENGTHS", "FT_PREFIX", "LOAD_MODE_ALT", "NotNeeded", "SpecGenError",
    "cell_name", "generate", "read_cache_policy",
]  # fmt: skip
