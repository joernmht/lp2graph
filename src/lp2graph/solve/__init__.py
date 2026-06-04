"""Concrete grounding and solving of formulations.

    from lp2graph import load
    from lp2graph.solve import Instance, solve

    f = load("formulations/constraints/mip_2_4_time_indexed.json")
    inst = Instance(cardinalities={"I": 3, "T": 3}, parameters={"cap": 1})
    print(solve(f, inst).objective)

See :mod:`lp2graph.solve.grounder` for the supported feature set.
"""

from __future__ import annotations

from lp2graph.solve.grounder import (
    SolveResult,
    UnsupportedModel,
    build_problem,
    solve,
    to_lp_string,
)
from lp2graph.solve.instance import Instance

__all__ = [
    "Instance",
    "SolveResult",
    "UnsupportedModel",
    "build_problem",
    "solve",
    "to_lp_string",
]
