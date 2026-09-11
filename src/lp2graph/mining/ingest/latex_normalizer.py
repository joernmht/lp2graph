r"""Non-canonical LaTeX normalizer (M1b).

Authors do not write the *canonical* LaTeX grammar that
:func:`lp2graph.codec.from_canonical_latex` parses. They write unicode
operators (U+2264/U+2265 ``<=``/``>=``, U+2200 for-all, U+2208 element-of,
U+00D7 times, U+2212 minus), ascii shorthands
(``<= >= !=``), use ``*`` for multiplication, wrap index sets in
``\mathbb`` or ``\mathrm`` rather than ``\mathcal``, and sprinkle
redundant whitespace. This module turns such author LaTeX into canonical
LaTeX by applying a **versioned, ordered rewrite-rule table**, recording
one :class:`~lp2graph.mining.provenance.Rewrite` per firing with a
:class:`~lp2graph.mining.provenance.SourceSpan` into the *original* text,
then parses and validates the result.

The exact target spellings are derived from
:mod:`lp2graph.codec.latex` -- the parser accepts ``\le``/``\ge``/``=``
comparators, ``\forall``/``\in``/``\mathcal{...}`` quantifiers and
binders, ``\cdot`` between a coefficient and a referent, and ``\sum_{...}``
aggregations. Rules only ever rewrite *toward* those spellings.

The ``%@`` annotation header carries the symbol table and is treated as
opaque: rewrites are confined to the algebraic ``align`` body so the
header is never corrupted. A few rules *read* the header (declared names
and shapes) and the body's binders to resolve scripts deterministically:
see :class:`DocContext` and the ``superscript_*`` / ``label_subscript``
rules (issue #63).
"""

# This module's whole job is mapping unicode Greek and look-alike codepoints
# to canonical ASCII names, so the "ambiguous character" lint fires on every
# table entry by design. A file-level directive keeps the tables free to be
# reformatted; the per-line `noqa: RUF001` comments this replaces were
# orphaned whenever `ruff format` exploded the dict literals, which left the
# CI format gate and the lint gate unable to pass at the same time.
# ruff: noqa: RUF001

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from lp2graph.codec import from_canonical_latex
from lp2graph.core.validate import ValidationError, validate
from lp2graph.mining.ingest.result import IngestionResult
from lp2graph.mining.provenance import ProvenanceMap, Rewrite, SourceSpan
from lp2graph.mining.versions import REWRITE_RULES_VERSION

# ---------------------------------------------------------------------------
# Rewrite-rule table (ordered, versioned)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RewriteRule:
    """One named rewrite rule.

    ``pattern`` is a compiled regex; ``replacement`` is either a literal
    replacement string (``re.sub`` semantics) or a callable
    ``match -> str``. ``rule_id`` is stamped into every emitted
    :class:`Rewrite` together with :data:`REWRITE_RULES_VERSION`.
    """

    rule_id: str
    pattern: re.Pattern[str]
    replacement: str | Callable[[re.Match[str]], str]
    note: str = ""
    #: A replacement that also sees the document context (declared names,
    #: bound letters). When set, ``replacement`` is ignored. Returning the
    #: match unchanged means "this rule does not apply here" and records
    #: no rewrite.
    ctx_replacement: Callable[[re.Match[str], DocContext], str] | None = None


def _rule(
    rule_id: str, regex: str, repl: str | Callable[[re.Match[str]], str], note: str = ""
) -> RewriteRule:
    return RewriteRule(rule_id=rule_id, pattern=re.compile(regex), replacement=repl, note=note)


def _ctx_rule(
    rule_id: str,
    pattern: re.Pattern[str],
    repl: Callable[[re.Match[str], DocContext], str],
    note: str = "",
) -> RewriteRule:
    return RewriteRule(
        rule_id=rule_id, pattern=pattern, replacement="", note=note, ctx_replacement=repl
    )


# Index-set wrapper normalization: the parser only resolves binder/quantifier
# sets spelled ``\mathcal{...}``. Authors often write ``\mathbb`` or
# ``\mathrm``. Rewrite the wrapper macro, preserving the set name.
def _to_mathcal(m: re.Match[str]) -> str:
    return r"\mathcal{" + m.group(1) + "}"


def _pad(m: re.Match[str], repl: str) -> str:
    """Space-guard a plain-identifier replacement so it never glues onto an
    adjacent letter or digit (``x\\bar{t}`` must not become ``xt_bar``)."""
    s = m.string
    left = " " if m.start() > 0 and s[m.start() - 1].isalnum() else ""
    right = " " if m.end() < len(s) and s[m.end()].isalnum() else ""
    return left + repl + right


def _plain_name(s: str) -> str:
    """The plain ``\\w+`` spelling of an identifier: ``\\mathit`` unwrapped,
    escaped underscores restored, MathML letter-spacing collapsed."""
    s = s.strip()
    mm = re.fullmatch(r"\\mathit\{([^{}]*)\}", s)
    if mm:
        s = mm.group(1)
    return s.replace("\\_", "_").replace(" ", "")


#: Accent spellings seen as the FIRST ``\overset``/``\underset`` argument in
#: Tier-2 MathML-derived corpus formulas (combining characters included) →
#: the standard accent command the pair collapses to. Only mapped arguments
#: rewrite; ``\overset{def}{=}``-style annotations fall through to
#: ``overset_base`` unchanged.
_OVERSET_ACCENTS: dict[str, str] = {
    "~": "tilde",
    "\\sim": "tilde",
    "\\tilde": "tilde",
    "\u0303": "tilde",
    "^": "hat",
    "\\wedge": "hat",
    "\\hat": "hat",
    "\u0302": "hat",
    "-": "bar",
    "\\bar": "bar",
    "\\overline": "bar",
    "\u0304": "bar",
    "¯": "bar",
    "⃗": "vec",
    "→": "vec",
    "\\rightarrow": "vec",
    "\\vec": "vec",
}

_UNDERSET_ACCENTS: dict[str, str] = {
    "\\underline": "underline",
    "_": "underline",
    "-": "underline",
    "\u0332": "underline",
}


def _accent_alts(table: dict[str, str]) -> str:
    return "|".join(re.escape(k) for k in sorted(table, key=len, reverse=True))


def _overset_accent_repl(m: re.Match[str]) -> str:
    return "\\" + _OVERSET_ACCENTS[m.group(1).strip()] + "{" + m.group(2) + "}"


def _underset_accent_repl(m: re.Match[str]) -> str:
    return "\\" + _UNDERSET_ACCENTS[m.group(1).strip()] + "{" + m.group(2) + "}"


def _accent_ident_repl(m: re.Match[str]) -> str:
    inner = m.group(2) if m.group(2) is not None else m.group(3)
    return _pad(m, _plain_name(inner) + "_" + m.group(1))


def _prime_ident_repl(m: re.Match[str]) -> str:
    deco = m.group(2)
    n = deco.count("'") + deco.count("′") + deco.count("\\prime")
    return _pad(m, _plain_name(m.group(1)) + "p" * n)


_SUM_GROUP = re.compile(r"\\sum_\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\s*")


def _sum_merge_repl(m: re.Match[str]) -> str:
    binders = [g.strip() for g in _SUM_GROUP.findall(m.group(0))]
    return r"\sum_{" + ", ".join(binders) + "} "


#: An accent's operand: a ``\mathit`` name or a (possibly MathML-spaced)
#: letter run — never a compound expression, which stays untouched.
_ACCENT_INNER = r"(?:\\mathit\{[^{}]*\}|[A-Za-z](?:\s?[A-Za-z0-9])*)"


#: Unicode Greek codepoint -> canonical spelled-out name (final sigma folds
#: into sigma: the positional variant is typography, not identity).
_GREEK_UNICODE: dict[str, str] = {
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "epsilon",
    "ζ": "zeta",
    "η": "eta",
    "θ": "theta",
    "ι": "iota",
    "κ": "kappa",
    "λ": "lambda",
    "μ": "mu",
    "ν": "nu",
    "ξ": "xi",
    "ο": "omicron",
    "π": "pi",
    "ρ": "rho",
    "ς": "sigma",
    "σ": "sigma",
    "τ": "tau",
    "υ": "upsilon",
    "φ": "phi",
    "χ": "chi",
    "ψ": "psi",
    "ω": "omega",
    "Γ": "Gamma",
    "Δ": "Delta",
    "Θ": "Theta",
    "Λ": "Lambda",
    "Ξ": "Xi",
    "Π": "Pi",
    "Σ": "Sigma",
    "Υ": "Upsilon",
    "Φ": "Phi",
    "Ψ": "Psi",
    "Ω": "Omega",
    "ℓ": "ell",
}


# ---------------------------------------------------------------------------
# Declaration-driven script resolution (issue #63)
# ---------------------------------------------------------------------------
#
# The canonical grammar has no superscripts, and every subscript position is
# an index. Authors use scripts for two unrelated things: INDICES
# (``x_{i}^{k}`` with ``k`` bound by a binder or quantifier) and LABELS
# (``t_{i}^{arr}``, ``v_{i}^{c}``, ``h_{min}``, ``Z_{1}``). Which one a
# script is, is decidable from the document itself: the ``%@`` header says
# which names exist and which carry a shape, and the ``align`` body says
# which letters are bound. So these rules resolve scripts deterministically
# and bijectively: an index script moves into the subscript, a label script
# folds into a plain ``\w+`` name (the same convention as ``accent_ident``:
# ``t_arr``, ``v_c``, ``tau_de``, ``h_min``), and anything else is left
# untouched for the parser to refuse by name. The declaration sidecar has
# to declare the folded spellings; that is the lab's vocabulary step.


@dataclass(frozen=True, slots=True)
class DocContext:
    r"""What a document declares and binds, read once per context rule.

    ``declared`` holds every ``%@ index``/``param``/``var`` name,
    ``shaped`` the param/var names declared with a non-empty shape, and
    ``bound`` every letter the body binds through ``\in`` binders and
    quantifiers, tuple binders ``(i, j) \in``, ``\forall i, j`` lists and
    big-operator ranges ``\sum_{i = 1}^{n}``.
    """

    declared: frozenset[str]
    shaped: frozenset[str]
    bound: frozenset[str]
    #: ``%@ param`` names and ``%@ var`` names (for the product rule).
    params: frozenset[str] = frozenset()
    variables: frozenset[str] = frozenset()
    #: Whether the document carries any ``%@`` declaration at all. Without
    #: one there is nothing to resolve scripts against, so every context
    #: rule leaves a bare snippet untouched (the repo converter normalizes
    #: header-less rows and applies its own symbol table afterwards).
    has_header: bool = False

    @classmethod
    def build(cls, text: str, body: str) -> DocContext:
        declared: set[str] = set()
        shaped: set[str] = set()
        params: set[str] = set()
        variables: set[str] = set()
        for line in text.splitlines():
            dm = _DECL_RE.match(line)
            if dm is None:
                continue
            kind, name, rest = dm.groups()
            declared.add(name)
            if kind == "param":
                params.add(name)
            elif kind == "var":
                variables.add(name)
            if kind != "index":
                sm = re.search(r"\bshape=(\S+)", rest)
                if sm is not None and sm.group(1) != "-":
                    shaped.add(name)
        bound: set[str] = set()
        for bm in _BOUND_IN_RE.finditer(body):
            bound.update(_plain_name(t) for t in _split_top_commas(bm.group(1)))
        for bm in _BOUND_TUPLE_RE.finditer(body):
            inner = bm.group(1) if bm.group(1) is not None else bm.group(2)
            for t in _split_top_commas(inner):
                if re.fullmatch(_TOK, t.strip()):
                    bound.add(_plain_name(t))
        for bm in _BOUND_FORALL_RE.finditer(body):
            bound.update(_plain_name(t) for t in _split_top_commas(bm.group(1)))
        for bm in _BIGOP_SUB_RE.finditer(body):
            for rm in _RANGE_BINDER_RE.finditer(bm.group(1)):
                bound.add(_plain_name(rm.group(1)))
        return cls(
            declared=frozenset(declared),
            shaped=frozenset(shaped),
            bound=frozenset(bound),
            params=frozenset(params),
            variables=frozenset(variables),
            has_header=bool(declared),
        )


_DECL_RE = re.compile(r"^\s*%@\s*(index|param|var)\s+([A-Za-z_]\w*)(.*)$")
_TOK = r"(?:\\mathit\{[^{}]*\}|[A-Za-z]\w*)"
_BOUND_IN_RE = re.compile(r"(" + _TOK + r"(?:\s*,\s*" + _TOK + r")*)\s*\\in(?![A-Za-z])")
_BOUND_TUPLE_RE = re.compile(
    r"\\left\(\s*([^()]*?)\s*\\right\)\s*\\in(?![A-Za-z])|\(\s*([^()]*?)\s*\)\s*\\in(?![A-Za-z])"
)
_BOUND_FORALL_RE = re.compile(r"\\forall\s*(" + _TOK + r"(?:\s*,\s*" + _TOK + r")*)")
_BIGOP_SUB_RE = re.compile(
    r"\\(?:sum|prod|max|min|bigcup|bigcap)_\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}"
)
_RANGE_BINDER_RE = re.compile(r"(" + _TOK + r")\s*=")
_SCRIPT_GRP = r"\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}"
_BASE = r"(?<![\\A-Za-z0-9_])(\\mathit\{[^{}]*\}|[A-Za-z]\w*)"
_BARE_SUB_RE = re.compile(
    r"(?<![\\A-Za-z0-9_])(\\mathit\{[^{}]*\}|[A-Za-z][A-Za-z0-9]*)_([A-Za-z0-9])(?![A-Za-z0-9_])"
)
_BARE_SUP_RE = re.compile(
    r"(?<![\\A-Za-z0-9_])(\\mathit\{[^{}]*\}|[A-Za-z]\w*(?:_\{[^{}]*\})?)\^([A-Za-z0-9*+-])"
    r"(?![A-Za-z0-9_{])"
)
_SUP_RULE_RE = re.compile(
    _BASE + r"(?:_" + _SCRIPT_GRP + r")?\^" + _SCRIPT_GRP + r"(?:_" + _SCRIPT_GRP + r")?"
)
_SUB_RULE_RE = re.compile(_BASE + r"_" + _SCRIPT_GRP + r"(?!\s*\^)")
_WRAP_RE = re.compile(
    r"\\(?:text|textrm|mathit|mathrm|mathtt|mathsf|mathbf|operatorname)\s*\{([^{}]*)\}"
)
_OFFSET_RE = re.compile(r"(" + _TOK + r")\s*([+-])\s*(\d+)")


def _split_top_commas(s: str) -> list[str]:
    """Split on commas outside braces/parentheses (``a, b_{c,d}`` -> 2)."""
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in s:
        if ch in "{(":
            depth += 1
        elif ch in "})":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def _piece_word(piece: str) -> str | None:
    """The plain word a simple script piece spells, or ``None`` when the
    piece is not a simple token (nested scripts, delimiters, sums ...)."""
    q = piece.strip()
    wm = _WRAP_RE.fullmatch(q)
    if wm is not None:
        q = wm.group(1).strip()
    if q in ("*", r"\star", r"\ast"):
        return "star"
    if q in ("+", "-"):
        return "plus" if q == "+" else "minus"  # positive/negative parts: d^{+}, d^{-}
    if q in (r"\max", r"\min"):
        return q[1:]
    if re.fullmatch(r"[A-Za-z0-9](?:\s+[A-Za-z0-9])+", q):
        q = q.replace(" ", "")  # MathML letter spacing: d e p -> dep
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*|[0-9]+", q):
        return q
    return None


def _index_pieces(piece: str, ctx: DocContext) -> list[str] | None:
    """The index expressions a script piece denotes, or ``None`` if the
    piece is not made of bound letters (a label, or something else)."""
    q = piece.strip()
    w = _piece_word(q)
    if w is not None and w in ctx.bound:
        return [w]
    om = _OFFSET_RE.fullmatch(q)
    if om is not None and _plain_name(om.group(1)) in ctx.bound:
        return [f"{_plain_name(om.group(1))} {om.group(2)} {om.group(3)}"]
    if re.fullmatch(r"[A-Za-z](?:\s+[A-Za-z])+", q):
        letters = q.split()
        if all(ch in ctx.bound for ch in letters):
            return letters
    if re.fullmatch(r"[A-Za-z]{2,}", q) and all(ch in ctx.bound for ch in q):
        # Glued single-letter indices (x_{ij} with i and j bound): the
        # dominant hand-written spelling. A word is a label only when at
        # least one of its letters is not bound (h_{min} with i bound).
        return list(q)
    return None


_SCRIPT_GROUP_RE = re.compile(r"([_^])\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
_TEXT_IDENT_RE = re.compile(r"\\(?:text|textrm|mathrm)\s*\{\s*([A-Za-z][A-Za-z0-9]*)\s*\}")
#: Two symbol tokens separated by whitespace only (no operator between them).
_PRODUCT_TOK = (
    r"(?:\\mathit\{[^{}]*\}|[A-Za-z][A-Za-z0-9]*(?:_(?!\{)[A-Za-z0-9]+)*)"
    r"(?:_\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})?"
)
_DECLARED_PRODUCT_RE = re.compile(
    r"(?<![\\A-Za-z0-9_])(" + _PRODUCT_TOK + r")([ \t]+)(" + _PRODUCT_TOK + r")(?![A-Za-z0-9_{])"
)


def _text_ident_script_repl(m: re.Match[str], ctx: DocContext) -> str:
    if not ctx.has_header:
        return m.group(0)
    inner = _TEXT_IDENT_RE.sub(lambda mm: mm.group(1), m.group(2))
    return m.group(1) + "{" + inner + "}"


def _declared_product_repl(m: re.Match[str], ctx: DocContext) -> str:
    if not ctx.has_header:
        return m.group(0)
    prefix = m.string[: m.start()]
    if prefix.count("{") != prefix.count("}"):
        return m.group(0)  # inside a script or set: never a product
    left, right = m.group(1), m.group(3)
    lname = _plain_name(re.split(r"_\{", left, maxsplit=1)[0])
    rname = _plain_name(re.split(r"_\{", right, maxsplit=1)[0])
    if lname in ctx.params and (rname in ctx.params or rname in ctx.variables):
        return f"{left} \\cdot {right}"
    if lname in ctx.variables and rname in ctx.params:
        return f"{right} \\cdot {left}"  # commutative: the coefficient goes first
    return m.group(0)


def _bare_sub_repl(m: re.Match[str], ctx: DocContext) -> str:
    if not ctx.has_header:
        return m.group(0)
    base, suffix = m.group(1), m.group(2)
    name = _plain_name(base)
    if f"{name}_{suffix}" in ctx.declared:
        return m.group(0)  # a declared plain name such as Z_1 or tc_hat
    if name in ctx.shaped or suffix in ctx.bound:
        return base + "_{" + suffix + "}"
    return m.group(0)


def _bare_sup_repl(m: re.Match[str], ctx: DocContext) -> str:
    if not ctx.has_header:
        return m.group(0)
    return m.group(1) + "^{" + m.group(2) + "}"


def _superscript_repl(m: re.Match[str], ctx: DocContext, *, want: str) -> str:
    if not ctx.has_header:
        return m.group(0)
    base, sub_a, sup, sub_b = m.group(1), m.group(2), m.group(3), m.group(4)
    if sub_a is not None and sub_b is not None:
        return m.group(0)  # two subscripts: not a plain scripted symbol
    sub = sub_a if sub_a is not None else sub_b
    pieces = _split_top_commas(sup)
    idx = [_index_pieces(q, ctx) for q in pieces]
    if all(ip is not None for ip in idx):
        if want != "index":
            return m.group(0)
        new_sub = [q.strip() for q in _split_top_commas(sub)] if sub and sub.strip() else []
        for ip in idx:
            new_sub.extend(ip or [])
        return _pad(m, base + "_{" + ", ".join(new_sub) + "}")
    labels = [_piece_word(q) for q in pieces]
    if all(lb is not None for lb in labels):
        if want != "label":
            return m.group(0)
        name = _plain_name(base) + "_" + "_".join(lb or "" for lb in labels)
        tail = "_{" + sub.strip() + "}" if sub and sub.strip() else ""
        return _pad(m, name + tail)
    return m.group(0)


def _superscript_index_repl(m: re.Match[str], ctx: DocContext) -> str:
    return _superscript_repl(m, ctx, want="index")


def _superscript_label_repl(m: re.Match[str], ctx: DocContext) -> str:
    return _superscript_repl(m, ctx, want="label")


def _label_subscript_repl(m: re.Match[str], ctx: DocContext) -> str:
    if not ctx.has_header:
        return m.group(0)
    base, sub = m.group(1), m.group(2)
    bname = _plain_name(base)
    keep: list[str] = []
    labels: list[str] = []
    expanded = False
    for q in _split_top_commas(sub):
        qs = q.strip()
        if not qs:
            return m.group(0)
        idx = _index_pieces(qs, ctx)
        if idx is not None:
            # Spaced or glued bound letters (i j, ij) become one index each.
            expanded = expanded or len(idx) > 1
            keep.extend(idx if len(idx) > 1 else [qs])
            continue
        w = _piece_word(qs)
        if w is None:
            return m.group(0)  # unresolvable piece: the parser refuses it by name
        if w.isdigit():
            if bname in ctx.shaped:
                keep.append(qs)  # fixed-element reference against a declared shape
            else:
                labels.append(w)
            continue
        if len(w) == 1:
            keep.append(qs)  # a lone letter is an index by convention
            continue
        labels.append(w)
    if not labels:
        if not expanded:
            return m.group(0)
        return base + "_{" + ", ".join(keep) + "}"
    name = bname + "_" + "_".join(labels)
    return _pad(m, name + ("_{" + ", ".join(keep) + "}" if keep else ""))


#: The ordered rule table. Order matters: unicode/ascii operators are mapped
#: to macros first, then ``*`` multiplication, then structural wrappers, then
#: whitespace is collapsed last so spans of earlier rules stay meaningful.
REWRITE_RULES: tuple[RewriteRule, ...] = (
    # --- unicode comparison / membership / quantifier operators -----------
    _rule("u2264_le", "≤", r"\le", "U+2264 <= to \\le"),
    _rule("u2265_ge", "≥", r"\ge", "U+2265 >= to \\ge"),
    _rule("u2260_neq", "≠", r"\neq", "U+2260 != to \\neq"),
    _rule("u2200_forall", "∀", r"\forall", "U+2200 for-all to \\forall"),
    _rule("u2208_in", "∈", r"\in", "U+2208 element-of to \\in"),
    _rule("u00d7_cdot", "×", r"\cdot", "U+00D7 times to \\cdot"),
    _rule("u22c5_cdot", "⋅", r"\cdot", "U+22C5 dot operator to \\cdot"),
    _rule("u2212_minus", "−", "-", "U+2212 minus sign to '-'"),
    _rule("u2211_sum", "∑", r"\sum", "U+2211 n-ary sum to \\sum"),
    # --- ascii comparison shorthands (before bare '<'/'>') ----------------
    _rule("ascii_le", r"<=", r"\le", "ascii <= to \\le"),
    _rule("ascii_ge", r">=", r"\ge", "ascii >= to \\ge"),
    _rule("ascii_ne", r"!=", r"\neq", "ascii != to \\neq"),
    _rule("ascii_eqeq", r"==", "=", "ascii == to ="),
    # --- multiplication: '*' between operands becomes \cdot ---------------
    # A '*' that is itself a script (x^*, q^{*}) is a label, not a product;
    # the script rules below fold it into the name (q_star).
    _rule(
        "star_cdot",
        r"\s*(?<![\^_]\{)(?<!\^)\*(?!\})\s*",
        r" \cdot ",
        "'*' multiplication to \\cdot",
    ),
    # \times the COMMAND (the unicode char is mapped above); corpus evidence:
    # weighted objectives write w_1 \times f_1.
    _rule("times_cdot", r"\\times(?![a-zA-Z])", r"\cdot", "\\times to \\cdot"),
    # --- index-set wrapper macros to \mathcal -----------------------------
    _rule(
        "mathbb_mathcal",
        r"\\mathbb\s*\{([A-Za-z][\w\\]*)\}",
        _to_mathcal,
        "\\mathbb index set to \\mathcal",
    ),
    _rule(
        "mathrm_set_mathcal",
        r"\\mathrm\s*\{([A-Z][A-Za-z]*)\}",
        _to_mathcal,
        "\\mathrm upper-case set to \\mathcal",
    ),
    # --- big-operator wrapper forms (corpus evidence: 3,668/8,957 Tier-2
    # MathML-derived formulas write aggregations via \underset/\mathop/
    # \overset instead of the canonical \sum_{...} spelling) ----------------
    _rule(
        "underset_bigop",
        r"\\underset\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\s*"
        r"\{\s*(\\sum|\\prod|\\min|\\max|\\int|\\bigcup|\\bigcap)\s*\}",
        lambda m: m.group(2) + "_{" + m.group(1) + "}",
        "\\underset{X}{\\sum} to \\sum_{X} (canonical aggregation spelling)",
    ),
    # An \underset whose SECOND argument is an accented base (the first is
    # the accent) is a decoration, not a big operator; collapse it to the
    # standard accent command so accent_ident (below) can rename it.
    _rule(
        "underset_accent",
        r"\\underset\s*\{\s*(" + _accent_alts(_UNDERSET_ACCENTS) + r")\s*\}\s*"
        r"\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        _underset_accent_repl,
        "\\underset{\\underline}{X} to \\underline{X}",
    ),
    _rule(
        "mathop_unwrap",
        r"\\mathop\s*\{\s*(\\[a-zA-Z]+|[a-zA-Z]+)\s*\}",
        lambda m: m.group(1),
        "\\mathop{\\sum} to \\sum",
    ),
    _rule(
        "underbrace_unwrap",
        r"\\underbrace\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        lambda m: "{" + m.group(1) + "}",
        "\\underbrace{X} to {X} (drop annotation brace)",
    ),
    # An \overset carrying an ACCENT (tilde/hat/bar/vec spellings incl.
    # combining characters) is a decorated identifier: collapse to the
    # standard accent command BEFORE overset_base can drop the accent and
    # silently merge \overset{~}{\beta} with a plain \beta.
    _rule(
        "overset_accent",
        r"\\overset\s*\{\s*(" + _accent_alts(_OVERSET_ACCENTS) + r")\s*\}\s*"
        r"\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        _overset_accent_repl,
        "\\overset{~}{X} to \\tilde{X} (accent argument)",
    ),
    _rule(
        "overset_base",
        r"\\overset\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        lambda m: "{" + m.group(1) + "}",
        "\\overset{a}{b} to {b} (keep the base symbol)",
    ),
    # Consecutive big operators do not parse; the canonical spelling is ONE
    # \sum with a comma-joined multi-binder (order preserved: the second
    # binder set may reference the first index, \sum_{j \in T, a \in A^{j}}).
    # Corpus evidence: 60 of 168 grammar-failing papers (2026-08 sprint).
    _rule(
        "sum_merge",
        r"(?:\\sum_\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}\s*){2,}",
        _sum_merge_repl,
        "consecutive \\sum operators merge into one multi-binder \\sum",
    ),
    # --- Greek identifiers (corpus evidence: Tier-2 formulas name symbols
    # \lambda, \pi, \tau, ...; the canonical identifier grammar is
    # [A-Za-z_]\w*, so a Greek command can never be a ref or binder index.
    # The canonical spelling of a multi-character name is \mathit{name}, so
    # the bijective rewrite \lambda -> \mathit{lambda} makes Greek-named
    # models expressible without touching their meaning) -------------------
    _rule(
        "greek_ident",
        r"\\(alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda"
        r"|mu|nu|xi|omicron|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega"
        r"|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Upsilon|Phi|Psi|Omega"
        r"|varepsilon|vartheta|varpi|varrho|varsigma|varphi|ell)(?![a-zA-Z])",
        lambda m: r"\mathit{" + m.group(1) + "}",
        "Greek/\\ell command identifier to \\mathit{name}",
    ),
    _rule(
        "greek_unicode_ident",
        "[αβγδεζηθικλμνξοπρςστυφχψωΓΔΘΛΞΠΣΥΦΨΩℓ]",
        lambda m: r"\mathit{" + _GREEK_UNICODE[m.group(0)] + "}",
        "unicode Greek identifier to \\mathit{name}",
    ),
    # --- decorated identifiers (corpus evidence: 130 of 168 grammar-failing
    # papers in the 2026-08 sprint decorate names with accents or primes;
    # decorations are outside the identifier grammar but bijectively
    # renameable. Targets are PLAIN \w+ names (tc_hat, kp) — the spelling
    # the lab's repair convention already uses — because a plain name is
    # valid in EVERY position (binder, quantifier index, subscript expr,
    # referent), where \mathit{...} is not. Runs AFTER the Greek rules so
    # \tilde{\beta} arrives here as \tilde{\mathit{beta}} -> beta_tilde) --
    _rule(
        "accent_ident",
        r"\\(widehat|widetilde|overline|underline|mathring|tilde|check|breve"
        r"|acute|grave|ddot|dot|bar|hat|vec)(?![a-zA-Z])"
        r"\s*(?:\{\s*(" + _ACCENT_INNER + r")\s*\}|\s+([A-Za-z])(?![a-zA-Z]))",
        _accent_ident_repl,
        "accented identifier to plain name_accent (\\hat{tc} -> tc_hat)",
    ),
    _rule(
        "prime_ident",
        r"(?<![A-Za-z0-9_\\])((?:\\mathit\{[^{}]*\})|[A-Za-z]\w*)"
        r"((?:['′])+|\^\{\s*(?:\\prime|['′])+\s*\}|\^\\prime(?![a-zA-Z]))",
        _prime_ident_repl,
        "primed identifier to plain p-suffixed name (t' -> tp, k^{'} -> kp)",
    ),
    # --- declaration-driven script resolution (issue #63; corpus evidence:
    # 49 + 21 of 220 grammar-failing papers in the 2026-09 re-run stall on
    # superscripts and label subscripts, and unbraced scripts B_u \cdot w_u
    # read as plain identifiers, issue #62). Order: brace bare scripts,
    # move index superscripts into the subscript, fold label superscripts
    # and label subscripts into plain names ----------------------------------
    _ctx_rule(
        "text_ident_script",
        _SCRIPT_GROUP_RE,
        _text_ident_script_repl,
        "\\text{l} / \\mathrm{l} inside a script is the identifier l",
    ),
    _ctx_rule(
        "bare_sub_brace",
        _BARE_SUB_RE,
        _bare_sub_repl,
        "unbraced subscript on a shaped or bound symbol to the braced form (B_u -> B_{u})",
    ),
    _ctx_rule(
        "bare_sup_brace",
        _BARE_SUP_RE,
        _bare_sup_repl,
        "unbraced single-character superscript to the braced form (x^k -> x^{k})",
    ),
    _ctx_rule(
        "superscript_index",
        _SUP_RULE_RE,
        _superscript_index_repl,
        "superscript made of bound letters moves into the subscript (x_{i}^{k} -> x_{i, k})",
    ),
    _ctx_rule(
        "superscript_label",
        _SUP_RULE_RE,
        _superscript_label_repl,
        "label superscript folds into a plain name (t_{i}^{arr} -> t_arr_{i})",
    ),
    _ctx_rule(
        "label_subscript",
        _SUB_RULE_RE,
        _label_subscript_repl,
        "label subscript folds into a plain name (h_{min} -> h_min, Z_{1} -> Z_1); "
        "glued bound letters split into indices (x_{ij} -> x_{i, j})",
    ),
    # A declared parameter written next to a declared symbol with no operator
    # between them is a product: the canonical spelling carries \cdot, and the
    # coefficient goes first (corpus evidence: ~84% of rows write products by
    # juxtaposition). Undeclared names are left alone for the parser to refuse.
    _ctx_rule(
        "declared_product",
        _DECLARED_PRODUCT_RE,
        _declared_product_repl,
        "juxtaposed declared symbols get \\cdot (c_{i} x_{i} -> c_{i} \\cdot x_{i})",
    ),
    # --- whitespace hygiene (last) ----------------------------------------
    _rule("collapse_ws", r"[ \t]{2,}", " ", "collapse runs of spaces/tabs"),
)


# ---------------------------------------------------------------------------
# Body isolation
# ---------------------------------------------------------------------------

_BODY_RE = re.compile(r"\\begin\{align\}.*?\\end\{align\}", re.DOTALL)


def _body_span(text: str) -> tuple[int, int]:
    """Return the half-open span of the ``align`` body, or whole text.

    Rewrites must not touch the ``%@`` header (the symbol table). When an
    ``align`` block is present we confine rewriting to it; otherwise we
    rewrite the whole text (a parse failure downstream is then reported).
    """
    m = _BODY_RE.search(text)
    if m is None:
        return 0, len(text)
    return m.start(), m.end()


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------


def normalize_latex(text: str, *, source: str) -> tuple[str, ProvenanceMap]:
    """Apply the rewrite-rule table in order, recording provenance.

    Returns the rewritten text and a :class:`ProvenanceMap` whose
    ``rewrites`` list has one :class:`Rewrite` per rule firing. Each
    rewrite's :class:`SourceSpan` indexes into the *original* ``text``.

    Determinism: rules are a frozen, ordered tuple and ``re`` scans
    left-to-right, so the same input yields the same output and the same
    rewrite list.
    """
    prov = ProvenanceMap(source=source)
    lo, hi = _body_span(text)
    head, body, tail = text[:lo], text[lo:hi], text[hi:]

    # ``offset`` maps a position in the *current* body back to the original
    # body so recorded spans always point into the untouched input.
    cur = body
    offset_map = list(range(len(body) + 1))

    for rule in REWRITE_RULES:
        new_chars: list[str] = []
        new_offsets: list[int] = []
        pos = 0
        # Context rules read the header and the CURRENT body (earlier rules
        # may have renamed a bound letter, t' -> tp), so build it per rule.
        ctx = DocContext.build(text, cur) if rule.ctx_replacement is not None else None
        for m in rule.pattern.finditer(cur):
            before = m.group(0)
            if rule.ctx_replacement is not None and ctx is not None:
                after = rule.ctx_replacement(m, ctx)
            elif callable(rule.replacement):
                after = rule.replacement(m)
            else:
                after = rule.replacement
            if after == before:
                continue  # the rule declined: no text change, no rewrite record
            new_chars.append(cur[pos : m.start()])
            new_offsets.extend(offset_map[pos : m.start()])

            orig_start = lo + offset_map[m.start()]
            orig_end = lo + offset_map[m.end()]
            prov = prov.with_rewrite(
                Rewrite(
                    rule=rule.rule_id,
                    before=before,
                    after=after,
                    span=SourceSpan(
                        source=source,
                        start=orig_start,
                        end=orig_end,
                        line=text.count("\n", 0, orig_start) + 1,
                    ),
                    rules_version=REWRITE_RULES_VERSION,
                )
            )
            new_chars.append(after)
            # The whole replacement is anchored at the match start in the
            # original; intra-replacement character spans are not tracked.
            new_offsets.extend([offset_map[m.start()]] * len(after))
            pos = m.end()
        new_chars.append(cur[pos:])
        new_offsets.extend(offset_map[pos:])
        cur = "".join(new_chars)
        new_offsets.append(offset_map[-1])
        offset_map = new_offsets[: len(cur) + 1]

    return head + cur + tail, prov


def ingest_latex(text: str, *, source: str) -> IngestionResult:
    """Normalize, parse, and validate non-canonical author LaTeX.

    Pipeline: :func:`normalize_latex` (stage ``"normalize"``) ->
    :func:`from_canonical_latex` (stage ``"parse"``) ->
    :func:`validate` (stage ``"validate"``). A failure at any stage is
    captured and returned as a reported :class:`IngestionResult`, never an
    uncaught exception.
    """
    try:
        normalized, prov = normalize_latex(text, source=source)
    except Exception as exc:
        return IngestionResult.single_failure(
            source=source,
            stage="normalize",
            message=f"rewrite-rule normalization failed: {exc}",
            detail=type(exc).__name__,
        )

    try:
        formulation = from_canonical_latex(normalized)
    except Exception as exc:
        return IngestionResult.single_failure(
            source=source,
            stage="parse",
            message=f"normalized LaTeX is not in the canonical grammar: {exc}",
            detail=type(exc).__name__,
        )

    try:
        validate(formulation)
    except ValidationError as exc:
        return IngestionResult.single_failure(
            source=source,
            stage="validate",
            message=f"parsed formulation failed semantic validation: {exc}",
            detail=" | ".join(exc.errors),
        )

    return IngestionResult.success(source=source, formulation=formulation, provenance=prov)


__all__ = [
    "REWRITE_RULES",
    "DocContext",
    "RewriteRule",
    "ingest_latex",
    "normalize_latex",
]
