"""Deterministic, solver-free transformations of formulations.

`bigm` turns a logical *indicator* constraint ("if y = v then a·x ⋄ b") into
either a native indicator descriptor (for solvers that support it) or a
big-M linearization with the **tightest valid M computed from variable
bounds** (for solvers that do not). Both encodings describe the same feasible
region; the choice is per target solver.
"""

from lp2graph.transform.bigm import (
    Bounds,
    IndicatorConstraint,
    LinearConstraint,
    UnboundedExpressionError,
    expr_extremum,
    minimal_big_m,
    to_big_m,
    to_indicator,
)

__all__ = [
    "Bounds",
    "IndicatorConstraint",
    "LinearConstraint",
    "UnboundedExpressionError",
    "expr_extremum",
    "minimal_big_m",
    "to_big_m",
    "to_indicator",
]
