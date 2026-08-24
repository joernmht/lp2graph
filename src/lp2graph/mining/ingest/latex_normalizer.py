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


#: Unicode Greek codepoint -> canonical spelled-out name (final sigma folds
#: into sigma: the positional variant is typography, not identity).
_GREEK_UNICODE: dict[str, str] = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",  # noqa: RUF001
    "ζ": "zeta", "η": "eta", "θ": "theta", "ι": "iota", "κ": "kappa",  # noqa: RUF001
    "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "ο": "omicron",  # noqa: RUF001
    "π": "pi", "ρ": "rho", "ς": "sigma", "σ": "sigma", "τ": "tau",  # noqa: RUF001
    "υ": "upsilon", "φ": "phi", "χ": "chi", "ψ": "psi", "ω": "omega",  # noqa: RUF001
    "Γ": "Gamma", "Δ": "Delta", "Θ": "Theta", "Λ": "Lambda", "Ξ": "Xi",
    "Π": "Pi", "Σ": "Sigma", "Υ": "Upsilon", "Φ": "Phi", "Ψ": "Psi",  # noqa: RUF001
    "Ω": "Omega", "ℓ": "ell",  # noqa: RUF001
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
    _rule("u00d7_cdot", "×", r"\cdot", "U+00D7 times to \\cdot"),  # noqa: RUF001
    _rule("u22c5_cdot", "⋅", r"\cdot", "U+22C5 dot operator to \\cdot"),
    _rule("u2212_minus", "−", "-", "U+2212 minus sign to '-'"),  # noqa: RUF001
    _rule("u2211_sum", "∑", r"\sum", "U+2211 n-ary sum to \\sum"),
    # --- ascii comparison shorthands (before bare '<'/'>') ----------------
    _rule("ascii_le", r"<=", r"\le", "ascii <= to \\le"),
    _rule("ascii_ge", r">=", r"\ge", "ascii >= to \\ge"),
    _rule("ascii_ne", r"!=", r"\neq", "ascii != to \\neq"),
    _rule("ascii_eqeq", r"==", "=", "ascii == to ="),
    # --- multiplication: '*' between operands becomes \cdot ---------------
    _rule("star_cdot", r"\s*\*\s*", r" \cdot ", "'*' multiplication to \\cdot"),
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
    _rule(
        "overset_base",
        r"\\overset\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        lambda m: "{" + m.group(1) + "}",
        "\\overset{a}{b} to {b} (keep the base symbol)",
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
