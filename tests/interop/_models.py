"""Shared model builders for the interop test matrix.

Three small models with hand-verified optima drive every
``code -> graph -> code`` round-trip:

- ``express_freight`` (MILP, max): Z* = 44 at x1=1.5, x2=5, y=1.
- ``dantzig`` (pure LP, max): Z* = 36 at x=2, y=6.
- ``mix_min`` (min, equality + free variable + objective constant):
  Z* = 25 at a=10, b=0.
"""

from __future__ import annotations

import pytest

from lp2graph.core.model import (
    ConstraintTemplate,
    Formulation,
    Index,
    Objective,
    Parameter,
    Quantifier,
    Term,
    VariableTemplate,
)
from lp2graph.solve.instance import Instance

EMPTY = Instance(cardinalities={})


def express_freight() -> Formulation:
    """max 4 x1 + 10 x2 - 12 y ; 2 x1 + 3 x2 <= 18 ; x2 <= 5 y ; y binary."""
    return Formulation(
        id="express_freight",
        name="Express freight dispatch",
        family="milp",
        variables=(
            VariableTemplate(name="x1", domain="non_negative"),
            VariableTemplate(name="x2", domain="non_negative"),
            VariableTemplate(name="y", domain="binary"),
        ),
        objective=Objective(
            sense="max",
            terms=(
                Term(ref="x1", coefficient=4, role="objective"),
                Term(ref="x2", coefficient=10, role="objective"),
                Term(ref="y", coefficient=12, sign=-1, role="objective"),
            ),
        ),
        constraints=(
            ConstraintTemplate(
                name="hours",
                comparator="le",
                lhs=(
                    Term(ref="x1", coefficient=2, role="lhs"),
                    Term(ref="x2", coefficient=3, role="lhs"),
                ),
                rhs=(Term(constant=18, role="rhs"),),
            ),
            ConstraintTemplate(
                name="link",
                comparator="le",
                lhs=(Term(ref="x2", role="lhs"),),
                rhs=(Term(ref="y", coefficient=5, role="rhs"),),
            ),
        ),
    )


def dantzig() -> Formulation:
    """max 3 x + 5 y ; x <= 4 ; 2 y <= 12 ; 3 x + 2 y <= 18 (Z* = 36)."""
    return Formulation(
        id="dantzig",
        name="Dantzig textbook LP",
        family="lp",
        variables=(
            VariableTemplate(name="x", domain="non_negative", upper=4),
            VariableTemplate(name="y", domain="non_negative"),
        ),
        objective=Objective(
            sense="max",
            terms=(
                Term(ref="x", coefficient=3, role="objective"),
                Term(ref="y", coefficient=5, role="objective"),
            ),
        ),
        constraints=(
            ConstraintTemplate(
                name="machine_b",
                comparator="le",
                lhs=(Term(ref="y", coefficient=2, role="lhs"),),
                rhs=(Term(constant=12, role="rhs"),),
            ),
            ConstraintTemplate(
                name="machine_c",
                comparator="le",
                lhs=(
                    Term(ref="x", coefficient=3, role="lhs"),
                    Term(ref="y", coefficient=2, role="lhs"),
                ),
                rhs=(Term(constant=18, role="rhs"),),
            ),
        ),
    )


def mix_min() -> Formulation:
    """min 2 a + 3 b + 5 ; a + b = 10 ; a - b >= -2 ; a free, 0 <= b <= 6.

    Z* = 25 at a=10, b=0 (equality, negative RHS, free variable, and an
    objective constant all in one model).
    """
    return Formulation(
        id="mix_min",
        name="Minimization mix",
        family="lp",
        variables=(
            VariableTemplate(name="a", domain="continuous"),
            VariableTemplate(name="b", domain="non_negative", upper=6),
        ),
        objective=Objective(
            sense="min",
            terms=(
                Term(ref="a", coefficient=2, role="objective"),
                Term(ref="b", coefficient=3, role="objective"),
                Term(constant=5, role="objective"),
            ),
        ),
        constraints=(
            ConstraintTemplate(
                name="total",
                comparator="eq",
                lhs=(
                    Term(ref="a", role="lhs"),
                    Term(ref="b", role="lhs"),
                ),
                rhs=(Term(constant=10, role="rhs"),),
            ),
            ConstraintTemplate(
                name="skew",
                comparator="ge",
                lhs=(
                    Term(ref="a", role="lhs"),
                    Term(ref="b", sign=-1, role="lhs"),
                ),
                rhs=(Term(constant=-2, role="rhs"),),
            ),
        ),
    )


def assignment_template() -> tuple[Formulation, Instance]:
    """A 2x2 assignment problem as a *template-level* formulation.

    min sum_ij c_ij x_ij with row/column partition constraints; costs
    [[1, 10], [10, 2]] make the optimum 3 (diagonal assignment). This
    exercises the PuLP grounding path of the exporters (indices,
    quantifiers, sum terms, parameter coefficients).
    """
    f = Formulation(
        id="assignment_2x2",
        name="2x2 assignment",
        family="milp",
        indices=(Index(name="I"), Index(name="J")),
        parameters=(Parameter(name="c", shape=("I", "J"), kind="matrix"),),
        variables=(VariableTemplate(name="x", shape=("I", "J"), domain="binary"),),
        objective=Objective(
            sense="min",
            terms=(
                Term(
                    ref="x",
                    coefficient="c",
                    role="objective",
                    operator="sum",
                    operator_over=("I", "J"),
                    bindings=(
                        {"index": "I", "expr": "i"},
                        {"index": "J", "expr": "j"},
                    ),
                ),
            ),
        ),
        constraints=(
            ConstraintTemplate(
                name="row",
                quantifiers=(Quantifier(index="i", over="I"),),
                comparator="eq",
                lhs=(
                    Term(
                        ref="x",
                        role="lhs",
                        operator="sum",
                        operator_over=("J",),
                        bindings=(
                            {"index": "I", "expr": "i"},
                            {"index": "J", "expr": "j"},
                        ),
                    ),
                ),
                rhs=(Term(constant=1, role="rhs"),),
            ),
            ConstraintTemplate(
                name="col",
                quantifiers=(Quantifier(index="j", over="J"),),
                comparator="eq",
                lhs=(
                    Term(
                        ref="x",
                        role="lhs",
                        operator="sum",
                        operator_over=("I",),
                        bindings=(
                            {"index": "I", "expr": "i"},
                            {"index": "J", "expr": "j"},
                        ),
                    ),
                ),
                rhs=(Term(constant=1, role="rhs"),),
            ),
        ),
    )
    inst = Instance(
        cardinalities={"I": 2, "J": 2},
        parameters={"c": [[1, 10], [10, 2]]},
    )
    return f, inst


#: (formulation factory, known optimum) for the flat round-trip matrix.
KNOWN_MODELS = (
    (express_freight, 44.0),
    (dantzig, 36.0),
    (mix_min, 25.0),
)


def solve_cbc(f: Formulation) -> float:
    """Ground + solve a flat formulation with CBC; return the objective."""
    pulp = pytest.importorskip("pulp")
    del pulp
    from lp2graph.solve.grounder import solve

    result = solve(f, EMPTY)
    assert result.status == "optimal", result
    assert result.objective is not None
    return result.objective
