r"""Structural row canonicalizer (M1b, rules ``row_exact`` / ``row_widened``).

The regex rewrite rules of :mod:`lp2graph.mining.ingest.latex_normalizer` map
*spellings* onto the canonical grammar. They cannot restructure algebra: a
parenthesised sum under a coefficient, a product written by juxtaposition
three levels deep, a ``\sum`` whose body is itself a sum, a quantifier tail
that names a tuple or a range. This module does that structurally. It reads
one ``align`` row into a small expression tree, proves that the row is a
*linear* relation over the document's declared symbols, and re-emits it in
the canonical spelling. Every step is an algebraic identity:

* a product distributes over a parenthesised sum,
* a ``\sum`` of a sum is the sum of the ``\sum``\ s,
* nested ``\sum`` operators merge into one multi-binder ``\sum``,
* a factor written outside a ``\sum`` moves inside it,
* a numeric denominator scales the coefficient.

Nothing is guessed. A row that mentions an undeclared symbol, multiplies two
variables, raises to a power, or contains any token the reader has no rule
for is returned unchanged, so the canonical parser refuses it by name exactly
as before.

Two things the canonical model cannot carry are handled explicitly and
recorded, never silently:

**Derived parameters.** A canonical term has one coefficient. A product of
parameters (``\lambda \cdot C_{k} \cdot z_{k}``), a number times a parameter
on a variable (``2 M x``) or a parameter ratio (``d_{k} / T``) is itself a
parameter: data, not structure. The canonicalizer names it deterministically
(``lambda_x_C``, ``n2_x_M``, ``d_over_T``), uses it as the coefficient and
reports the declaration line it needs; the normalizer appends those lines to
the ``%@`` header and records one rewrite per derived parameter.

**Widening.** The canonical quantifier binds one index over one declared
family. A binder over a restricted set (``i \in I \setminus \{1\}``), a tuple
(``(i, j) \in A``), a range (``i = 1, \ldots, n``) or a tail condition the
model has no field for is widened to the base families of its letters. That
is the same recorded approximation as the ``restricted_set_widen`` rule
(lab ADR-0015); it is applied only by the ``row_widened`` rule, so the
provenance shows which rows are exact and which were widened.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from fractions import Fraction
from functools import lru_cache
from typing import Final

__all__ = [
    "RowContext",
    "RowOutline",
    "SymbolUse",
    "canonicalize_row",
    "derived_declaration",
    "outline_row",
    "scan_symbols",
]


#: Words that, written as a subscript or superscript, name a variant of the
#: symbol (a bound, a phase, a direction) and never a run of index letters.
#: Part of the rewrite-rule resource (``REWRITE_RULES_VERSION``).
SCRIPT_LABELS: Final = frozenset(
    [
        "acc",
        "accel",
        "act",
        "actual",
        "after",
        "arc",
        "arr",
        "arrival",
        "aux",
        "avg",
        "bar",
        "base",
        "before",
        "begin",
        "best",
        "blk",
        "block",
        "bound",
        "brake",
        "buf",
        "buffer",
        "cap",
        "capacity",
        "close",
        "closed",
        "cost",
        "crew",
        "cum",
        "cumulative",
        "cur",
        "curr",
        "current",
        "dec",
        "decel",
        "del",
        "delay",
        "dem",
        "demand",
        "dep",
        "departure",
        "dest",
        "destination",
        "dis",
        "disr",
        "disruption",
        "dist",
        "distance",
        "down",
        "driver",
        "dual",
        "dwell",
        "dyn",
        "dynamic",
        "early",
        "edge",
        "end",
        "est",
        "estimated",
        "exp",
        "expected",
        "fin",
        "final",
        "first",
        "fix",
        "fixed",
        "flow",
        "free",
        "hat",
        "head",
        "headway",
        "high",
        "idle",
        "init",
        "initial",
        "last",
        "late",
        "len",
        "length",
        "line",
        "link",
        "load",
        "low",
        "lower",
        "max",
        "mean",
        "min",
        "new",
        "next",
        "node",
        "nom",
        "nominal",
        "obs",
        "observed",
        "occ",
        "occupied",
        "off",
        "old",
        "open",
        "opt",
        "optimal",
        "orig",
        "origin",
        "out",
        "pass",
        "passenger",
        "passing",
        "path",
        "pax",
        "pen",
        "penalty",
        "plan",
        "planned",
        "plat",
        "platform",
        "post",
        "pre",
        "prev",
        "previous",
        "prime",
        "real",
        "ref",
        "res",
        "rev",
        "route",
        "run",
        "running",
        "safe",
        "safety",
        "sched",
        "scheduled",
        "sec",
        "section",
        "seg",
        "segment",
        "sink",
        "slack",
        "snk",
        "source",
        "speed",
        "src",
        "sta",
        "star",
        "start",
        "static",
        "station",
        "stn",
        "stop",
        "sum",
        "supply",
        "temp",
        "tilde",
        "time",
        "tmp",
        "tot",
        "total",
        "track",
        "train",
        "turn",
        "unit",
        "upper",
        "var",
        "variable",
        "veh",
        "vehicle",
        "vel",
        "velocity",
        "wait",
        "waiting",
        "worst",
    ]
)


class _Refuse(Exception):
    """The row is outside what this reader can prove; leave it untouched."""


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RowContext:
    """What the document declares, as the row reader needs it."""

    params: frozenset[str]
    variables: frozenset[str]
    indices: frozenset[str]
    shapes: dict[str, tuple[str, ...]]
    #: Letters the body binds anywhere (binders, quantifiers, ranges).
    bound: frozenset[str]
    #: letter -> the one family the body binds it over in exact binders
    #: (absent when the body binds it over several families or none).
    letter_family: dict[str, str] = field(default_factory=dict)
    #: Derived parameters created so far: name -> (shape, definition). Shared
    #: and mutable on purpose: the normalizer collects them across rows.
    derived: dict[str, tuple[tuple[str, ...], str]] = field(default_factory=dict)

    def shape(self, name: str) -> tuple[str, ...]:
        if name in self.derived:
            return self.derived[name][0]
        return self.shapes.get(name, ())

    def is_symbol(self, name: str) -> bool:
        return name in self.params or name in self.variables or name in self.derived

    def is_var(self, name: str) -> bool:
        """A declared variable, or a derived one (an auxiliary variable the
        reader introduced; its definition is marked ``var:<domain>:``)."""
        return name in self.variables or (
            name in self.derived and self.derived[name][1].startswith("var:")
        )

    def is_param(self, name: str) -> bool:
        return name in self.params or (name in self.derived and not self.is_var(name))


_EXACT_BINDER_RE = re.compile(
    r"(?<![\\A-Za-z0-9_])([A-Za-z]\w*(?:\s*,\s*[A-Za-z]\w*)*)\s*\\in\s*"
    r"(?:\\mathcal\{([A-Za-z_]\w*)\}|\\mathit\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))"
    r"(?![A-Za-z0-9_]|\s*[_^(]|\s*\\left\()"
)


@lru_cache(maxsize=8)
def body_letter_families(body: str) -> dict[str, str]:
    """letter -> family for every letter the body binds over exactly one family."""
    seen: dict[str, set[str]] = {}
    for m in _EXACT_BINDER_RE.finditer(body):
        fam = m.group(2) or m.group(3) or m.group(4)
        for letter in re.split(r"\s*,\s*", m.group(1)):
            seen.setdefault(letter, set()).add(fam)
    return {k: next(iter(v)) for k, v in sorted(seen.items()) if len(v) == 1}


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Tok:
    kind: str  # num name cmd open close lb rb bar op text sep
    val: str
    start: int
    end: int


_LEX_RE = re.compile(
    r"""
    (?P<ws>(?:\s|&|\\[,;!:\ ]|\\(?:displaystyle|limits|nolimits|nonumber|notag|hfill|allowbreak)(?![A-Za-z]))+)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<mathit>\\mathit\{\s*(?P<mi>[A-Za-z_][\w\\]*)\s*\})
  | (?P<text>\\(?:text|textrm|mathrm|textit|textbf|mbox|operatorname)\s*\{(?P<tx>[^{}]*)\})
  | (?P<left>\\left\s*(?P<ld>\\\{|\\langle|\\lfloor|\\lceil|\\\||\\lbrace|[(\[|.〈]))
  | (?P<right>\\right\s*(?P<rd>\\\}|\\rangle|\\rfloor|\\rceil|\\\||\\rbrace|[)\]|.〉]))
  | (?P<setl>\\\{|\\lbrace(?![A-Za-z]))
  | (?P<setr>\\\}|\\rbrace(?![A-Za-z]))
  | (?P<cmd>\\[A-Za-z]+)
  | (?P<name>[A-Za-z][A-Za-z0-9]*(?:_(?!\{)[A-Za-z0-9]+)*)
  | (?P<ch>.)
    """,
    re.VERBOSE | re.DOTALL,
)

_OPEN = {"(": "(", "[": "[", r"\{": "{", r"\lbrace": "{", r"\langle": "<", "〈": "<"}
_CLOSE = {")": ")", "]": "]", r"\}": "}", r"\rbrace": "}", r"\rangle": ">", "〉": ">"}
_MATCH = {"(": ")", "[": "]", "{": "}", "<": ">"}

_REL_CMDS: Final = {
    r"\le": "le",
    r"\leq": "le",
    r"\leqslant": "le",
    r"\ge": "ge",
    r"\geq": "ge",
    r"\geqslant": "ge",
}
_REL_OUT: Final = {"le": r"\le", "ge": r"\ge", "eq": "="}
_SET_WRAPPERS: Final = frozenset(
    {
        r"\mathcal",
        r"\mathbb",
        r"\mathbf",
        r"\mathfrak",
        r"\mathscr",
        r"\boldsymbol",
        r"\vec",
        r"\bm",
    }
)
_DOTS: Final = frozenset({r"\ldots", r"\cdots", r"\dots", r"\hdots", r"\dotsc", r"\dotsb"})
_TAIL_WORDS: Final = frozenset({"for", "forall", "where", "with", "if", "when", "and"})
_SPACERS: Final = frozenset({r"\quad", r"\qquad"})
_CONDITION_WORDS: Final = frozenset(
    {"if", "and", "or", "for", "all", "each", "every", "otherwise", "where", "when", "with"}
    | {"such", "that", "is", "in", "the", "of", "st", "else", "any", "not", "odd", "even"}
)


def _lex(text: str) -> list[_Tok]:
    out: list[_Tok] = []
    for m in _LEX_RE.finditer(text):
        k = m.lastgroup
        s, e = m.start(), m.end()
        if k == "ws":
            continue
        if k == "num":
            out.append(_Tok("num", m.group(), s, e))
        elif k == "mathit":
            out.append(_Tok("name", m.group("mi").replace("\\_", "_"), s, e))
        elif k == "text":
            out.append(_Tok("text", " ".join(m.group("tx").split()), s, e))
        elif k == "left":
            d = m.group("ld")
            if d == ".":
                continue
            if d in ("|", r"\|"):
                out.append(_Tok("bar", "L", s, e))
            elif d in _OPEN:
                out.append(_Tok("open", _OPEN[d], s, e))
            else:
                out.append(_Tok("cmd", r"\left" + d, s, e))
        elif k == "right":
            d = m.group("rd")
            if d == ".":
                continue
            if d in ("|", r"\|"):
                out.append(_Tok("bar", "R", s, e))
            elif d in _CLOSE:
                out.append(_Tok("close", _CLOSE[d], s, e))
            else:
                out.append(_Tok("cmd", r"\right" + d, s, e))
        elif k == "setl":
            out.append(_Tok("open", "{", s, e))
        elif k == "setr":
            out.append(_Tok("close", "}", s, e))
        elif k == "cmd":
            out.append(_Tok("cmd", m.group(), s, e))
        elif k == "name":
            out.append(_Tok("name", m.group(), s, e))
        else:
            ch = m.group()
            if ch in "([":
                out.append(_Tok("open", ch, s, e))
            elif ch in ")]":
                out.append(_Tok("close", ch, s, e))
            elif ch == "{":
                out.append(_Tok("lb", ch, s, e))
            elif ch == "}":
                out.append(_Tok("rb", ch, s, e))
            elif ch == "|":
                out.append(_Tok("bar", "?", s, e))
            elif ch in "∊":
                out.append(_Tok("cmd", r"\in", s, e))
            else:
                out.append(_Tok("op", ch, s, e))
    return out


def _depths(toks: list[_Tok]) -> list[int]:
    """Nesting depth *before* each token (parens, sets and TeX groups)."""
    out: list[int] = []
    d = 0
    for t in toks:
        if t.kind in ("close", "rb"):
            d -= 1
        out.append(d)
        if t.kind in ("open", "lb"):
            d += 1
    if d != 0 or any(x < 0 for x in out):
        raise _Refuse("unbalanced delimiters")
    return out


def _group_end(toks: list[_Tok], i: int) -> int:
    """Index of the token closing the group opened at ``i``."""
    d = 0
    for j in range(i, len(toks)):
        if toks[j].kind in ("open", "lb"):
            d += 1
        elif toks[j].kind in ("close", "rb"):
            d -= 1
            if d == 0:
                return j
    raise _Refuse("unbalanced group")


def _src(text: str, toks: list[_Tok]) -> str:
    return text[toks[0].start : toks[-1].end] if toks else ""


@dataclass(frozen=True, slots=True)
class SymbolUse:
    """One identifier occurrence in a row, as the lexer reads it."""

    name: str
    pieces: tuple[str, ...]
    #: raw superscript group, if one is left on the occurrence
    sup: str | None
    #: the occurrence is followed by ``\cdot`` (it multiplies what follows)
    coefficient: bool
    #: the occurrence sits in the quantifier tail (after ``\forall``/``\qquad``)
    in_tail: bool
    #: the identifier this occurrence multiplies (the next factor), if any
    multiplies: str | None = None
    #: every identifier of the product that follows this occurrence, looking
    #: through a ``\sum`` and into a bracket: ``w \sum_{i} c_{i} x_{i}`` and
    #: ``M (1 - x_{i})`` both give ``w`` / ``M`` a product that holds ``x``
    product: tuple[str, ...] = ()


def scan_symbols(row: str) -> list[SymbolUse]:
    r"""Every identifier of a row outside script groups and ``\sum`` binders.

    A plain reading aid for callers that audit vocabulary and shapes: nothing
    is interpreted, a name is whatever the lexer reads as one.
    """
    toks = _lex(row)
    out: list[SymbolUse] = []
    i = 0
    in_tail = False
    n = len(toks)

    def skip_group(j: int) -> int:
        if j < n and toks[j].kind == "lb":
            try:
                return _group_end(toks, j) + 1
            except _Refuse:
                return n
        return j + 1

    def product_names(j: int) -> list[str]:
        """Identifiers of the factors that follow position ``j`` in one product."""
        names: list[str] = []
        k = j
        while k < n:
            tk = toks[k]
            if tk.kind == "cmd" and tk.val == r"\cdot":
                k += 1
            elif tk.kind == "name":
                names.append(tk.val)
                k += 1
                while k < n and toks[k].kind == "op" and toks[k].val in "_^":
                    k = skip_group(k + 1)
            elif tk.kind == "num":
                k += 1
            elif tk.kind == "cmd" and tk.val == r"\sum":
                k += 1
                while k < n and toks[k].kind == "op" and toks[k].val in "_^":
                    k = skip_group(k + 1)
            elif tk.kind == "cmd" and tk.val == r"\underset":
                k = skip_group(skip_group(k + 1))
            elif tk.kind in ("open", "lb"):
                try:
                    end = _group_end(toks, k)
                except _Refuse:
                    break
                d = 0
                m = k + 1
                while m < end:  # every name of the bracket, outside script groups
                    tm = toks[m]
                    if tm.kind == "op" and tm.val in "_^":
                        m = skip_group(m + 1)
                        continue
                    if tm.kind == "name":
                        names.append(tm.val)
                    m += 1
                del d
                k = end + 1
            else:
                break
        return names

    while i < n:
        t = toks[i]
        if t.kind == "cmd" and t.val in (r"\forall", r"\qquad"):
            in_tail = True
        if t.kind == "cmd" and t.val in (
            r"\sum",
            r"\prod",
            r"\max",
            r"\min",
            r"\bigcup",
            r"\bigcap",
        ):
            i += 1
            while i < n and toks[i].kind == "op" and toks[i].val in "_^":
                i = skip_group(i + 1)
            continue
        if t.kind == "cmd" and t.val == r"\underset":
            i = skip_group(i + 1)
            continue
        if t.kind == "cmd" and t.val in (r"\tag", r"\label"):
            i = skip_group(i + 1)
            continue
        if t.kind != "name":
            i += 1
            continue
        pieces: list[str] = []
        sup: str | None = None
        j = i + 1
        while j < n and toks[j].kind == "op" and toks[j].val in "_^":
            k = skip_group(j + 1)
            if j + 1 >= n:
                break
            first = toks[j + 1]
            if first.kind == "lb" and k - 1 < n:
                inner = row[first.end : toks[k - 1].start]
            else:
                inner = row[first.start : first.end]
            if toks[j].val == "_":
                pieces.extend(_sub_pieces(inner))
            else:
                sup = inner.strip()
            j = k
        coef = j < n and toks[j].kind == "cmd" and toks[j].val == r"\cdot"
        k = j + 1 if coef else j
        # what the occurrence multiplies may sit behind a \sum or inside a
        # bracket: c \sum_{i} x_{i}, M (1 - x_{i})
        hops = 0
        while k < n and hops < 6:
            tk = toks[k]
            if tk.kind == "cmd" and tk.val == r"\sum":
                k += 1
                while k < n and toks[k].kind == "op" and toks[k].val in "_^":
                    k = skip_group(k + 1)
            elif tk.kind == "cmd" and tk.val == r"\underset":
                k = skip_group(skip_group(k + 1))
            elif (
                tk.kind in ("open", "lb")
                or tk.kind == "num"
                or (tk.kind == "op" and tk.val in "+-")
            ):
                if tk.kind in ("num", "op") and hops == 0:
                    break  # a number or sign right after the name: not a product
                k += 1
            else:
                break
            hops += 1
        nxt = toks[k] if k < n else None
        out.append(
            SymbolUse(
                t.val,
                tuple(pieces),
                sup,
                coef,
                in_tail,
                nxt.val if nxt is not None and nxt.kind == "name" else None,
                tuple(product_names(j)),
            )
        )
        i = j
    return out


@dataclass(frozen=True, slots=True)
class RowOutline:
    """The skeleton of one row: its comparators and, per side, the
    identifiers of the algebra (the quantifier tail is left out)."""

    comparators: tuple[str, ...]
    sides: tuple[tuple[SymbolUse, ...], ...]
    #: per side: the side is exactly one identifier occurrence (``u_{i} = ...``)
    alone: tuple[bool, ...]


def outline_row(row: str, symbols: frozenset[str]) -> RowOutline | None:
    """Split a row's algebra at its top-level comparators; ``None`` when the
    row cannot be delimited. ``symbols`` are the names known to be symbols
    (they decide where a tail written without ``\\forall`` starts)."""
    ctx = RowContext(
        params=symbols, variables=frozenset(), indices=frozenset(), shapes={}, bound=frozenset()
    )
    text = _TRAILING_RE.sub("", row.strip().lstrip("&").strip())
    try:
        toks = _lex(text)
        if not toks:
            return None
        alg = toks[: _tail_start(toks, ctx)]
        rels = _relations(alg)
    except _Refuse:
        return None
    bounds = [0]
    for pos, _c, _s in rels:
        bounds.extend((pos, pos + 1))
    bounds.append(len(alg))
    sides: list[tuple[SymbolUse, ...]] = []
    alone: list[bool] = []
    for k in range(0, len(bounds), 2):
        seg = alg[bounds[k] : bounds[k + 1]]
        if not seg:
            sides.append(())
            alone.append(False)
            continue
        src = text[seg[0].start : seg[-1].end]
        uses = tuple(scan_symbols(src))
        sides.append(uses)
        alone.append(len(uses) == 1 and _is_label(seg) and seg[-1].kind != "close")
    return RowOutline(tuple(c for _p, c, _s in rels), tuple(sides), tuple(alone))


# ---------------------------------------------------------------------------
# Expression tree
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Sym:
    name: str
    subs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Mono:
    """``coef * prod(syms)`` under the ``sums`` binders."""

    coef: Fraction
    syms: tuple[_Sym, ...] = ()
    sums: tuple[tuple[str, str], ...] = ()
    #: Symbols that divide (parameter ratios); kept apart from ``syms``.
    dens: tuple[_Sym, ...] = ()
    #: Source text of the binders this term was summed under (widening guard).
    origin: tuple[str, ...] = ()
    #: The term is ``coef * pw``: an absolute value or an extremum of
    #: expressions. It has no canonical spelling of its own; a row may carry
    #: one only where it can be rewritten exactly, anything else is refused.
    pw: _Piecewise | None = None


@dataclass(frozen=True, slots=True)
class _Piecewise:
    r"""``|e|`` (kind ``abs``, one branch), ``max(e_1, ..)`` / ``min(e_1, ..)``,
    or an extremum over a binder (``max_{i \in I} e_i``: one branch, ``binders``)."""

    kind: str
    branches: tuple[tuple[_Mono, ...], ...]
    binders: tuple[tuple[str, str], ...] = ()


_IDX_ATOM = r"[A-Za-z]\w*"
_IDX_EXPR_RE = re.compile(rf"^(?:{_IDX_ATOM}(?:\s*[+-]\s*(?:\d+|{_IDX_ATOM}))?|\d+)$")
_LETTERS_RUN_RE = re.compile(r"^[A-Za-z](?:\s+[A-Za-z]\w*)+$")


def _split_top(s: str, seps: str = ",") -> list[str]:
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] in "{}":
            cur.append(s[i : i + 2])
            i += 2
            continue
        if ch in "{([〈":
            depth += 1
        elif ch in "})]〉":
            depth -= 1
        if ch in seps and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur))
    return [x.strip() for x in out]


class _Reader:
    """Recursive-descent reader of one row's algebra."""

    def __init__(self, text: str, toks: list[_Tok], ctx: RowContext, *, widen: bool) -> None:
        self.text = text
        self.toks = toks
        self.ctx = ctx
        self.widen = widen
        self.i = 0
        #: letter -> families seen at its subscript positions in this row
        self.usage: dict[str, set[str]] = {}
        #: letters this row binds (binders and tail); a declared symbol of the
        #: same name must not occur bare in the row (it would be the letter)
        self.shadowed: set[str] = set()
        self.widened = False
        #: names the row for derived symbols (shared by the row's sub-readers)
        self.row_id = "row"
        self.counter: list[int] = [0]

    def child(self, toks: list[_Tok]) -> _Reader:
        """A reader over part of this row, sharing what the row accumulates."""
        sub = _Reader(self.text, toks, self.ctx, widen=self.widen)
        sub.usage = self.usage
        sub.shadowed = self.shadowed
        sub.row_id = self.row_id
        sub.counter = self.counter
        return sub

    # -- token helpers ------------------------------------------------------

    def peek(self, k: int = 0) -> _Tok | None:
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else None

    def take(self) -> _Tok:
        t = self.toks[self.i]
        self.i += 1
        return t

    def at_op(self, val: str) -> bool:
        t = self.peek()
        return t is not None and t.kind == "op" and t.val == val

    def at_cmd(self, *vals: str) -> bool:
        t = self.peek()
        return t is not None and t.kind == "cmd" and t.val in vals

    def group_text(self) -> str:
        """Consume ``{...}`` (or one token) after ``_``/``^``; return the inner source."""
        t = self.peek()
        if t is None:
            raise _Refuse("dangling script")
        if t.kind == "lb":
            j = _group_end(self.toks, self.i)
            inner = self.text[t.end : self.toks[j].start]
            self.i = j + 1
            return inner.strip()
        self.i += 1
        return self.text[t.start : t.end]

    # -- grammar ------------------------------------------------------------

    def expr(self) -> list[_Mono]:
        monos: list[_Mono] = []
        sign = 1
        need = True
        while True:
            t = self.peek()
            if t is not None and t.kind == "op" and t.val in "+-":
                self.take()
                if t.val == "-":
                    sign = -sign
                need = True
                continue
            if t is None or not self.starts_factor(t):
                if need:
                    raise _Refuse("dangling operator")
                break
            if not need:
                break
            monos.extend(_scale(m, Fraction(sign)) for m in self.term())
            sign = 1
            need = False
        return monos

    def starts_factor(self, t: _Tok) -> bool:
        if t.kind in ("num", "name", "open", "lb"):
            return True
        if t.kind == "bar":
            return t.val == "L"
        if t.kind == "cmd":
            return t.val in (
                r"\sum",
                r"\frac",
                r"\dfrac",
                r"\tfrac",
                r"\underset",
                r"\max",
                r"\min",
                r"\casesof",
            )
        return False

    def term(self) -> list[_Mono]:
        acc = self.factor()
        prev_value = _is_index_value(acc)
        while True:
            t = self.peek()
            if t is None:
                break
            if t.kind == "cmd" and t.val == r"\cdot":
                self.take()
                nxt = self.peek()
                if nxt is None or not self.starts_factor(nxt):
                    raise _Refuse("dangling product")
                rhs = self.factor()
                prev_value = _is_index_value(rhs)
                acc = _mul(acc, rhs)
                continue
            if t.kind == "op" and t.val == "/":
                self.take()
                nxt = self.peek()
                if nxt is None or not self.starts_factor(nxt):
                    raise _Refuse("dangling division")
                acc = _div(acc, self.single_denominator(self.factor()))
                prev_value = False
                continue
            if self.starts_factor(t):
                juxtaposed_group = t.kind in ("open", "lb")
                rhs = self.factor()
                if (prev_value or _is_index_value(rhs)) and not juxtaposed_group:
                    # "P_{u} t" may be the call P(t) with its brackets lost: an
                    # index letter is read as a number only next to an operator
                    raise _Refuse("index letter next to a symbol without an operator")
                prev_value = _is_index_value(rhs)
                acc = _mul(acc, rhs)
                continue
            break
        return acc

    def factor(self) -> list[_Mono]:
        t = self.take()
        if t.kind == "num":
            return [_Mono(Fraction(t.val))]
        if t.kind == "name" and t.val.lower() in ("max", "min") and not self.ctx.is_symbol(t.val):
            return self.extremum(t.val.lower(), None)
        if t.kind == "cmd" and t.val in (r"\max", r"\min"):
            return self.extremum(t.val[1:], None)
        if t.kind == "name":
            if not self.ctx.is_symbol(t.val) and t.val in self.ctx.bound:
                nxt = self.peek()
                if nxt is None or not (nxt.kind == "op" and nxt.val in "_^"):
                    # a bound index letter used as a number: its value is data
                    # (decided once the row's binders are known)
                    return [_Mono(Fraction(1), (_Sym(_INDEX_VALUE, (t.val,)),))]
            return [_Mono(Fraction(1), (self.symbol(t.val),))]
        if t.kind in ("open", "lb"):
            self.i -= 1
            j = _group_end(self.toks, self.i)
            inner = self.child(self.toks[self.i + 1 : j])
            # a group holding one bare name is that name: {c}_{a}, \left(c\right)_{a}
            only = self.toks[self.i + 1 : j]
            self.i = j + 1
            if len(only) == 1 and only[0].kind == "name":
                return [_Mono(Fraction(1), (self.symbol(only[0].val),))]
            monos = inner.expr()
            if inner.i != len(inner.toks):
                raise _Refuse("unread tokens in group")
            self.widened = self.widened or inner.widened
            nxt = self.peek()
            if nxt is not None and nxt.kind == "op" and nxt.val in "^_":
                raise _Refuse("script on a parenthesised expression")
            return monos
        if t.kind == "bar" and t.val == "L":
            depth = 0
            for j in range(self.i, len(self.toks)):
                tj = self.toks[j]
                if tj.kind in ("open", "lb"):
                    depth += 1
                elif tj.kind in ("close", "rb"):
                    depth -= 1
                elif tj.kind == "bar" and tj.val == "R" and depth == 0:
                    break
            else:
                raise _Refuse("unclosed absolute value")
            card = self.cardinality(self.toks[self.i : j])
            if card is not None:
                self.i = j + 1
                return [_Mono(Fraction(1), (card,))]
            inner = self.child(self.toks[self.i : j])
            monos = inner.expr()
            if inner.i != len(inner.toks):
                raise _Refuse("unread tokens in absolute value")
            self.widened = self.widened or inner.widened
            self.i = j + 1
            return [_Mono(Fraction(1), pw=_Piecewise("abs", (tuple(monos),)))]
        if t.kind == "cmd" and t.val == r"\casesof":
            return [_Mono(Fraction(1), (self.cases_parameter(),))]
        if t.kind == "cmd" and t.val == r"\sum":
            return self.bigsum(None)
        if t.kind == "cmd" and t.val == r"\underset":
            nxt = self.peek()
            if nxt is None or nxt.kind != "lb":
                raise _Refuse("underset without argument")
            binder = self.group_text()
            op = re.sub(
                r"\\(?:text|mathrm|mathit|mathbf|operatorname)\s*\{([^{}]*)\}",
                r"\1",
                self.group_text(),
            )
            op = op.replace(" ", "").lstrip("\\").lower()
            if op == "sum":
                return self.bigsum(binder)
            if op in ("max", "min"):
                return self.extremum(op, binder)
            raise _Refuse(f"underset over {op!r}")
        if t.kind == "cmd" and t.val in (r"\frac", r"\dfrac", r"\tfrac"):
            num = self.braced_expr()
            den = self.braced_expr()
            return _div(num, self.single_denominator(den))
        raise _Refuse(f"no rule for token {t.val!r}")

    def single_denominator(self, den: list[_Mono]) -> list[_Mono]:
        """A denominator that is a sum of parameter terms is itself one
        (derived) parameter: ``(T_max - T_min)`` under a fraction bar."""
        if len(den) <= 1:
            return den
        ctx = self.ctx
        parts: list[str] = []
        define: list[str] = []
        exprs: list[str] = []
        shape: list[str] = []
        for m in den:
            if m.sums or m.dens or any(s.name in ctx.variables for s in m.syms) or m.coef == 0:
                raise _Refuse("division by a sum")
            sign = "m" if m.coef < 0 else "p"
            mag = abs(m.coef)
            names = ([_num_ident(mag)] if mag != 1 or not m.syms else []) + [s.name for s in m.syms]
            parts.append(sign + "_" + "_x_".join(names))
            define.append(
                ("- " if m.coef < 0 else "+ ")
                + " * ".join(
                    ([_num_text(mag)] if mag != 1 or not m.syms else []) + [s.name for s in m.syms]
                )
            )
            for s in m.syms:
                fshape = ctx.shape(s.name)
                if len(fshape) != len(s.subs):
                    raise _Refuse("division by a sum")
                for fam, e in zip(fshape, s.subs, strict=True):
                    if e not in exprs:
                        exprs.append(e)
                        shape.append(fam)
        name = "sum_" + "_".join(parts)
        if ctx.is_symbol(name) and name not in ctx.derived:
            if not (name in ctx.params and ctx.shape(name) == tuple(shape)):
                raise _Refuse("division by a sum")
        else:
            ctx.derived[name] = (tuple(shape), " ".join(define).lstrip("+ "))
        return [_Mono(Fraction(1), (_Sym(name, tuple(exprs)),))]

    def cases_parameter(self) -> _Sym:
        """``\\casesof{v_1}{c_1}{v_2}{c_2}..``: a value that depends on a
        condition over the indices. When every branch value is free of
        variables (``1``, ``-1``, ``0``; ``\\gamma``, ``-\\gamma``, ``0``)
        the whole distinction is data: one derived parameter over the index
        letters its conditions and values name. A branch that holds a variable
        is a second constraint under another condition, which the model
        cannot state, and is refused."""
        ctx = self.ctx
        branches: list[tuple[list[_Mono], str]] = []
        while True:
            t = self.peek()
            if t is None or t.kind != "lb":
                break
            j = _group_end(self.toks, self.i)
            value = self.child(self.toks[self.i + 1 : j])
            monos = value.expr() if value.toks else []
            if value.i != len(value.toks):
                raise _Refuse("unread tokens in a case value")
            self.i = j + 1
            t = self.peek()
            if t is None or t.kind != "lb":
                raise _Refuse("case without a condition")
            j = _group_end(self.toks, self.i)
            cond = self.text[t.end : self.toks[j].start]
            self.i = j + 1
            branches.append((monos, cond))
        if len(branches) < 2:
            raise _Refuse("case distinction with fewer than two branches")
        letters: list[str] = []

        def note(atom: str) -> None:
            if atom in ctx.bound and not ctx.is_symbol(atom) and atom not in letters:
                letters.append(atom)

        for monos, cond in branches:
            for m in monos:
                if (
                    m.sums
                    or m.pw is not None
                    or any(ctx.is_var(x.name) for x in (*m.syms, *m.dens))
                ):
                    raise _Refuse("case value holds a variable or a sum")
                for sym in (*m.syms, *m.dens):
                    if not ctx.is_symbol(sym.name):
                        raise _Refuse("case value holds an index letter")
                    for piece in sym.subs:
                        for atom in re.findall(_IDX_ATOM, piece):
                            note(atom)
            # The condition must be a test over the row's index letters and
            # declared data. Prose ("if activity a is maintained") describes
            # what a variable means; such a row is a definition in words, not
            # a constraint, and is left alone.
            cond = _SPACED_CASE_WORD_RE.sub(" ", cond)
            # an undeclared plain name an index letter is compared with for
            # equality is a fixed element of the letter's family (i = o)
            elements: set[str] = set()
            for em in _CASE_ELEMENT_RE.finditer(cond):
                for letter, other in ((em.group(1), em.group(2)), (em.group(2), em.group(1))):
                    if letter in ctx.bound and not ctx.is_symbol(letter):
                        elements.add(other)
            for tok in _lex(cond):
                if tok.kind == "text":
                    if set(re.findall(r"[A-Za-z]+", tok.val.lower())) - _CASE_WORDS:
                        raise _Refuse("case condition in words")
                elif tok.kind == "name":
                    if tok.val.lower() in _CASE_WORDS:
                        continue
                    if ctx.is_var(tok.val):
                        raise _Refuse("case condition tests a variable")
                    if tok.val in ctx.bound and not ctx.is_symbol(tok.val):
                        note(tok.val)
                    elif not (
                        ctx.is_symbol(tok.val) or tok.val in ctx.indices or tok.val in elements
                    ):
                        raise _Refuse(f"case condition names {tok.val!r}, which is not declared")
        shape: list[str] = []
        for letter in letters:
            fams = self.usage.get(letter)
            fam = next(iter(fams)) if fams and len(fams) == 1 else ctx.letter_family.get(letter)
            if fam is None:
                raise _Refuse(f"no family for the letter {letter!r} of a case distinction")
            shape.append(fam)
        self.counter[0] += 1
        name = f"case_{self.row_id}_{self.counter[0]}"
        if ctx.is_symbol(name) and name not in ctx.derived:
            if not (name in ctx.params and ctx.shape(name) == tuple(shape)):
                raise _Refuse(f"derived name {name!r} collides with a declared symbol")
        else:
            ctx.derived[name] = (
                tuple(shape),
                f"value by index condition, {len(branches)} cases, of the row {self.row_id}",
            )
        return _Sym(name, tuple(letters))

    def cardinality(self, toks: list[_Tok]) -> _Sym | None:
        """``|S|`` with ``S`` an index family (or a labelled or indexed subset
        of one, ``|E^{stop}_{f}|``) is a number the data fixes: the derived
        parameter ``card_S``. ``None`` when the bars hold anything else."""
        ctx = self.ctx
        wrappers = 0
        i = 0
        while (
            i + 1 < len(toks)
            and toks[i].kind == "cmd"
            and toks[i].val in _SET_WRAPPERS
            and toks[i + 1].kind == "lb"
        ):
            i += 2
            wrappers += 1
        if i >= len(toks) or toks[i].kind != "name":
            return None
        name = toks[i].val
        base = re.sub(r"_.*$", "", name)
        # A family whose name is also a scalar parameter (the horizon T next
        # to the periods \mathcal{T}): between bars it is the set.
        homonym = name in ctx.indices and ctx.is_param(name) and not ctx.shape(name)
        if (ctx.is_symbol(name) and not homonym) or not (
            name in ctx.indices or base in ctx.indices
        ):
            return None
        i += 1 + wrappers
        if any(t.kind != "rb" for t in toks[i - wrappers : i]):
            return None
        pieces: list[str] = []
        while i < len(toks) and toks[i].kind == "op" and toks[i].val == "_":
            if i + 1 < len(toks) and toks[i + 1].kind == "lb":
                end = _group_end(toks, i + 1)
                pieces.extend(_sub_pieces(self.text[toks[i + 1].end : toks[end].start]))
                i = end + 1
            else:
                return None
        if i != len(toks):
            return None
        shape: list[str] = []
        for piece in pieces:
            fam = ctx.letter_family.get(piece)
            if fam is None:
                return None
            shape.append(fam)
        derived = "card_" + name
        if ctx.is_symbol(derived) and derived not in ctx.derived:
            if not (derived in ctx.params and ctx.shape(derived) == tuple(shape)):
                return None
        else:
            known = ctx.derived.get(derived)
            if known is not None and known[0] != tuple(shape):
                return None
            ctx.derived[derived] = (tuple(shape), f"number of elements of {name}")
        return _Sym(derived, tuple(pieces))

    def extremum(self, kind: str, binder: str | None) -> list[_Mono]:
        """``max \\{a, b\\}``, ``\\max_{i \\in I} e_i``, ``\\underset{i}{max} e_i``."""
        if binder is None and self.at_op("_"):
            self.take()
            binder = self.group_text()
        nxt = self.peek()
        if nxt is None:
            raise _Refuse("extremum without arguments")
        branches: list[list[_Mono]] | None = None
        if nxt.kind == "open":
            j = _group_end(self.toks, self.i)
            inner = self.toks[self.i + 1 : j]
            depths = _depths(inner)
            parts: list[list[_Tok]] = [[]]
            for tok, d in zip(inner, depths, strict=True):
                if d == 0 and tok.kind == "op" and tok.val == ",":
                    parts.append([])
                else:
                    parts[-1].append(tok)
            if len(parts) >= 2:
                branches = []
                for part in parts:
                    sub = self.child(part)
                    if not part:
                        raise _Refuse("empty argument of an extremum")
                    branches.append(sub.expr())
                    if sub.i != len(sub.toks):
                        raise _Refuse("unread tokens in an extremum")
                    self.widened = self.widened or sub.widened
                self.i = j + 1
        if branches is None:
            if binder is None:
                raise _Refuse("extremum of one expression without a binder")
            if not self.starts_factor(nxt):
                raise _Refuse("extremum without a body")
            branches = [self.term()]
        pairs: list[tuple[str, str]] = []
        if binder is not None:
            pairs, widened = _binder_clauses(binder, None, self, tail=False)
            self.widened = self.widened or widened
        pw = _Piecewise(kind, tuple(tuple(b) for b in branches), tuple(pairs))
        return [_Mono(Fraction(1), pw=pw)]

    def braced_expr(self) -> list[_Mono]:
        t = self.peek()
        if t is None or t.kind != "lb":
            raise _Refuse("fraction without braces")
        j = _group_end(self.toks, self.i)
        inner = self.child(self.toks[self.i + 1 : j])
        monos = inner.expr()
        if inner.i != len(inner.toks):
            raise _Refuse("unread tokens in fraction")
        self.widened = self.widened or inner.widened
        self.i = j + 1
        return monos

    def bigsum(self, binder: str | None) -> list[_Mono]:
        upper = None
        if binder is None:
            if not self.at_op("_"):
                raise _Refuse("sum without binder")
            self.take()
            binder = self.group_text()
        if self.at_op("^"):
            self.take()
            upper = self.group_text()
        nxt = self.peek()
        if nxt is None or not self.starts_factor(nxt):
            raise _Refuse("sum without body")
        # The body is read first so the binder letters can take their family
        # from the declared shapes of the symbols they index.
        body = self.term()
        pairs, widened = _binder_clauses(binder, upper, self, tail=False)
        self.widened = self.widened or widened
        letters = [p[0] for p in pairs]
        out: list[_Mono] = []
        for m in body:
            if any(letter in dict(m.sums) for letter in letters):
                raise _Refuse("nested sums reuse a binder letter")
            src = " ".join(binder.split()) + ("^" + " ".join(upper.split()) if upper else "")
            out.append(replace(m, sums=tuple(pairs) + m.sums, origin=(src, *m.origin)))
        return out

    def symbol(self, name: str) -> _Sym:
        ctx = self.ctx
        if not ctx.is_symbol(name):
            raise _Refuse(f"undeclared symbol {name!r}")
        subs: list[str] = []
        while True:
            t = self.peek()
            if t is None:
                break
            if t.kind == "op" and t.val == "_":
                self.take()
                subs.extend(_sub_pieces(self.group_text()))
                continue
            if t.kind == "op" and t.val == "^":
                self.take()
                sup = self.group_text()
                pieces = _sub_pieces(sup)
                if not pieces or not all(self.index_like(p, nested=True) for p in pieces):
                    raise _Refuse(f"superscript {sup!r} on {name!r}")
                if any(re.fullmatch(r"\d+", p) for p in pieces):
                    raise _Refuse(f"power {sup!r} on {name!r}")
                subs.extend(pieces)
                continue
            if t.kind == "open" and t.val == "(":
                j = _group_end(self.toks, self.i)
                inner = self.text[t.end : self.toks[j].start].strip()
                args = [_norm_piece(a) for a in _split_top(inner, ",;")]
                if args and all(self.index_like(a, nested=True) for a in args):
                    subs.extend(args)
                    self.i = j + 1
                    continue
            if (
                t.kind == "name"
                and t.val in ctx.bound
                and not ctx.is_symbol(t.val)
                and len(subs) < len(ctx.shape(name))
            ):
                # x_{i} t: a call argument whose parentheses an earlier rule removed
                subs.append(t.val)
                self.take()
                continue
            break
        subs = self.reorder(name, self.split_runs(subs))
        for piece in subs:
            if not _PIECE_OK_RE.fullmatch(piece):
                raise _Refuse(f"subscript {piece!r} on {name!r} is not an index expression")
        shape = ctx.shape(name)
        for pos, piece in enumerate(subs):
            m = re.match(_IDX_ATOM, piece)
            if m and pos < len(shape):
                self.usage.setdefault(m.group(), set()).add(shape[pos])
        return _Sym(name, tuple(subs))

    def index_like(self, piece: str, *, nested: bool) -> bool:
        """A subscript-position expression: a bound letter (with an offset) or,
        when ``nested``, a declared symbol indexed by bound letters."""
        p = " ".join(piece.split())
        ctx = self.ctx
        m = re.fullmatch(rf"({_IDX_ATOM})(?:\s*[+-]\s*(\d+|{_IDX_ATOM}))?", p)
        if m:
            base = m.group(1)
            return base in ctx.bound and not ctx.is_symbol(base)
        if nested:
            m2 = re.fullmatch(rf"({_IDX_ATOM})_\{{([^{{}}]*)\}}", p)
            if m2 and (ctx.is_symbol(m2.group(1)) or m2.group(1) in ctx.bound):
                return all(
                    re.fullmatch(_IDX_ATOM, q.strip()) is not None for q in _split_top(m2.group(2))
                )
        return False

    def split_runs(self, subs: list[str]) -> list[str]:
        """Spaced or glued index letters are one index each: ``x_{i j, k}`` and
        ``x_{ij, k}`` (with i and j bound, ``ij`` itself not) are ``x_{i, j, k}``."""
        ctx = self.ctx
        out: list[str] = []
        for piece in subs:
            parts: list[str] | None = None
            if _LETTERS_RUN_RE.fullmatch(piece):
                parts = piece.split()
            elif (
                re.fullmatch(r"[A-Za-z]{2,}", piece)
                and piece not in ctx.bound
                and not ctx.is_symbol(piece)
                and piece.lower() not in SCRIPT_LABELS
            ):
                parts = list(piece)
            if parts and all(q in ctx.bound and not ctx.is_symbol(q) for q in parts):
                out.extend(parts)
            else:
                out.append(piece)
        return out

    def reorder(self, name: str, subs: list[str]) -> list[str]:
        """Written subscript order -> declared shape order, when the body
        binds every letter over one family and those families are exactly the
        declared shape in another order (``x_{a, k}`` against ``shape=K,A``)."""
        shape = self.ctx.shape(name)
        if len(shape) < 2 or len(subs) != len(shape) or len(set(shape)) != len(shape):
            return subs
        fams: list[str] = []
        for piece in subs:
            m = re.match(_IDX_ATOM, piece)
            fam = self.ctx.letter_family.get(m.group()) if m else None
            if fam is None:
                return subs
            fams.append(fam)
        if tuple(fams) == shape or sorted(fams) != sorted(shape):
            return subs
        return [subs[fams.index(f)] for f in shape]


_MATHIT_RE = re.compile(r"\\mathit\{([^{}]*)\}")
_PIECE_OK_RE = re.compile(
    r"^(?:[A-Za-z]\w*(?:_\{(?:[A-Za-z0-9_, +-]|\{[A-Za-z0-9_, +-]*\})*\})?|\d+"
    r"|\\left\|\s*[A-Za-z]\w*\s*\\right\|)"
    r"(?:\s*[+-]\s*(?:\d+|[A-Za-z]\w*))?$"
)


def _norm_piece(piece: str) -> str:
    r"""One subscript piece in plain spelling: ``\mathit{a}`` -> ``a``,
    redundant braces and a stray leading ``_`` removed."""
    p = " ".join(piece.split())
    p = _MATHIT_RE.sub(lambda m: m.group(1).replace("\\_", "_").replace(" ", ""), p)
    while True:
        m = re.fullmatch(r"_?\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", p)
        if m is None:
            break
        p = m.group(1).strip()
    # a prime the source wrote apart from its letter: "j '" and v^{^{' '}}
    pm = re.fullmatch(r"([A-Za-z]\w*)\s*(?:\^\{\s*\^?\{?)?((?:\s*')+)\s*\}?\}?", p)
    if pm is not None:
        p = pm.group(1) + "p" * pm.group(2).count("'")
    # an index given by a labelled map, s_{r}^{d} or i_{a}^{+}: the label is
    # part of the map's name (s_d_{r}, i_plus_{a}), as for any symbol
    lm = re.fullmatch(r"([A-Za-z]\w*)(_\{[^{}]*\})\^\{?\s*([A-Za-z]\w*|[+*-])\s*\}?", p)
    if lm is not None:
        word = {"+": "plus", "-": "minus", "*": "star"}.get(lm.group(3), lm.group(3))
        p = f"{lm.group(1)}_{word}{lm.group(2)}"
    return p


_TUPLE_PIECE_RE = re.compile(
    r"^(?:\\left\s*)?[(〈\[]\s*(.*?)\s*(?:\\right\s*)?[)〉\]]$|^\\left\\langle\s*(.*?)\s*\\right\\rangle$"
)
_CASE_WORDS = frozenset({"if", "otherwise", "for", "and", "or", "else", "when"})
_SPACED_CASE_WORD_RE = re.compile(
    r"(?<![A-Za-z\\])(?:i\s+f|o\s+t\s+h\s+e\s+r\s+w\s+i\s+s\s+e)(?![A-Za-z])"
)
_CASE_ELEMENT_RE = re.compile(
    r"(?<![\w\\{^])([A-Za-z]\w*)\s*(?:=|\\neq?(?![A-Za-z]))\s*([A-Za-z]\w*)(?!\s*[\w_^{(]|\s*\\left)"
)
_RUN_MEMBER = r"(?:[A-Za-z]\w*(?:_\{[^{}]*\})?|\d+)"
_CALL_PIECE_RE = re.compile(
    r"^([A-Za-z]\w*(?:_\{[A-Za-z0-9_, +-]*\})?)\s*(?:\\left\s*)?\(\s*((?:[A-Za-z0-9_, +-]|\{[A-Za-z0-9_, +-]*\})*?)\s*(?:\\right\s*)?\)$"
)


def _sub_pieces(inner: str) -> list[str]:
    """The index expressions of one script group, in plain spelling.

    A tuple written inside a subscript groups indices (``d_{(v, s)}`` is
    ``d_{v, s}``); an index given by a map in function notation
    (``q_{i, t(\\delta)}``) is spelled like the subscripted form
    ``t_{\\delta}``; identifiers separated by spaces are separate indices
    (the MathML-derived spelling of ``x_{ij}``).
    """
    out: list[str] = []
    for raw in _split_top(inner):
        if not raw.strip():
            continue
        p = _norm_piece(raw)
        tm = _TUPLE_PIECE_RE.fullmatch(p)
        if tm is not None and "," in (tm.group(1) or tm.group(2) or ""):
            out.extend(_sub_pieces(tm.group(1) or tm.group(2)))
            continue
        cm = _CALL_PIECE_RE.fullmatch(p)
        if cm is not None and cm.group(2):
            head = re.fullmatch(r"([A-Za-z]\w*)(?:_\{([^{}]*)\})?", cm.group(1))
            assert head is not None
            args = [a.strip() for a in ((head.group(2) or "") + "," + cm.group(2)).split(",")]
            p = head.group(1) + "_{" + ",".join(a for a in args if a) + "}"
        if "," in p and "{" not in p:
            out.extend(q.strip() for q in p.split(",") if q.strip())
        elif re.search(r"[A-Za-z]", p) and re.fullmatch(rf"{_RUN_MEMBER}(?:\s+{_RUN_MEMBER})+", p):
            # letters (and fixed elements) written apart: i j, 1 k f
            out.extend(re.findall(_RUN_MEMBER, p))
        else:
            out.append(p)
    return out


def _scale(m: _Mono, k: Fraction) -> _Mono:
    return replace(m, coef=m.coef * k)


def _mul(a: list[_Mono], b: list[_Mono]) -> list[_Mono]:
    out: list[_Mono] = []
    for x in a:
        for y in b:
            xl = {s[0] for s in x.sums}
            yl = {s[0] for s in y.sums}
            if xl & yl:
                raise _Refuse("product of sums over the same letter")
            # a factor outside a sum must not use the sum's bound letter
            for letters, other in ((yl, x), (xl, y)):
                for sym in other.syms + other.dens:
                    for piece in sym.subs:
                        if set(re.findall(_IDX_ATOM, piece)) & letters:
                            raise _Refuse("free letter captured by a sum binder")
            if x.pw is not None and y.pw is not None:
                raise _Refuse("product of piecewise terms")
            out.append(
                _Mono(
                    x.coef * y.coef,
                    x.syms + y.syms,
                    x.sums + y.sums,
                    x.dens + y.dens,
                    x.origin + y.origin,
                    x.pw or y.pw,
                )
            )
    return out


def _div(a: list[_Mono], b: list[_Mono]) -> list[_Mono]:
    if len(b) != 1 or b[0].sums:
        raise _Refuse("division by a sum")
    d = b[0]
    if d.coef == 0:
        raise _Refuse("division by zero")
    if d.dens:
        raise _Refuse("nested division")
    out: list[_Mono] = []
    for x in a:
        xl = {s[0] for s in x.sums}
        for sym in d.syms:
            for piece in sym.subs:
                if set(re.findall(_IDX_ATOM, piece)) & xl:
                    raise _Refuse("free letter captured by a sum binder")
        out.append(replace(x, coef=x.coef / d.coef, dens=x.dens + d.syms))
    return out


# ---------------------------------------------------------------------------
# Binders and quantifier tails
# ---------------------------------------------------------------------------


def _family_name(toks: list[_Tok], text: str) -> tuple[str, int] | None:
    """``(family, tokens consumed)`` when ``toks`` starts with a set name:
    ``I``, ``\\mathcal{I}``, ``\\mathbf{\\mathcal{I}}``."""
    i = 0
    wrappers = 0
    while (
        i + 1 < len(toks)
        and toks[i].kind == "cmd"
        and toks[i].val in _SET_WRAPPERS
        and toks[i + 1].kind == "lb"
    ):
        i += 2
        wrappers += 1
    if i < len(toks) and toks[i].kind == "name":
        name = toks[i].val
        i += 1
        for _ in range(wrappers):
            if i < len(toks) and toks[i].kind == "rb":
                i += 1
            else:
                return None
        return name, i
    return None


def _homonym_letter(name: str, ctx: RowContext) -> bool:
    """An index letter that shares its name with a subscripted symbol (the
    time index ``t`` next to the times ``t_{e,a}``): written bare it is the
    letter, since the symbol never appears without its subscripts."""
    return bool(ctx.shape(name)) and name in ctx.letter_family


def _letter_family(letter: str, rd: _Reader) -> str | None:
    fams = rd.usage.get(letter)
    if fams and len(fams) == 1:
        return next(iter(fams))
    return rd.ctx.letter_family.get(letter)


def _split_clause_toks(toks: list[_Tok]) -> list[list[_Tok]]:
    """Split a binder/tail token run at top-level separators."""
    depths = _depths(toks)
    out: list[list[_Tok]] = []
    cur: list[_Tok] = []
    for t, d in zip(toks, depths, strict=True):
        is_sep = d == 0 and (
            (t.kind == "op" and t.val in ",;:")
            or t.kind == "bar"
            or (t.kind == "cmd" and t.val in (r"\mid", r"\vert", r"\colon"))
            or (t.kind == "cmd" and t.val in (r"\forall", r"\land", r"\wedge", *_SPACERS))
            or (t.kind == "text" and t.val.lower() in ("and", "for all", "for", "for each", ""))
            or (t.kind == "name" and t.val in ("and",))
        )
        if is_sep:
            out.append(cur)
            cur = []
        else:
            cur.append(t)
    out.append(cur)
    return [c for c in out if c]


def _is_dots(t: _Tok) -> bool:
    return (t.kind == "cmd" and t.val in _DOTS) or (t.kind == "op" and t.val in ".…")


def _binder_clauses(
    binder: str, upper: str | None, rd: _Reader, *, tail: bool
) -> tuple[list[tuple[str, str]], bool]:
    """``(letter, family)`` pairs of a ``\\sum`` binder; second value says
    whether anything was widened. Raises :class:`_Refuse` otherwise."""
    pairs, extras, widened = _clauses(binder, rd, tail=tail)
    if upper is not None:
        widened = True  # a range i = a .. b is read as the letter's family
    if extras:
        widened = True  # a sum has no field for a restriction
    if widened and not rd.widen:
        raise _Refuse("binder needs widening")
    if not pairs:
        raise _Refuse("binder binds nothing")
    return pairs, widened


def _clauses(src: str, rd: _Reader, *, tail: bool) -> tuple[list[tuple[str, str]], list[str], bool]:
    """Read binder or tail clauses.

    Returns ``(pairs, restrictions, widened)``: the ``(letter, family)`` pairs
    in order, the exact restrictions kept (``i \\neq j``), and whether a
    clause had to be widened or dropped.
    """
    ctx = rd.ctx
    toks = _lex(src)
    pairs: list[tuple[str, str]] = []
    restrictions: list[str] = []
    widened = False
    range_open = False  # inside "i = 1, 2, ..., n": the items after the first
    pending: list[str] = []  # lone letters waiting for a following ``\in``

    def bind(letter: str, fam: str | None, *, exact: bool) -> None:
        nonlocal widened
        rd.shadowed.add(letter)
        if fam is None:
            fam = _letter_family(letter, rd)
            if fam is None:
                if letter in rd.usage or not tail:
                    raise _Refuse(f"no single family for binder letter {letter!r}")
                return  # an unused tail letter binds nothing in this row
        if not exact:
            widened = True
        for k, (other, _f) in enumerate(pairs):
            if other == letter:
                pairs[k] = (letter, fam)
                return
        pairs.append((letter, fam))

    def flush_pending() -> None:
        for letter in pending:
            bind(letter, None, exact=True)
        pending.clear()

    for cl in _split_clause_toks(toks):
        depths = _depths(cl)
        ins = [
            k
            for k, t in enumerate(cl)
            if depths[k] == 0 and t.kind == "cmd" and t.val in (r"\in", r"\ni")
        ]
        if len(ins) >= 1:
            k = ins[0]
            lhs, rhs = cl[:k], cl[k + 1 :]
            range_open = False
            if len(ins) > 1:
                raise _Refuse("several memberships in one clause")
            fam = _family_name(rhs, src)
            # --- left side: letters, a tuple, or name = tuple
            letters: list[str] = []
            tuple_letters: list[str] = []
            named: str | None = None
            lt = list(lhs)
            if len(lt) >= 2 and lt[0].kind == "name" and lt[1].kind == "op" and lt[1].val == "=":
                named = lt[0].val
                lt = lt[2:]
            if (
                lt
                and lt[0].kind == "open"
                and lt[-1].kind == "close"
                and _group_end(lt, 0) == len(lt) - 1
            ):
                for t in lt[1:-1]:
                    if t.kind == "name":
                        tuple_letters.append(t.val)
                    elif not (t.kind == "op" and t.val == ","):
                        raise _Refuse("tuple binder with a non-letter member")
            elif lt and all(t.kind == "name" or (t.kind == "op" and t.val == ",") for t in lt):
                letters = [t.val for t in lt if t.kind == "name"]
            elif not lt and named is None:
                raise _Refuse("membership without a subject")
            else:
                # x_{i} \in \{0, 1\}: a domain statement about a declared symbol
                if lt and lt[0].kind == "name" and ctx.is_symbol(lt[0].val) and tail:
                    widened = True
                    continue
                # s + 1 \in S: the neighbour of a bound letter exists; a
                # condition on that letter, which the model has no field for
                offset = (
                    len(lt) == 3
                    and lt[0].kind == "name"
                    and lt[1].kind == "op"
                    and lt[1].val in "+-"
                    and lt[2].kind == "num"
                )
                if offset and not ctx.is_symbol(lt[0].val) and named is None:
                    widened = True
                    continue
                raise _Refuse("binder subject not understood")
            shared = list(pending)  # "h, i \in I": letters listed before the subject
            pending.clear()
            if fam is not None and fam[1] == len(rhs):
                family: str | None = fam[0]
                exact = True
                base = re.sub(r"_.*$", "", fam[0])
                if family not in ctx.indices and base in ctx.indices:
                    family = base  # a labelled subset E_de of a declared family E
                    exact = False
            elif fam is not None:
                family = fam[0]  # a restricted, scripted or combined set: its base family
                exact = False
                rest_toks = rhs[fam[1] :]
                if any(t.kind == "cmd" and t.val == r"\cup" for t in rest_toks):
                    others = {t.val for t in rest_toks if t.kind == "name"}
                    base = re.sub(r"_.*$", "", family)
                    if any(re.sub(r"_.*$", "", o) != base for o in others if o[:1].isupper()):
                        raise _Refuse("union of different families")
            else:
                family = None  # an enumerated set or interval: the letter's own family
                exact = False
            for letter in shared:
                own = _letter_family(letter, rd)
                if own is not None or family is None or named is not None or tuple_letters:
                    bind(letter, own, exact=True)
                else:
                    bind(letter, family, exact=exact)
            if named is not None:
                if family is not None and (named in rd.usage or not tuple_letters):
                    bind(named, family, exact=exact)
                for letter in tuple_letters:
                    bind(letter, None, exact=False)
            elif tuple_letters:
                for letter in tuple_letters:
                    bind(letter, None, exact=False)
            else:
                for letter in letters:
                    if family is not None:
                        bind(letter, family, exact=exact)
                    else:
                        bind(letter, None, exact=False)
            continue
        # --- no membership in this clause
        if all(t.kind == "name" or (t.kind == "op" and t.val == ",") for t in cl):
            names = [t.val for t in cl if t.kind == "name"]
            if range_open:
                widened = True  # the upper end of a range: i = 1, ..., n
                continue
            if any(ctx.is_symbol(n) and not _homonym_letter(n, ctx) for n in names):
                raise _Refuse("stray symbol in binder")
            pending.extend(names)
            continue
        flush_pending()
        rels = [
            k
            for k, t in enumerate(cl)
            if depths[k] == 0
            and (
                (t.kind == "op" and t.val in "=<>")
                or (t.kind == "cmd" and (t.val in _REL_CMDS or t.val in (r"\ne", r"\neq")))
            )
        ]
        if cl[0].kind == "name" and len(cl) == 3 and cl[2].kind == "name" and tail:
            # a restriction between two bound letters is exact: i \ne j, i < j
            a, op, b = cl[0].val, cl[1], cl[2].val
            spelled = {
                r"\ne": r"\neq",
                r"\neq": r"\neq",
                "<": "<",
                ">": ">",
                r"\prec": r"\prec",
            }.get(op.val) or {"le": r"\leq", "ge": r"\geq"}.get(_REL_CMDS.get(op.val, ""), "")
            if spelled and not ctx.is_symbol(a) and not ctx.is_symbol(b):
                restrictions.append(f"{a} {spelled} {b}")
                continue
        if (
            tail
            and len(rels) == 1
            and cl[0].kind == "name"
            and cl[0].val in ctx.params
            and cl[rels[0]].val == "="
        ):
            # a where-clause p_{i} = v on a quantified letter is exact
            src_cl = src[cl[0].start : cl[-1].end]
            wm = re.fullmatch(
                r"(?:\\mathit\{[^{}]*\}|[A-Za-z_]\w*)_\{\s*([A-Za-z]\w*)\s*\}\s*=\s*"
                r"(-?\d+(?:\.\d+)?|\\mathrm\{\w+\})",
                src_cl.strip(),
            )
            if wm and ctx.shape(cl[0].val) and len(ctx.shape(cl[0].val)) == 1:
                restrictions.append("WHERE " + wm.group(1) + " " + " ".join(src_cl.split()))
                continue
        # a range or bound on a letter: i = 1, ..., n / i \ge 2 / i = 1
        if (
            cl[0].kind == "name"
            and rels
            and rels[0] == 1
            and (not ctx.is_symbol(cl[0].val) or _homonym_letter(cl[0].val, ctx))
        ):
            if any(t.kind == "name" and t.val in ctx.variables for t in cl[2:]):
                raise _Refuse("condition mentions a variable")
            bind(cl[0].val, None, exact=False)
            widened = True
            range_open = True
            continue
        # "1 \le i \le n": a range around a letter
        if len(rels) == 2:
            mid = cl[rels[0] + 1 : rels[1]]
            if (
                len(mid) == 1
                and mid[0].kind == "name"
                and (not ctx.is_symbol(mid[0].val) or _homonym_letter(mid[0].val, ctx))
            ):
                if any(t.kind == "name" and t.val in ctx.variables for t in cl):
                    raise _Refuse("condition mentions a variable")
                bind(mid[0].val, None, exact=False)
                widened = True
                continue
        # dots or numbers continuing a range: "2, \ldots, n"
        if all(_is_dots(t) or t.kind in ("num",) for t in cl):
            widened = True
            continue
        # "\ldots T": the dots and the upper end of a range in one clause. The
        # end is a number whatever else carries its letter (a subscripted
        # symbol T_{w} is never written bare).
        ends = [t for t in cl if not (_is_dots(t) or t.kind == "num")]
        if (
            len(ends) == 1
            and len(ends) < len(cl)
            and any(_is_dots(t) for t in cl)
            and ends[0].kind == "name"
            and (ends[0].val not in ctx.variables or ctx.shape(ends[0].val))
        ):
            widened = True
            continue
        # anything else is a condition the model has no field for. It may be
        # dropped only when it is a filter on data: every name in it must be a
        # declared parameter, an index family, a bound letter or a plain word.
        # A statement about a variable (or about a symbol nobody declared) is
        # algebra and is never dropped; a trailing domain statement
        # "x_{i} \ge 0" is the one exception.
        if not (tail and _is_domain_statement(cl, ctx)):
            for t in cl:
                if t.kind != "name":
                    continue
                known = (
                    ctx.is_param(t.val)
                    or t.val in ctx.indices
                    or t.val in ctx.bound
                    or t.val.lower() in _CONDITION_WORDS
                )
                if t.val in ctx.variables or not known:
                    raise _Refuse(f"tail clause mentions {t.val!r}")
        widened = True
    flush_pending()
    return pairs, restrictions, widened


def _is_domain_statement(cl: list[_Tok], ctx: RowContext) -> bool:
    """``x_{i} \\ge 0`` / ``x \\in \\{0, 1\\}`` — a statement about one variable only."""
    if not cl or cl[0].kind != "name" or cl[0].val not in ctx.variables:
        return False
    i = 1
    while i < len(cl) and cl[i].kind == "op" and cl[i].val in "_^":
        if i + 1 < len(cl) and cl[i + 1].kind == "lb":
            i = _group_end(cl, i + 1) + 1
        else:
            i += 2
    rest = cl[i:]
    if len(rest) == 2 and rest[0].kind == "cmd" and rest[0].val in (r"\ge", r"\geq", r"\geqslant"):
        return rest[1].kind == "num" and rest[1].val == "0"
    return False


# ---------------------------------------------------------------------------
# Row splitting
# ---------------------------------------------------------------------------


def _tail_start(toks: list[_Tok], ctx: RowContext) -> int:
    """Index of the first token of the quantifier tail (``len(toks)`` if none):
    the earliest of a ``\\forall``/spacer/"for" word, a top-level comma whose
    remainder is tail material, and the subject of a bare top-level membership."""
    depths = _depths(toks)
    n = len(toks)
    cands = [n]
    for k, t in enumerate(toks):
        if depths[k] != 0:
            continue
        if (
            (t.kind == "cmd" and t.val in (r"\forall", *_SPACERS))
            or (t.kind == "text" and t.val.lower().split(" ")[0] in _TAIL_WORDS)
            or (t.kind == "name" and t.val in ("for", "forall", "where"))
        ):
            cands.append(k)
            break
    # a top-level comma/semicolon whose remainder is all tail material
    for k, t in enumerate(toks):
        if depths[k] == 0 and t.kind == "op" and t.val in ",;":
            rest = toks[k + 1 :]
            if not rest:
                cands.append(k)
                break
            rd = depths[k + 1 :]
            has_in = any(
                d == 0 and x.kind == "cmd" and x.val == r"\in"
                for x, d in zip(rest, rd, strict=True)
            )
            first = rest[0]
            starts_letter = first.kind == "name" and not ctx.is_symbol(first.val)
            if has_in or starts_letter or first.kind == "open":
                cands.append(k)
                break
    # a bare membership glued to the algebra: "... - d_{t} t \\in T, s \\in R"
    for k, t in enumerate(toks):
        if depths[k] == 0 and t.kind == "cmd" and t.val == r"\in":
            j = k - 1
            if j >= 0 and toks[j].kind == "close":
                d = 0
                while j >= 0:
                    if toks[j].kind in ("close", "rb"):
                        d += 1
                    elif toks[j].kind in ("open", "lb"):
                        d -= 1
                        if d == 0:
                            break
                    j -= 1
                if (
                    j >= 2
                    and toks[j - 1].kind == "op"
                    and toks[j - 1].val == "="
                    and toks[j - 2].kind == "name"
                ):
                    j -= 2
                cands.append(max(j, 0))
                break
            while j >= 0 and toks[j].kind == "name":
                if j >= 1 and toks[j - 1].kind == "op" and toks[j - 1].val == ",":
                    j -= 2
                else:
                    j -= 1
                    break
            cands.append(j + 1)
            break
    return min(cands)


def _is_label(toks: list[_Tok]) -> bool:
    """One symbol with its scripts and an optional argument list: ``Z``,
    ``Z_{1}``, ``f \\left(x , y\\right)``."""
    if not toks:
        return False
    if toks[0].kind == "name":
        i = 1
    elif toks[0].kind == "cmd" and toks[0].val in _SET_WRAPPERS and len(toks) > 1:
        if toks[1].kind != "lb":
            return False
        i = _group_end(toks, 1) + 1
    else:
        return False
    while i < len(toks) and toks[i].kind == "op" and toks[i].val in "_^":
        if i + 1 < len(toks) and toks[i + 1].kind == "lb":
            i = _group_end(toks, i + 1) + 1
        else:
            i += 2
    if i < len(toks) and toks[i].kind == "open":
        i = _group_end(toks, i) + 1
    return i >= len(toks)


def _relations(toks: list[_Tok]) -> list[tuple[int, str, bool]]:
    """Top-level relation tokens as ``(position, comparator, strict)``."""
    depths = _depths(toks)
    out: list[tuple[int, str, bool]] = []
    for k, t in enumerate(toks):
        if depths[k] != 0:
            continue
        if t.kind == "op" and t.val == "=":
            out.append((k, "eq", False))
        elif t.kind == "op" and t.val in "<>":
            out.append((k, "le" if t.val == "<" else "ge", True))
        elif t.kind == "cmd" and t.val in _REL_CMDS:
            out.append((k, _REL_CMDS[t.val], False))
    return out


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


def _num_text(x: Fraction) -> str:
    if x.denominator == 1:
        return str(x.numerator)
    rest = x.denominator
    for p in (2, 5):
        while rest % p == 0:
            rest //= p
    if rest != 1:
        raise _Refuse("coefficient has no terminating decimal")
    text = f"{float(x):.12f}".rstrip("0").rstrip(".")
    if Fraction(text) != x:
        raise _Refuse("coefficient does not print exactly")
    return text


def _sym_text(s: _Sym) -> str:
    base = s.name if len(s.name) == 1 else r"\mathit{" + s.name.replace("_", r"\_") + "}"
    if not s.subs:
        return base
    return base + "_{" + ",".join(s.subs) + "}"


def _set_text(family: str) -> str:
    return r"\mathcal{" + family.replace("_", r"\_") + "}"


def _num_ident(x: Fraction) -> str:
    text = _num_text(x)
    return "n" + text.replace(".", "p").replace("-", "m")


def derived_declaration(name: str, shape: tuple[str, ...], definition: str) -> str:
    """The header line a derived parameter (or auxiliary variable) needs."""
    shape_s = ",".join(shape) if shape else "-"
    if definition.startswith("var:"):
        _var, domain, what = definition.split(":", 2)
        return (
            f"%@ var {name} shape={shape_s} domain={domain} role=auxiliary "
            f"drole=auxiliary_linearization lo=- hi=- :: derived: {what}"
        )
    kind = "scalar" if not shape else "vector" if len(shape) == 1 else "matrix"
    return f"%@ param {name} shape={shape_s} kind={kind} domain=- :: derived: {definition}"


def _derive(mag: Fraction, nums: list[_Sym], dens: list[_Sym], ctx: RowContext) -> _Sym:
    """Fold ``mag * prod(nums) / prod(dens)`` (all parameters, ``mag > 0``)
    into one derived parameter and return it as a symbol."""
    parts: list[str] = []
    define: list[str] = []
    if mag != 1:
        parts.append(_num_ident(mag))
        define.append(_num_text(mag))
    for s in nums:
        parts.append(s.name)
        define.append(s.name)
    name = "_x_".join(parts) if parts else "n1"
    definition = " * ".join(define) if define else "1"
    if dens:
        name += "_over_" + "_x_".join(s.name for s in dens)
        definition += " / " + (" / ".join(s.name for s in dens))
    # shape: the distinct index expressions of the factors, each with the
    # family its own declaration gives that position
    exprs: list[str] = []
    shape: list[str] = []
    for s in [*nums, *dens]:
        fshape = ctx.shape(s.name)
        if len(fshape) != len(s.subs):
            raise _Refuse(f"factor {s.name!r} is written with a different arity than declared")
        for fam, e in zip(fshape, s.subs, strict=True):
            if e in exprs:
                if shape[exprs.index(e)] != fam:
                    raise _Refuse("one index expression over two families")
                continue
            exprs.append(e)
            shape.append(fam)
    if ctx.is_symbol(name) and name not in ctx.derived:
        # A document that already declares the derived parameter (a canonical
        # document read again) uses the declaration as it stands.
        if name in ctx.params and ctx.shape(name) == tuple(shape):
            return _Sym(name, tuple(exprs))
        raise _Refuse(f"derived name {name!r} collides with a declared symbol")
    known = ctx.derived.get(name)
    if known is not None and known[0] != tuple(shape):
        raise _Refuse(f"derived parameter {name!r} would need two shapes")
    ctx.derived[name] = (tuple(shape), definition)
    return _Sym(name, tuple(exprs))


def _coefficient(coef: _Sym, ref: _Sym, m: _Mono, ctx: RowContext, scope: dict[str, str]) -> _Sym:
    """The coefficient as the canonical term can carry it.

    A canonical coefficient is a bare parameter name; its indices are implied:
    the referent's own when the shapes agree, otherwise the one letter in
    scope per family. ``t_{k-1} \\cdot x_{i,k}`` or ``n_{p} \\cdot z_{p,q}``
    (two letters of one family in scope) have no such reading. The parameter
    *as seen from the referent's position* is still data, so it becomes a
    derived parameter over the referent's shape.
    """
    if not coef.subs:
        return coef
    cshape, rshape = ctx.shape(coef.name), ctx.shape(ref.name)
    if len(cshape) != len(coef.subs) or len(rshape) != len(ref.subs):
        return coef  # an arity the declarations do not know: the parser's finding
    if coef.subs == ref.subs and cshape == rshape:
        return coef
    in_scope: dict[str, set[str]] = {}
    for letter, fam in (*scope.items(), *m.sums):
        in_scope.setdefault(fam, set()).add(letter)
    for fam, expr in zip(rshape, ref.subs, strict=True):
        if re.fullmatch(_IDX_ATOM, expr):
            in_scope.setdefault(fam, set()).add(expr)
    if all(in_scope.get(fam) == {e} for fam, e in zip(cshape, coef.subs, strict=True)):
        return coef
    # Only a coefficient written consistently with its own declaration is
    # re-read from the referent's position: every index letter must be in
    # scope over the family the coefficient declares for that place. A
    # coefficient indexed by a foreign letter (b over J written b_{e}) is the
    # parser's finding and stays one.
    for fam, expr in zip(cshape, coef.subs, strict=True):
        if re.fullmatch(r"\d+", expr):
            continue  # a fixed element, t_{0}: the same number wherever it is read
        lm = re.match(_IDX_ATOM, expr)
        if lm is None or lm.group() not in in_scope.get(fam, set()):
            return coef
    slug = re.sub(r"[^A-Za-z0-9]", "", "_".join(coef.subs).replace("-", "m").replace("+", "p"))
    name = f"{coef.name}_{slug}_on_{ref.name}"
    if ctx.is_symbol(name) and name not in ctx.derived:
        if not (name in ctx.params and ctx.shape(name) == rshape):
            raise _Refuse(f"derived name {name!r} collides with a declared symbol")
    else:
        ctx.derived[name] = (
            rshape,
            f"{coef.name}[{', '.join(coef.subs)}] at {ref.name}[{', '.join(ref.subs)}]",
        )
    return _Sym(name, ref.subs)


def _emit_mono(m: _Mono, ctx: RowContext, scope: dict[str, str] | None = None) -> tuple[int, str]:
    scope = scope or {}
    if m.pw is not None:
        # the canonical grammar has |coef * ref| as a term of its own
        if not _single_term_abs(m):
            raise _Refuse("piecewise term outside a bound")
        _inner_sign, inner = _emit_mono(m.pw.branches[0][0], ctx, scope)
        return (-1 if m.coef < 0 else 1), rf"\left| {inner} \right|"
    if any(s.name == _INDEX_VALUE for s in (*m.syms, *m.dens)):
        raise _Refuse("index letter used as a value where no binder is known")
    variables = [s for s in m.syms if ctx.is_var(s.name)]
    params = [s for s in m.syms if not ctx.is_var(s.name)]
    if len(variables) > 1:
        raise _Refuse("product of variables")
    if any(ctx.is_var(s.name) for s in m.dens):
        raise _Refuse("division by a variable")
    if m.coef == 0:
        raise _Refuse("zero term")
    sign = -1 if m.coef < 0 else 1
    mag = abs(m.coef)
    dens = list(m.dens)
    body: str
    if variables:
        var = variables[0]
        if not params and not dens:
            body = _sym_text(var) if mag == 1 else f"{_num_text(mag)} \\cdot {_sym_text(var)}"
        else:
            coef = (
                params[0]
                if len(params) == 1 and not dens and mag == 1
                else _derive(mag, params, dens, ctx)
            )
            body = _sym_text(_coefficient(coef, var, m, ctx, scope)) + r" \cdot " + _sym_text(var)
    elif not params and not dens:
        body = _num_text(mag)
    elif len(params) == 1 and not dens:
        body = (
            _sym_text(params[0]) if mag == 1 else f"{_num_text(mag)} \\cdot {_sym_text(params[0])}"
        )
    elif len(params) == 2 and not dens and mag == 1 and not (params[0].subs and params[1].subs):
        a, b = params
        if a.subs:
            a, b = b, a  # the scalar is the coefficient
        body = _sym_text(a) + r" \cdot " + _sym_text(b)
    else:
        body = _sym_text(_derive(mag, params, dens, ctx))
    if m.sums:
        binders = ", ".join(letter + r" \in " + _set_text(fam) for letter, fam in m.sums)
        body = rf"\sum_{{{binders}}} {body}"
    return sign, body


def _single_term_abs(m: _Mono) -> bool:
    """``|coef * ref|`` with nothing outside the bars but a sign."""
    if m.pw is None or m.pw.kind != "abs" or len(m.pw.branches[0]) != 1:
        return False
    if abs(m.coef) != 1 or m.syms or m.sums or m.dens:
        return False
    inner = m.pw.branches[0][0]
    return inner.coef > 0 and not inner.sums and inner.pw is None and len(inner.syms) >= 1


def _emit_side(monos: list[_Mono], ctx: RowContext, scope: dict[str, str] | None = None) -> str:
    monos = [m for m in monos if m.coef != 0]
    if not monos:
        return "0"
    parts: list[str] = []
    for k, m in enumerate(monos):
        sign, body = _emit_mono(m, ctx, scope)
        if k == 0:
            parts.append(("- " if sign < 0 else "") + body)
        else:
            parts.append(("- " if sign < 0 else "+ ") + body)
    return " ".join(parts)


_INDEX_VALUE: Final = "__index_value__"


def _is_index_value(monos: list[_Mono]) -> bool:
    return (
        len(monos) == 1
        and len(monos[0].syms) == 1
        and monos[0].syms[0].name == _INDEX_VALUE
        and not monos[0].sums
    )


def _index_values(
    sides: list[list[_Mono]], pairs: list[tuple[str, str]], rd: _Reader
) -> list[list[_Mono]]:
    """Resolve index-value placeholders: ``t`` used as a number, with ``t``
    bound in this row over the family ``T``, is the derived parameter
    ``val_T`` indexed by ``t`` (the numeric value of an index element is
    data). A letter this row does not bind is refused."""
    ctx = rd.ctx
    tail = dict(pairs)
    out: list[list[_Mono]] = []
    for monos in sides:
        new: list[_Mono] = []
        for m in monos:
            local = dict(m.sums)

            def fix(sym: _Sym, local: dict[str, str] = local) -> _Sym:
                if sym.name != _INDEX_VALUE:
                    return sym
                letter = sym.subs[0]
                fam = local.get(letter) or tail.get(letter)
                if fam is None:
                    raise _Refuse(f"letter {letter!r} is used as a value but not bound in this row")
                name = "val_" + fam
                if ctx.is_symbol(name) and name not in ctx.derived:
                    if not (name in ctx.params and ctx.shape(name) == (fam,)):
                        raise _Refuse(f"derived name {name!r} collides with a declared symbol")
                else:
                    ctx.derived[name] = ((fam,), f"numeric value of the index over {fam}")
                return _Sym(name, (letter,))

            new.append(
                replace(m, syms=tuple(fix(s) for s in m.syms), dens=tuple(fix(s) for s in m.dens))
            )
        out.append(new)
    return out


def _piecewise_bound(
    sides: list[list[_Mono]], cmps: list[str]
) -> tuple[list[list[_Mono]], list[str], list[tuple[str, str]]]:
    """A piecewise term bounding from the convex side is a conjunction.

    ``|e| \\le b`` is ``-b \\le e \\le b``; ``max(e_1, e_2) \\le b`` is
    ``e_1 \\le b`` and ``e_2 \\le b``; ``b \\le min(e_1, e_2)`` likewise;
    an extremum over a binder quantifies the one inequality over it. These are
    the places such a term has an exact linear spelling: alone on the smaller
    (max, abs) or larger (min) side of a single inequality whose other side
    holds none. Returns the new sides, comparators and quantifier pairs to
    add; every other occurrence stays in the terms and is refused at emission.
    """
    flat = [m for monos in sides for m in monos if m.pw is not None and not _single_term_abs(m)]
    if not flat:
        return sides, cmps, []
    if len(flat) != 1 or len(sides) != 2 or len(cmps) != 1:
        raise _Refuse("piecewise term outside a bound")
    k = 0 if any(m.pw is not None for m in sides[0]) else 1
    (mono,) = flat
    pw = mono.pw
    assert pw is not None
    alone = len([m for m in sides[k] if m.coef != 0]) == 1
    plain = mono.coef == 1 and not (mono.syms or mono.sums or mono.dens)
    smaller = (k == 0 and cmps[0] == "le") or (k == 1 and cmps[0] == "ge")
    larger = (k == 0 and cmps[0] == "ge") or (k == 1 and cmps[0] == "le")
    nested = any(m.pw is not None for b in pw.branches for m in b)
    if not (alone and plain) or nested or any(m.pw is not None for m in sides[1 - k]):
        raise _Refuse("piecewise term outside a bound")
    bound = sides[1 - k]
    branches = [list(b) for b in pw.branches]
    extra = list(pw.binders)
    if pw.kind == "abs" and smaller:
        return [[_scale(m, Fraction(-1)) for m in bound], branches[0], bound], ["le", "le"], extra
    if pw.kind == "max" and smaller:
        if len(branches) == 1:
            return [branches[0], bound], ["le"], extra
        if len(branches) == 2:
            return [branches[0], bound, branches[1]], ["le", "ge"], extra
    if pw.kind == "min" and larger:
        if len(branches) == 1:
            return [bound, branches[0]], ["le"], extra
        if len(branches) == 2:
            return [branches[0], bound, branches[1]], ["ge", "le"], extra
    raise _Refuse("piecewise term outside a bound")


def _free_letters(m: _Mono, ctx: RowContext) -> list[str]:
    """Index letters a term uses without binding them (its own sums and the
    binders of a piecewise factor bind theirs)."""
    out: list[str] = []
    bound_here = {letter for letter, _fam in m.sums}

    def visit(x: _Mono, bound: set[str]) -> None:
        local = bound | {letter for letter, _fam in x.sums}
        for sym in (*x.syms, *x.dens):
            for piece in sym.subs:
                for atom in re.findall(_IDX_ATOM, piece):
                    free = atom in ctx.bound and not ctx.is_symbol(atom) and atom not in local
                    if free and atom not in out:
                        out.append(atom)
        if x.pw is not None:
            inner = local | {letter for letter, _fam in x.pw.binders}
            for branch in x.pw.branches:
                for y in branch:
                    visit(y, inner)

    visit(m, bound_here)
    return out


def _objective_scope(monos: list[_Mono], ctx: RowContext) -> tuple[list[_Mono], bool]:
    """An objective is a number, so a term with a free index letter is summed.

    ``\\sum_{i, k} |a_{ik}| + |d_{ik}|`` means the sum over both terms: the
    author's ``\\sum`` reaches further than the grammar's. A free letter is
    bound by the nearest sum written before the term that binds that letter;
    with none, the row is refused. Returns the terms and whether any scope
    was extended (a reading of the notation, recorded as widening).
    """
    out: list[_Mono] = []
    extended = False
    for k, m in enumerate(monos):
        free = _free_letters(m, ctx)
        if not free:
            out.append(m)
            continue
        add: list[tuple[str, str]] = []
        for letter in free:
            fam = next(
                (f for prev in reversed(monos[:k]) for le, f in prev.sums if le == letter), None
            )
            if fam is None:
                raise _Refuse(f"letter {letter!r} of an objective term is not summed")
            add.append((letter, fam))
        out.append(replace(m, sums=(*add, *m.sums)))
        extended = True
    return out, extended


def _epigraph(
    monos: list[_Mono], sense: str, row_id: str, rd: _Reader
) -> tuple[list[_Mono], list[tuple[str, str]]]:
    """A piecewise term of an objective, moved into constraints.

    Minimising ``w |e|`` or ``w max(e_1, e_2)`` with ``w \\ge 0`` is
    minimising ``w u`` subject to ``u \\ge e`` and ``u \\ge -e`` (or
    ``u \\ge e_k``): the standard exact reformulation with an explicit
    auxiliary variable. The mirror cases (maximising ``-w |e|``, ``w min(..)``)
    are covered; the non-convex ones are refused. A symbolic weight is taken
    to be non-negative, which the derived variable's description states.

    Returns the objective's terms with each piecewise term replaced by its
    auxiliary variable, and the defining rows as ``(tag suffix, row text)``.
    """
    ctx = rd.ctx
    out: list[_Mono] = []
    rows: list[tuple[str, str]] = []
    n = 0
    for m in monos:
        pw = m.pw
        if pw is None or _single_term_abs(m):
            out.append(m)
            continue
        if any(ctx.is_var(s.name) for s in (*m.syms, *m.dens)):
            raise _Refuse("piecewise term multiplied by a variable")
        upper = pw.kind in ("abs", "max")  # the auxiliary variable bounds from above
        positive = m.coef > 0
        convex = (sense == "min") == (positive == upper)
        if not convex or any(x.pw is not None for b in pw.branches for x in b):
            raise _Refuse("piecewise term the objective cannot linearise")
        n += 1
        outer = dict(m.sums)
        inner_letters = {letter for letter, _fam in pw.binders}
        letters: list[str] = []
        for branch in pw.branches:
            for x in branch:
                local = {letter for letter, _fam in x.sums} | inner_letters
                for sym in (*x.syms, *x.dens):
                    for piece in sym.subs:
                        for atom in re.findall(_IDX_ATOM, piece):
                            if atom in local or ctx.is_symbol(atom):
                                continue
                            if atom in outer:
                                if atom not in letters:
                                    letters.append(atom)
                            elif atom in ctx.bound:
                                raise _Refuse(f"letter {atom!r} of a piecewise term is not summed")
        letters = [x for x in outer if x in letters]  # the order the sums bind them in
        name = f"aux_{row_id}_{n}"
        if ctx.is_symbol(name) and name not in ctx.derived:
            raise _Refuse(f"derived name {name!r} collides with a declared symbol")
        domain = "non_negative" if pw.kind == "abs" else "continuous"
        what = {"abs": "absolute value", "max": "maximum", "min": "minimum"}[pw.kind]
        ctx.derived[name] = (
            tuple(outer[x] for x in letters),
            f"var:{domain}:{what} term {n} of the objective {row_id}, weight taken as non-negative",
        )
        aux = _Sym(name, tuple(letters))
        out.append(replace(m, pw=None, syms=(*m.syms, aux)))
        quantified = [(x, outer[x]) for x in letters] + list(pw.binders)
        scope = dict(quantified)
        tail = ""
        if quantified:
            tail = r" \qquad " + r",\; ".join(
                r"\forall " + letter + r" \in " + _set_text(fam) for letter, fam in quantified
            )
        lhs = _emit_side([_Mono(Fraction(1), (aux,))], ctx, scope)
        branches = [list(b) for b in pw.branches]
        if pw.kind == "abs":
            branches = [branches[0], [_scale(x, Fraction(-1)) for x in branches[0]]]
        cmp = r"\ge" if upper else r"\le"
        for k, side in enumerate(branches, start=1):
            rows.append((f"aux{n}_{k}", f"{lhs} {cmp} {_emit_side(side, ctx, scope)}{tail}"))
    return out, rows


def _merge_guard(sides: list[list[_Mono]], ctx: RowContext) -> None:
    """Widening must not merge terms the source keeps apart.

    A balance row sums the same variable over two different restricted sets
    (in-arcs minus out-arcs). Widened to the base family both sums become the
    same term and the row a tautology: such a row is refused, not promoted.
    """
    seen: dict[str, tuple[str, ...]] = {}
    for monos in sides:
        for m in monos:
            if m.coef == 0 or not m.sums or m.pw is not None:
                continue
            _sign, body = _emit_mono(replace(m, coef=abs(m.coef)), ctx)
            first = seen.setdefault(body, m.origin)
            if first != m.origin:
                raise _Refuse("widening would merge sums over different sets")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_TRAILING_RE = re.compile(r"(?:[\s.,;:]|\\quad|\\qquad|\\;|\\,)+$")


def canonicalize_row(
    body: str,
    ctx: RowContext,
    *,
    objective: bool,
    widen: bool,
    sense: str = "min",
    row_id: str = "row",
) -> tuple[str, bool, list[tuple[str, str]]] | None:
    """Canonical spelling of one row body (the text between ``&`` and
    ``\\tag``), or ``None`` when the row is left to the parser.

    Returns ``(text, widened, extra rows)``. With ``widen=False`` only exact
    rewrites are produced; a row that needs a widened binder or a dropped tail
    condition returns ``None`` and is retried by the widening rule. The extra
    rows, ``(tag suffix, row text)``, define the auxiliary variables an
    objective's piecewise terms were replaced by (``sense`` says which way the
    objective runs, ``row_id`` names them).
    """
    snapshot = dict(ctx.derived)
    try:
        return _canonicalize(
            body, ctx, objective=objective, widen=widen, sense=sense, row_id=row_id
        )
    except _Refuse:
        ctx.derived.clear()
        ctx.derived.update(snapshot)
        return None
    except (RecursionError, ZeroDivisionError, ValueError, IndexError):
        ctx.derived.clear()
        ctx.derived.update(snapshot)
        return None


def _canonicalize(
    body: str, ctx: RowContext, *, objective: bool, widen: bool, sense: str, row_id: str
) -> tuple[str, bool, list[tuple[str, str]]]:
    text = _TRAILING_RE.sub("", body.strip())
    toks = _lex(text)
    if not toks:
        raise _Refuse("empty row")
    cut = _tail_start(toks, ctx)
    alg, tail = toks[:cut], toks[cut:]
    while alg and alg[-1].kind == "op" and alg[-1].val in ",;.:":
        alg = alg[:-1]
    if not alg:
        raise _Refuse("no algebra")
    rels = _relations(alg)
    rd = _Reader(text, alg, ctx, widen=widen)
    rd.row_id = row_id
    widened = False

    def side(lo: int, hi: int) -> list[_Mono]:
        sub = rd.child(alg[lo:hi])
        if lo == hi:
            raise _Refuse("empty side")
        monos = sub.expr()
        if sub.i != len(sub.toks):
            raise _Refuse(f"unread token {sub.toks[sub.i].val!r}")
        nonlocal widened
        widened = widened or sub.widened
        return monos

    if objective:
        if tail:
            raise _Refuse("objective with a tail")
        if rels:
            # "Z = expr" / "f(x) = expr" / "f = f_1 = expr": a leading segment
            # that is one bare symbol is a label and states no algebra; the
            # objective is the first segment that is an expression.
            if any(c != "eq" for _, c, _s in rels):
                raise _Refuse("relation in an objective")
            cuts = [-1, *[pos for pos, _c, _s in rels], len(alg)]
            segs = [(cuts[k] + 1, cuts[k + 1]) for k in range(len(cuts) - 1)]
            chosen = segs[-1]
            for lo, hi in segs[:-1]:
                if not _is_label(alg[lo:hi]):
                    chosen = (lo, hi)
                    break
            monos = side(*chosen)
        else:
            monos = side(0, len(alg))
        if widened and not widen:
            raise _Refuse("needs widening")
        monos, scoped = _objective_scope(monos, ctx)
        if scoped:
            widened = True
            if not widen:
                raise _Refuse("needs widening")
        (monos,) = _index_values([monos], [], rd)
        for m in monos:
            for sym in (*m.syms, *m.dens):
                if not sym.subs and sym.name in rd.shadowed:
                    raise _Refuse(f"bound letter {sym.name!r} used as a value")
        monos, extras = _epigraph(monos, sense, row_id, rd)
        return _emit_side(monos, ctx), widened, extras

    if not rels:
        raise _Refuse("no relation")
    if any(strict for _, _c, strict in rels):
        widened = True
    bounds = [0]
    for pos, _c, _s in rels:
        bounds.extend((pos, pos + 1))
    bounds.append(len(alg))
    sides = [side(bounds[k], bounds[k + 1]) for k in range(0, len(bounds), 2)]
    cmps = [c for _, c, _s in rels]
    sides, cmps, quantified = _piecewise_bound(sides, cmps)

    pairs: list[tuple[str, str]] = []
    restrictions: list[str] = []
    if tail:
        tail_src = text[tail[0].start : tail[-1].end]
        pairs, restrictions, tail_widened = _clauses(tail_src, rd, tail=True)
        widened = widened or tail_widened
    for q_letter, q_fam in quantified:  # the binder of an extremum quantifies its inequality
        if q_letter in {p[0] for p in pairs}:
            raise _Refuse("an extremum rebinds a quantified letter")
        pairs.append((q_letter, q_fam))
    if widened and not widen:
        raise _Refuse("needs widening")
    # every restriction must name two quantified letters
    bound_letters = {p[0] for p in pairs}
    kept: list[str] = []
    for r in restrictions:
        if r.startswith("WHERE "):
            _w, letter, clause = r.split(" ", 2)
            fam = dict(pairs).get(letter)
            pname = re.match(r"\\mathit\{([^{}]*)\}|([A-Za-z_]\w*?)_\{", clause)
            name = (pname.group(1) or pname.group(2)) if pname else ""
            if fam is not None and ctx.shape(name.replace("\\_", "_")) == (fam,):
                kept.append(clause)
                continue
        else:
            a, _op, b = r.split(" ")
            if a in bound_letters and b in bound_letters:
                kept.append(r)
                continue
        widened = True  # a condition on a letter this row does not quantify
        if not widen:
            raise _Refuse("needs widening")
    restrictions = kept

    sides = _index_values(sides, pairs, rd)
    for monos in sides:
        for m in monos:
            for sym in (*m.syms, *m.dens):
                if not sym.subs and sym.name in rd.shadowed:
                    raise _Refuse(f"bound letter {sym.name!r} used as a value")
    if widened:
        _merge_guard(sides, ctx)
    # the letters in scope of every term: the tail's, or (no tail) the free
    # letters the implicit quantifier will bind over their one usage family
    scope = dict(pairs)
    if not tail and not quantified:
        for monos in sides:
            for m in monos:
                bound_here = {letter for letter, _fam in m.sums}
                for sym in (*m.syms, *m.dens):
                    for piece in sym.subs:
                        lm = re.match(_IDX_ATOM, piece)
                        fams = rd.usage.get(lm.group()) if lm else None
                        if lm and lm.group() not in bound_here and fams and len(fams) == 1:
                            scope[lm.group()] = next(iter(fams))
    out = _emit_side(sides[0], ctx, scope)
    for k, cmp in enumerate(cmps):
        out += f" {_REL_OUT[cmp]} " + _emit_side(sides[k + 1], ctx, scope)
    if pairs or restrictions:
        clauses = [r"\forall " + letter + r" \in " + _set_text(fam) for letter, fam in pairs]
        out += r" \qquad " + r",\; ".join(clauses + restrictions)
    return out, widened, []
