"""The single source of truth for model-file format identity.

Every layer that has to answer "what format is this artifact?" reads its
table from here: the validation sniffer
(:mod:`lp2graph.validation.detect`), the mining ingestion dispatcher
(:mod:`lp2graph.mining.ingest.dispatch`), and the ``convert`` routing in
:mod:`lp2graph.cli`.

Before this module existed each of those layers carried its own private
extension table. They drifted: ``mining.ingest`` had no ``.json`` entry, so
the M1 front-end could not ingest lp2graph's *own* canonical format, while
``validation.detect`` documented itself as "a superset of mining.ingest's
table" — duplication the comments acknowledged but the code could not
enforce. Adding a format now means editing exactly one table.

The tables are plain module-level constants (not a mutable plug-in
registry) on purpose: format routing feeds determinism-critical paths, and
a table that third-party code can mutate at runtime would make ingestion
results depend on import order. Adding a format is a source edit here.
"""

from __future__ import annotations

#: Every format key the library can route to a parser.
#:
#: ``python`` is a member so solver-API source is *recognized* and reported
#: with actionable guidance — the deterministic core never executes code.
#: ``pdf`` is likewise recognized only to be refused: PDF math extraction is
#: out of scope for a deterministic pipeline.
FORMATS: tuple[str, ...] = (
    "json",
    "latex",
    "lp",
    "mps",
    "gams",
    "ampl",
    "jump",
    "python",
    "pdf",
)

#: File extension (lower-case, leading dot) -> format key.
EXT_FMT: dict[str, str] = {
    ".json": "json",
    ".tex": "latex",
    ".lp": "lp",
    ".mps": "mps",
    ".gms": "gams",
    ".mod": "ampl",
    ".jl": "jump",
    ".py": "python",
    ".pdf": "pdf",
}

#: Alternative spellings accepted for an explicit ``fmt=`` argument, so a
#: caller may pass either the format key or the bare file extension.
FMT_ALIASES: dict[str, str] = {
    "tex": "latex",
    "gms": "gams",
    "mod": "ampl",
    "jl": "jump",
    "py": "python",
}

#: Formats the validation pipeline sniffs and parses. It deliberately
#: excludes ``pdf``: a PDF is binary, so the sniffer must never be handed
#: one as text.
SNIFFABLE_FORMATS: tuple[str, ...] = tuple(f for f in FORMATS if f != "pdf")

#: Extension -> format key for the sniffable subset.
SNIFFABLE_EXT_FMT: dict[str, str] = {
    ext: fmt for ext, fmt in EXT_FMT.items() if fmt in SNIFFABLE_FORMATS
}


def format_for_extension(suffix: str) -> str | None:
    """Return the format key for a file ``suffix``, or ``None`` if unknown.

    ``suffix`` is matched case-insensitively and may be given with or
    without its leading dot (``".TeX"`` and ``"tex"`` both resolve to
    ``"latex"``).
    """
    s = suffix.lower()
    if not s.startswith("."):
        s = "." + s
    return EXT_FMT.get(s)


def normalize_format(fmt: str) -> str | None:
    """Resolve a user-supplied format string to a canonical format key.

    Accepts a key from :data:`FORMATS` or an alias from
    :data:`FMT_ALIASES`; returns ``None`` for anything unrecognized so the
    caller can report it rather than guess.
    """
    key = fmt.lower().lstrip(".")
    key = FMT_ALIASES.get(key, key)
    return key if key in FORMATS else None


__all__ = [
    "EXT_FMT",
    "FMT_ALIASES",
    "FORMATS",
    "SNIFFABLE_EXT_FMT",
    "SNIFFABLE_FORMATS",
    "format_for_extension",
    "normalize_format",
]
