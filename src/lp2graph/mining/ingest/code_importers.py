"""Solver-code importer registry (M1a).

A clean dispatcher over solver-language source files. The **GAMS**,
**AMPL**, **JuMP**, **LP**, and **MPS** entries are real: they route to
the deterministic parsers in :mod:`lp2graph.interop` and return a
validated, coefficient-faithful flat formulation. Anything the parsers
cannot represent surfaces as a structured :class:`IngestionFailure`
with ``stage="parse"`` -- never a swallowed exception and never a
silent drop.

Because a ``.py`` file is arbitrary code, importing a Python-hosted
model (gurobipy / PuLP / Pyomo) requires *executing* the module, which
the deterministic ingestion core does not do. A ``.py`` path is
therefore reported as ``"unsupported"``, with guidance to build the
model object and call :func:`lp2graph.interop.from_gurobipy` /
:func:`~lp2graph.interop.from_pulp` / :func:`~lp2graph.interop.from_pyomo`.
"""

from __future__ import annotations

from collections.abc import Callable

from lp2graph.core.model import Formulation
from lp2graph.interop._grounded import InteropError
from lp2graph.mining.ingest.result import IngestionResult
from lp2graph.mining.provenance import ProvenanceMap

# ---------------------------------------------------------------------------
# Real text importers (route to lp2graph.interop)
# ---------------------------------------------------------------------------


def _run_parser(
    parse: Callable[[str], Formulation], text: str, *, source: str, fmt: str
) -> IngestionResult:
    try:
        formulation = parse(text)
    except InteropError as exc:
        return IngestionResult.single_failure(
            source=source,
            stage="parse",
            message=f"{fmt} parse failed: {exc}",
            detail=type(exc).__name__,
        )
    return IngestionResult.success(
        source=source,
        formulation=formulation,
        provenance=ProvenanceMap(source=source),
    )


def import_gams(text: str, *, source: str) -> IngestionResult:
    """GAMS importer (scalar-linear subset; see :func:`lp2graph.interop.from_gams`)."""
    from lp2graph.interop.gams import from_gams

    return _run_parser(from_gams, text, source=source, fmt="GAMS")


def import_ampl(text: str, *, source: str) -> IngestionResult:
    """AMPL importer (scalar-linear subset; see :func:`lp2graph.interop.from_ampl`)."""
    from lp2graph.interop.ampl import from_ampl

    return _run_parser(from_ampl, text, source=source, fmt="AMPL")


def import_jump(text: str, *, source: str) -> IngestionResult:
    """JuMP importer (scalar-linear subset; see :func:`lp2graph.interop.from_jump`)."""
    from lp2graph.interop.jump import from_jump

    return _run_parser(from_jump, text, source=source, fmt="JuMP")


def import_lp(text: str, *, source: str) -> IngestionResult:
    """CPLEX/Gurobi LP-file importer (see :func:`lp2graph.interop.from_lp_string`)."""
    from lp2graph.interop.lp_format import from_lp_string

    return _run_parser(from_lp_string, text, source=source, fmt="LP")


def import_mps(text: str, *, source: str) -> IngestionResult:
    """MPS-file importer (see :func:`lp2graph.interop.from_mps_string`)."""
    from lp2graph.interop.mps import from_mps_string

    return _run_parser(from_mps_string, text, source=source, fmt="MPS")


# ---------------------------------------------------------------------------
# Honest stub (executing arbitrary Python is out of scope by design)
# ---------------------------------------------------------------------------


def import_python(text: str, *, source: str) -> IngestionResult:
    """Python source importer -- reports an unsupported failure.

    Importing a model from ``.py`` source means *executing* it, which the
    deterministic core does not do. Callers should build the model object
    themselves and pass it to ``lp2graph.interop.from_gurobipy`` /
    ``from_pulp`` / ``from_pyomo`` (or the structural
    :func:`lp2graph.mining.ingest.from_pyomo`).
    """
    return IngestionResult.single_failure(
        source=source,
        stage="unsupported",
        message="Python/solver-API ingestion from source is not performed "
        "(it would require executing the file).",
        detail="Build the model object and call lp2graph.interop.from_gurobipy / "
        "from_pulp / from_pyomo, or export the model to .lp/.mps and ingest that.",
    )


#: Registry mapping a format key to its text importer. The dispatcher
#: (:mod:`lp2graph.mining.ingest.dispatch`) routes by file extension or an
#: explicit ``fmt`` into this table.
CODE_IMPORTERS: dict[str, Callable[..., IngestionResult]] = {
    "python": import_python,
    "gams": import_gams,
    "ampl": import_ampl,
    "jump": import_jump,
    "lp": import_lp,
    "mps": import_mps,
}


__all__ = [
    "CODE_IMPORTERS",
    "import_ampl",
    "import_gams",
    "import_jump",
    "import_lp",
    "import_mps",
    "import_python",
]
