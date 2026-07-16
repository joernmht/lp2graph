"""Faulty-input detectors and format sniffing for LLM-generated artifacts.

LLM output rarely arrives as a clean model file: it comes fenced in
markdown, prefixed with prose, sprinkled with unicode look-alikes
(U+2212 minus, U+2264 <=), or truncated mid-expression by an output
limit. Each helper here repairs what is safely repairable, records what
it did as a :class:`~lp2graph.validation.report.Check`, and flags what
it cannot repair — nothing is fixed silently and nothing raises.

All detectors are deterministic: fixed regex tables, fixed replacement
maps, fixed tie-breaking order in the sniffer.
"""

from __future__ import annotations

import re

from lp2graph.validation.report import Check

#: Formats the pipeline can route to a parser. ``python`` is included so
#: solver-API source is *recognized* and reported with actionable guidance
#: (the deterministic core does not execute code).
FORMATS = ("json", "latex", "lp", "mps", "gams", "ampl", "jump", "python")

#: Aliases accepted for the ``fmt=`` argument (file-extension spellings).
FMT_ALIASES = {
    "tex": "latex",
    "gms": "gams",
    "mod": "ampl",
    "jl": "jump",
    "py": "python",
}

#: File extension -> format key (superset of mining.ingest's table: adds .json).
EXT_FMT = {
    ".json": "json",
    ".tex": "latex",
    ".lp": "lp",
    ".mps": "mps",
    ".gms": "gams",
    ".mod": "ampl",
    ".jl": "jump",
    ".py": "python",
}

#: Fence language tag -> format key (a tag is strong evidence).
_TAG_FMT = {
    "json": "json",
    "latex": "latex",
    "tex": "latex",
    "lp": "lp",
    "mps": "mps",
    "gams": "gams",
    "ampl": "ampl",
    "julia": "jump",
    "jump": "jump",
    "python": "python",
    "py": "python",
}

_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)\r?\n?```", re.DOTALL)

#: Unicode look-alikes -> ASCII, applied to non-LaTeX inputs. LaTeX gets
#: only the sign/space subset (TeX source may legitimately carry unicode).
_UNICODE_MAP = {
    "\u2212": "-",  # minus sign
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u00d7": "*",  # multiplication sign
    "\u00b7": "*",  # middle dot
    "\u2264": "<=",  # less-than-or-equal
    "\u2265": ">=",  # greater-than-or-equal
    "\u00a0": " ",  # no-break space
    "\u201c": '"',  # left double quote
    "\u201d": '"',  # right double quote
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u2026": "...",  # ellipsis
}
_UNICODE_MAP_LATEX = {"\u2212": "-", "\u00a0": " "}

#: Characters a complete model file plausibly ends on. Ending on one of
#: these operators/openers suggests the generator hit an output limit.
_DANGLING_TAIL = ("\\", "+", "-", "*", "/", "=", ",", "(", "&", "_", "^", "{", "[")


def decode_bytes(data: bytes, *, checks: list[Check]) -> str:
    """bytes -> text with recorded fallbacks (UTF-8, BOM, latin-1, NULs)."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
        checks.append(
            Check(
                stage="decode",
                level="warn",
                code="not-utf8",
                message="input is not valid UTF-8; decoded as latin-1 (bytes may be garbled).",
            )
        )
    if text.startswith("﻿"):
        text = text.lstrip("﻿")
        checks.append(
            Check(stage="decode", level="warn", code="bom-stripped", message="UTF-8 BOM removed.")
        )
    return strip_nul(text, checks=checks)


def strip_nul(text: str, *, checks: list[Check]) -> str:
    """Remove NUL bytes (a classic sign of binary contamination)."""
    if "\x00" in text:
        n = text.count("\x00")
        text = text.replace("\x00", "")
        checks.append(
            Check(
                stage="decode",
                level="warn",
                code="nul-bytes",
                message=f"removed {n} NUL byte(s) from the input.",
            )
        )
    return text


def extract_fenced(text: str, *, checks: list[Check]) -> tuple[str, str | None]:
    """Pull model source out of markdown code fences, if any.

    Returns ``(text, fmt_hint)``. When fences are present the fenced
    blocks replace the full text (surrounding prose is discarded, with a
    warning); the first recognized language tag becomes a format hint.
    An unterminated final fence is treated as truncation: its content is
    kept and flagged.
    """
    matches = list(_FENCE.finditer(text))
    hint: str | None = None
    if not matches:
        return text, None

    blocks = []
    for m in matches:
        tag = m.group(1).lower()
        if hint is None and tag in _TAG_FMT:
            hint = _TAG_FMT[tag]
        blocks.append(m.group(2))

    tail = text[matches[-1].end() :]
    open_tail = re.search(r"```[^\n]*\r?\n(.+)$", tail, re.DOTALL)
    if open_tail:
        blocks.append(open_tail.group(1))
        checks.append(
            Check(
                stage="detect",
                level="warn",
                code="unterminated-fence",
                message="final code fence is never closed; output looks truncated.",
            )
        )

    checks.append(
        Check(
            stage="detect",
            level="warn",
            code="markdown-fences",
            message=f"extracted {len(blocks)} fenced code block(s); surrounding prose discarded.",
            detail=f"language tag hint: {hint}" if hint else "",
        )
    )
    return "\n\n".join(blocks), hint


def normalize_unicode(text: str, fmt: str | None, *, checks: list[Check]) -> str:
    """Replace unicode math look-alikes with their ASCII spellings."""
    table = _UNICODE_MAP_LATEX if fmt == "latex" else _UNICODE_MAP
    replaced: list[str] = []
    for ch, repl in table.items():
        if ch in text:
            replaced.append(f"U+{ord(ch):04X}->{repl!r}")
            text = text.replace(ch, repl)
    if replaced:
        checks.append(
            Check(
                stage="detect",
                level="warn",
                code="unicode-normalized",
                message="replaced unicode math look-alikes with ASCII.",
                detail=", ".join(replaced),
            )
        )
    return text


def truncation_checks(text: str, fmt: str | None, *, checks: list[Check]) -> None:
    """Heuristic truncation/imbalance detectors (warn-level only)."""
    stripped = text.rstrip()
    if stripped.endswith(_DANGLING_TAIL):
        checks.append(
            Check(
                stage="detect",
                level="warn",
                code="dangling-tail",
                message=f"input ends on {stripped[-1]!r} (mid-expression); output truncated?",
            )
        )
    if fmt in ("latex", "json"):
        opens, closes = text.count("{"), text.count("}")
        if opens != closes:
            checks.append(
                Check(
                    stage="detect",
                    level="warn",
                    code="unbalanced-braces",
                    message=f"unbalanced braces: {opens} '{{' vs {closes} '}}'.",
                )
            )
    if fmt == "latex":
        begins = re.findall(r"\\begin\{([A-Za-z*]+)\}", text)
        ends = re.findall(r"\\end\{([A-Za-z*]+)\}", text)
        if sorted(begins) != sorted(ends):
            checks.append(
                Check(
                    stage="detect",
                    level="warn",
                    code="unbalanced-environments",
                    message="\\begin/\\end environments do not match.",
                    detail=f"begins={sorted(begins)} ends={sorted(ends)}",
                )
            )
    if fmt == "mps" and not re.search(r"^\s*ENDATA\b", text, re.MULTILINE):
        checks.append(
            Check(
                stage="detect",
                level="warn",
                code="mps-no-endata",
                message="MPS input has no ENDATA record; file may be truncated.",
            )
        )


def sniff_format(text: str) -> list[tuple[str, int]]:
    """Score each candidate format on content indicators.

    Returns ``(format, score)`` pairs with score > 0, best first; ties
    break on the fixed order of :data:`FORMATS` (deterministic).
    """
    scores = dict.fromkeys(FORMATS, 0)
    body = text.lstrip()

    if body.startswith("{"):
        scores["json"] += 4

    for pat, pts in (
        (r"^\s*ROWS\s*$", 3),
        (r"^\s*COLUMNS\s*$", 3),
        (r"^\s*RHS\s*$", 1),
        (r"^\s*ENDATA\b", 2),
        (r"^\s*NAME\b", 1),
    ):
        if re.search(pat, text, re.MULTILINE):
            scores["mps"] += pts

    for pat, pts in (
        (r"^\s*(Minimize|Maximize|MINIMIZE|MAXIMIZE)\s*$", 3),
        (r"^\s*(Subject\s+To|SUBJECT\s+TO|st|s\.t\.)\s*$", 3),
        (r"^\s*Bounds\s*$", 1),
        (r"^\s*(End|Generals|Binaries|Binary)\s*$", 1),
    ):
        if re.search(pat, text, re.MULTILINE):
            scores["lp"] += pts

    for pat, pts in (
        (r"\bsolve\s+\w+\s+using\b", 4),
        (r"^\s*Equations?\b", 2),
        (r"^\s*(Positive\s+|Binary\s+|Integer\s+)?Variables?\b", 1),
        (r"\.\.", 1),
    ):
        if re.search(pat, text, re.MULTILINE | re.IGNORECASE):
            scores["gams"] += pts

    for pat, pts in (
        (r"^\s*var\s+\w+", 3),
        (r"^\s*(minimize|maximize)\s+\w+\s*:", 3),
        (r"^\s*(subject\s+to|s\.t\.)\s+\w+\s*:", 2),
        (r"^\s*param\s+\w+", 1),
    ):
        if re.search(pat, text, re.MULTILINE):
            scores["ampl"] += pts

    for pat, pts in (
        (r"@variable\s*\(", 3),
        (r"@(constraint|objective)\s*\(", 2),
        (r"\busing\s+JuMP\b", 3),
        (r"\bModel\s*\(", 1),
    ):
        if re.search(pat, text):
            scores["jump"] += pts

    for pat, pts in (
        (r"^\s*(import|from)\s+(pulp|gurobipy|pyomo)\b", 4),
        (r"\b(LpProblem|ConcreteModel|gp\.Model|addVar|addConstr)\b", 2),
        (r"^\s*(def|import|from)\s+\w+", 1),
    ):
        if re.search(pat, text, re.MULTILINE):
            scores["python"] += pts

    if re.search(r"\\begin\{", text):
        scores["latex"] += 2
    if re.search(r"\\(min|max|sum|le|ge|leq|geq|forall|text)\b", text):
        scores["latex"] += 2
    if text.count("\\") >= 3:
        scores["latex"] += 1

    order = {name: i for i, name in enumerate(FORMATS)}
    ranked = [(name, s) for name, s in scores.items() if s > 0]
    ranked.sort(key=lambda item: (-item[1], order[item[0]]))
    return ranked


def resolve_fmt(fmt: str | None) -> str | None:
    """Normalize a user-supplied format name through the alias table."""
    if fmt is None:
        return None
    key = fmt.lower().lstrip(".")
    return FMT_ALIASES.get(key, key)


__all__ = [
    "EXT_FMT",
    "FMT_ALIASES",
    "FORMATS",
    "decode_bytes",
    "extract_fenced",
    "normalize_unicode",
    "resolve_fmt",
    "sniff_format",
    "strip_nul",
    "truncation_checks",
]
