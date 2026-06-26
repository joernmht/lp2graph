"""Concrete grounding and solving of formulations.

    from lp2graph import load
    from lp2graph.solve import Instance, solve

    f = load("formulations/constraints/mip_2_4_time_indexed.json")
    inst = Instance(cardinalities={"I": 3, "T": 3}, parameters={"cap": 1})
    print(solve(f, inst).objective)

``Instance`` is importable without a solver installed; the grounder
(``solve``, ``build_problem``, ``to_lp_string``, ``SolveResult``,
``UnsupportedModel``) is loaded lazily on first access and requires the
optional ``solver`` extra (``pip install "lp2graph[solver]"``). See
:mod:`lp2graph.solve.grounder` for the supported feature set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lp2graph.solve.instance import Instance

if TYPE_CHECKING:  # for type checkers / IDEs only — no runtime pulp import
    from lp2graph.solve.grounder import (
        SolveResult,
        UnsupportedModel,
        build_problem,
        default_solver,
        solve,
        to_lp_string,
    )

_LAZY = {
    "SolveResult",
    "UnsupportedModel",
    "build_problem",
    "default_solver",
    "solve",
    "to_lp_string",
}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        from lp2graph.solve import grounder

        return getattr(grounder, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Instance",
    "SolveResult",
    "UnsupportedModel",
    "build_problem",
    "default_solver",
    "solve",
    "to_lp_string",
]
