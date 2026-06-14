"""Solver-code importer registry (M1a).

A clean dispatcher over solver-language source files. The **Pyomo**
importer is real (:mod:`lp2graph.mining.ingest.pyomo_importer`); the
**GAMS**, **AMPL**, and **JuMP** entries are *honest, documented stubs*
that return a structured :class:`IngestionFailure` with
``stage="unsupported"`` -- never a swallowed ``NotImplementedError`` and
never a silent drop. Each message names the format and points the caller
at the working Pyomo path.

Because a ``.py`` file is arbitrary code, importing a Pyomo *model object*
requires executing the module, which the deterministic ingestion core does
not do. A ``.py`` path is therefore reported as ``"unsupported"`` too,
with guidance to call :func:`from_pyomo` on an already-built model.
"""

from __future__ import annotations

from collections.abc import Callable

from lp2graph.mining.ingest.result import IngestionResult

# ---------------------------------------------------------------------------
# Stub importers (honest, reported failures)
# ---------------------------------------------------------------------------


def _unsupported(source: str, fmt: str, hint: str) -> IngestionResult:
    return IngestionResult.single_failure(
        source=source,
        stage="unsupported",
        message=f"{fmt} ingestion is not implemented in this build.",
        detail=hint,
    )


def import_gams(text: str, *, source: str) -> IngestionResult:
    """GAMS importer -- documented stub (reports an unsupported failure)."""
    return _unsupported(
        source,
        "GAMS",
        "No GAMS front-end yet. Build a pyomo.environ model and call "
        "lp2graph.mining.ingest.from_pyomo(model), or supply canonical LaTeX.",
    )


def import_ampl(text: str, *, source: str) -> IngestionResult:
    """AMPL/.mod importer -- documented stub (reports an unsupported failure)."""
    return _unsupported(
        source,
        "AMPL",
        "No AMPL front-end yet. Build a pyomo.environ model and call "
        "lp2graph.mining.ingest.from_pyomo(model), or supply canonical LaTeX.",
    )


def import_jump(text: str, *, source: str) -> IngestionResult:
    """JuMP/Julia importer -- documented stub (reports an unsupported failure).

    A real ``@variable``/``@constraint``/``@objective`` parser would slot
    in here. Honest reporting is preferred over a partial, lossy parse, so
    this entry reports ``unsupported`` until that lands.
    """
    return _unsupported(
        source,
        "JuMP",
        "No JuMP front-end yet. Build a pyomo.environ model and call "
        "lp2graph.mining.ingest.from_pyomo(model), or supply canonical LaTeX.",
    )


def import_python(text: str, *, source: str) -> IngestionResult:
    """Python/Pyomo source importer -- reports an unsupported failure.

    Importing a model from ``.py`` source means *executing* it, which the
    deterministic core does not do. Callers should build the
    ``ConcreteModel`` themselves and pass it to :func:`from_pyomo`.
    """
    return _unsupported(
        source,
        "Python/Pyomo source",
        "Importing from .py source requires executing it. Build the "
        "ConcreteModel and call lp2graph.mining.ingest.from_pyomo(model).",
    )


#: Registry mapping a format key to its text importer. The dispatcher
#: (:mod:`lp2graph.mining.ingest.dispatch`) routes by file extension or an
#: explicit ``fmt`` into this table.
CODE_IMPORTERS: dict[str, Callable[..., IngestionResult]] = {
    "python": import_python,
    "gams": import_gams,
    "ampl": import_ampl,
    "jump": import_jump,
}


__all__ = [
    "CODE_IMPORTERS",
    "import_ampl",
    "import_gams",
    "import_jump",
    "import_python",
]
