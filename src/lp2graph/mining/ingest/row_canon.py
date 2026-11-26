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
from dataclasses import dataclass, field
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

    def is_param(self, name: str) -> bool:
        return name in self.params or name in self.derived


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
        nxt = toks[j + 1] if coef and j + 1 < n else toks[j] if j < n else None
        out.append(
            SymbolUse(
                t.val,
                tuple(pieces),
                sup,
                coef,
                in_tail,
                nxt.val if nxt is not None and nxt.kind == "name" else None,
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
        if ch in "{([":
            depth += 1
        elif ch in "})]":
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
            return t.val in (r"\sum", r"\frac", r"\dfrac", r"\tfrac", r"\underset")
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
            inner = _Reader(self.text, self.toks[self.i + 1 : j], self.ctx, widen=self.widen)
            inner.usage = self.usage
            inner.shadowed = self.shadowed
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
        if t.kind == "cmd" and t.val == r"\sum":
            return self.bigsum(None)
        if t.kind == "cmd" and t.val == r"\underset":
            nxt = self.peek()
            if nxt is None or nxt.kind != "lb":
                raise _Refuse("underset without argument")
            binder = self.group_text()
            op = self.group_text()
            if op.strip() != r"\sum":
                raise _Refuse(f"underset over {op!r}")
            return self.bigsum(binder)
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

    def braced_expr(self) -> list[_Mono]:
        t = self.peek()
        if t is None or t.kind != "lb":
            raise _Refuse("fraction without braces")
        j = _group_end(self.toks, self.i)
        inner = _Reader(self.text, self.toks[self.i + 1 : j], self.ctx, widen=self.widen)
        inner.usage = self.usage
        inner.shadowed = self.shadowed
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
            out.append(_Mono(m.coef, m.syms, tuple(pairs) + m.sums, m.dens, (src, *m.origin)))
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
                args = _split_top(inner)
                if args and all(self.index_like(a, nested=False) for a in args):
                    subs.extend(" ".join(a.split()) for a in args)
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
            if m2 and ctx.is_symbol(m2.group(1)):
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
    r"^(?:[A-Za-z]\w*(?:_\{[A-Za-z0-9_, +-]*\})?|\d+|\\left\|\s*[A-Za-z]\w*\s*\\right\|)"
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
    return p


_TUPLE_PIECE_RE = re.compile(
    r"^(?:\\left\s*)?[(〈\[]\s*(.*?)\s*(?:\\right\s*)?[)〉\]]$|^\\left\\langle\s*(.*?)\s*\\right\\rangle$"
)
_CALL_PIECE_RE = re.compile(
    r"^([A-Za-z]\w*)\s*(?:\\left\s*)?\(\s*([A-Za-z0-9_, +-]*?)\s*(?:\\right\s*)?\)$"
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
            p = cm.group(1) + "_{" + ",".join(a.strip() for a in cm.group(2).split(",")) + "}"
        if "," in p and "{" not in p:
            out.extend(q.strip() for q in p.split(",") if q.strip())
        elif re.fullmatch(r"[A-Za-z]\w*(?:\s+[A-Za-z]\w*)+", p):
            out.extend(p.split())
        else:
            out.append(p)
    return out


def _scale(m: _Mono, k: Fraction) -> _Mono:
    return _Mono(m.coef * k, m.syms, m.sums, m.dens, m.origin)


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
            out.append(
                _Mono(
                    x.coef * y.coef,
                    x.syms + y.syms,
                    x.sums + y.sums,
                    x.dens + y.dens,
                    x.origin + y.origin,
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
        out.append(_Mono(x.coef / d.coef, x.syms, x.sums, x.dens + d.syms, x.origin))
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
            if any(ctx.is_symbol(n) for n in names):
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
        if cl[0].kind == "name" and rels and rels[0] == 1 and not ctx.is_symbol(cl[0].val):
            if any(t.kind == "name" and t.val in ctx.variables for t in cl[2:]):
                raise _Refuse("condition mentions a variable")
            bind(cl[0].val, None, exact=False)
            widened = True
            range_open = True
            continue
        # "1 \le i \le n": a range around a letter
        if len(rels) == 2:
            mid = cl[rels[0] + 1 : rels[1]]
            if len(mid) == 1 and mid[0].kind == "name" and not ctx.is_symbol(mid[0].val):
                if any(t.kind == "name" and t.val in ctx.variables for t in cl):
                    raise _Refuse("condition mentions a variable")
                bind(mid[0].val, None, exact=False)
                widened = True
                continue
        # dots or numbers continuing a range: "2, \ldots, n"
        if all(_is_dots(t) or t.kind in ("num",) for t in cl):
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
    """The ``%@ param`` line a derived parameter needs."""
    kind = "scalar" if not shape else "vector" if len(shape) == 1 else "matrix"
    shape_s = ",".join(shape) if shape else "-"
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


def _emit_mono(m: _Mono, ctx: RowContext) -> tuple[int, str]:
    variables = [s for s in m.syms if s.name in ctx.variables]
    params = [s for s in m.syms if s.name not in ctx.variables]
    if len(variables) > 1:
        raise _Refuse("product of variables")
    if any(s.name in ctx.variables for s in m.dens):
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
        elif len(params) == 1 and not dens and mag == 1:
            body = f"{_sym_text(params[0])} \\cdot {_sym_text(var)}"
        else:
            body = _sym_text(_derive(mag, params, dens, ctx)) + r" \cdot " + _sym_text(var)
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


def _emit_side(monos: list[_Mono], ctx: RowContext) -> str:
    monos = [m for m in monos if m.coef != 0]
    if not monos:
        return "0"
    parts: list[str] = []
    for k, m in enumerate(monos):
        sign, body = _emit_mono(m, ctx)
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
                _Mono(
                    m.coef,
                    tuple(fix(s) for s in m.syms),
                    m.sums,
                    tuple(fix(s) for s in m.dens),
                    m.origin,
                )
            )
        out.append(new)
    return out


def _merge_guard(sides: list[list[_Mono]], ctx: RowContext) -> None:
    """Widening must not merge terms the source keeps apart.

    A balance row sums the same variable over two different restricted sets
    (in-arcs minus out-arcs). Widened to the base family both sums become the
    same term and the row a tautology: such a row is refused, not promoted.
    """
    seen: dict[str, tuple[str, ...]] = {}
    for monos in sides:
        for m in monos:
            if m.coef == 0 or not m.sums:
                continue
            _sign, body = _emit_mono(_Mono(abs(m.coef), m.syms, m.sums, m.dens), ctx)
            first = seen.setdefault(body, m.origin)
            if first != m.origin:
                raise _Refuse("widening would merge sums over different sets")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_TRAILING_RE = re.compile(r"(?:[\s.,;:]|\\quad|\\qquad|\\;|\\,)+$")


def canonicalize_row(
    body: str, ctx: RowContext, *, objective: bool, widen: bool
) -> tuple[str, bool] | None:
    """Canonical spelling of one row body (the text between ``&`` and
    ``\\tag``), or ``None`` when the row is left to the parser.

    Returns ``(text, widened)``. With ``widen=False`` only exact rewrites are
    produced; a row that needs a widened binder or a dropped tail condition
    returns ``None`` and is retried by the widening rule.
    """
    snapshot = dict(ctx.derived)
    try:
        return _canonicalize(body, ctx, objective=objective, widen=widen)
    except _Refuse:
        ctx.derived.clear()
        ctx.derived.update(snapshot)
        return None
    except (RecursionError, ZeroDivisionError, ValueError, IndexError):
        ctx.derived.clear()
        ctx.derived.update(snapshot)
        return None


def _canonicalize(body: str, ctx: RowContext, *, objective: bool, widen: bool) -> tuple[str, bool]:
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
    widened = False

    def side(lo: int, hi: int) -> list[_Mono]:
        sub = _Reader(text, alg[lo:hi], ctx, widen=widen)
        sub.usage = rd.usage
        sub.shadowed = rd.shadowed
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
        (monos,) = _index_values([monos], [], rd)
        for m in monos:
            for sym in (*m.syms, *m.dens):
                if not sym.subs and sym.name in rd.shadowed:
                    raise _Refuse(f"bound letter {sym.name!r} used as a value")
        return _emit_side(monos, ctx), widened

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

    pairs: list[tuple[str, str]] = []
    restrictions: list[str] = []
    if tail:
        tail_src = text[tail[0].start : tail[-1].end]
        pairs, restrictions, tail_widened = _clauses(tail_src, rd, tail=True)
        widened = widened or tail_widened
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
    out = _emit_side(sides[0], ctx)
    for k, cmp in enumerate(cmps):
        out += f" {_REL_OUT[cmp]} " + _emit_side(sides[k + 1], ctx)
    if pairs or restrictions:
        clauses = [r"\forall " + letter + r" \in " + _set_text(fam) for letter, fam in pairs]
        out += r" \qquad " + r",\; ".join(clauses + restrictions)
    return out, widened
