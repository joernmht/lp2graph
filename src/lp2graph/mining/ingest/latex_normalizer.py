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
header is never corrupted.
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


def _rule(
    rule_id: str, regex: str, repl: str | Callable[[re.Match[str]], str], note: str = ""
) -> RewriteRule:
    return RewriteRule(rule_id=rule_id, pattern=re.compile(regex), replacement=repl, note=note)


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
    _rule("star_cdot", r"\s*\*\s*", r" \cdot ", "'*' multiplication to \\cdot"),
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
        for m in rule.pattern.finditer(cur):
            new_chars.append(cur[pos : m.start()])
            new_offsets.extend(offset_map[pos : m.start()])

            before = m.group(0)
            after = rule.replacement(m) if callable(rule.replacement) else rule.replacement
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
    "RewriteRule",
    "ingest_latex",
    "normalize_latex",
]
