"""Format dispatcher for the ingestion front-end (M1).

:func:`ingest` is the single entry point. It routes a path or raw text to
the right importer by file extension, or by an explicit ``fmt`` override:

- ``.json`` -> canonical ``Formulation`` JSON (:mod:`lp2graph.core.loader`)
- ``.py``  -> Python-hosted model source (reported unsupported; build the
  model object and use ``lp2graph.interop.from_gurobipy`` / ``from_pulp``
  / ``from_pyomo``)
- ``.gms`` -> GAMS (scalar-linear subset, :mod:`lp2graph.interop.gams`)
- ``.mod`` -> AMPL (scalar-linear subset, :mod:`lp2graph.interop.ampl`)
- ``.jl``  -> JuMP (scalar-linear subset, :mod:`lp2graph.interop.jump`)
- ``.lp``  -> CPLEX/Gurobi LP file (:mod:`lp2graph.interop.lp_format`)
- ``.mps`` -> MPS file (:mod:`lp2graph.interop.mps`)
- ``.tex`` -> non-canonical LaTeX normalizer (:func:`ingest_latex`)
- ``.pdf`` -> reported unsupported (deterministic core does not do PDF
  math extraction)

Unknown extensions/formats produce a reported :class:`IngestionFailure`,
never an exception. This keeps the M1 invariant intact at the routing
layer too: there is no input that silently drops.
"""

from __future__ import annotations

from pathlib import Path

from lp2graph.formats import EXT_FMT, normalize_format
from lp2graph.mining.ingest.code_importers import CODE_IMPORTERS
from lp2graph.mining.ingest.latex_normalizer import ingest_latex
from lp2graph.mining.ingest.result import IngestionResult

#: File extension -> format key. Re-exported from :mod:`lp2graph.formats`,
#: the single source of truth; do not redefine the table here.
_EXT_FMT: dict[str, str] = EXT_FMT


def _looks_like_path(s: str) -> bool:
    """Heuristic: treat a single-line string with a known suffix as a path."""
    if "\n" in s or len(s) > 4096:
        return False
    return Path(s).suffix.lower() in _EXT_FMT


def ingest(path_or_text: str | Path, *, fmt: str | None = None) -> IngestionResult:
    """Ingest a source artifact into a validated :class:`IngestionResult`.

    Args:
        path_or_text: A filesystem path (``str``/``Path``) to a source
            artifact, or raw source text (requires ``fmt``).
        fmt: Explicit format override -- a key from
            :data:`lp2graph.formats.FORMATS` (or one of its file-extension
            aliases). When omitted, the format is inferred from the path's
            extension.

    Returns:
        An :class:`IngestionResult`. Routing problems (missing file,
        unknown format) are returned as reported failures, not raised.
    """
    source, text, resolved_fmt = _resolve(path_or_text, fmt)
    if isinstance(text, IngestionResult):  # an early routing failure
        return text

    if resolved_fmt is None:
        return IngestionResult.single_failure(
            source=source,
            stage="unsupported",
            message="could not determine format; pass an explicit fmt= or use "
            "a recognized file extension " + "/".join(sorted(EXT_FMT)) + ".",
        )

    # Accept the file-extension spellings too (fmt="tex", fmt="gms", ...).
    resolved_fmt = normalize_format(resolved_fmt) or resolved_fmt

    if resolved_fmt == "latex":
        return ingest_latex(text, source=source)
    if resolved_fmt == "pdf":
        return IngestionResult.single_failure(
            source=source,
            stage="unsupported",
            message="PDF math extraction is out of scope for the deterministic "
            "ingestion core. Extract the author LaTeX and ingest it as .tex.",
        )
    importer = CODE_IMPORTERS.get(resolved_fmt)
    if importer is not None:
        return importer(text, source=source)
    return IngestionResult.single_failure(
        source=source,
        stage="unsupported",
        message=f"unknown format {resolved_fmt!r}.",
    )


def _resolve(
    path_or_text: str | Path, fmt: str | None
) -> tuple[str, str | IngestionResult, str | None]:
    """Resolve (source-id, text-or-failure, format-key).

    Reading a path can fail (missing file); that is returned as an
    :class:`IngestionResult` in the second slot so the caller reports it.
    """
    if isinstance(path_or_text, Path) or (
        isinstance(path_or_text, str) and fmt is None and _looks_like_path(path_or_text)
    ):
        p = Path(path_or_text)
        source = str(p)
        resolved_fmt = fmt or _EXT_FMT.get(p.suffix.lower())
        if resolved_fmt == "pdf":
            # Do not attempt to read PDF bytes as text; report directly.
            return source, "", resolved_fmt
        try:
            text = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            return (
                source,
                IngestionResult.single_failure(
                    source=source,
                    stage="read",
                    message=f"source file not found: {source}",
                ),
                resolved_fmt,
            )
        except UnicodeDecodeError as exc:
            # Third-party corpus files are not always UTF-8 (BOMs, legacy
            # latin-1 comments, binary blobs mistaken for text). ``read_text``
            # raises ``UnicodeDecodeError`` -- a ``ValueError``, *not* an
            # ``OSError`` -- which would otherwise escape and abort the whole
            # batch, breaking the M1 "never an exception, never silently drop"
            # invariant. Report it as a read-stage failure instead.
            return (
                source,
                IngestionResult.single_failure(
                    source=source,
                    stage="read",
                    message=f"source file is not valid UTF-8: {exc}",
                    detail=type(exc).__name__,
                ),
                resolved_fmt,
            )
        except OSError as exc:
            return (
                source,
                IngestionResult.single_failure(
                    source=source,
                    stage="read",
                    message=f"could not read source file: {exc}",
                    detail=type(exc).__name__,
                ),
                resolved_fmt,
            )
        return source, text, resolved_fmt

    # Raw text path.
    source = "<text>"
    return source, str(path_or_text), fmt


__all__ = ["ingest"]
