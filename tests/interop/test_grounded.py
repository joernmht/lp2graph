"""Unit tests for the grounded-model hub (`lp2graph.interop._grounded`)."""

from __future__ import annotations

import _models
import pytest

from lp2graph.core.model import (
    ConstraintTemplate,
    Formulation,
    Objective,
    Term,
    VariableTemplate,
)
from lp2graph.interop._grounded import (
    GroundedModel,
    GroundedVar,
    InteropError,
    NameMap,
    format_number,
    ground,
    to_formulation,
)


def test_flat_ground_normalizes_sides():
    """Variables and constants on both sides fold into ``vars <cmp> rhs``."""
    f = Formulation(
        id="norm",
        name="normalization",
        family="lp",
        variables=(
            VariableTemplate(name="u", domain="non_negative"),
            VariableTemplate(name="w", domain="non_negative"),
        ),
        objective=Objective(sense="min", terms=(Term(ref="u", role="objective"),)),
        constraints=(
            # 2u + 3 - w <= w + 7   ==>   2u - 2w <= 4
            ConstraintTemplate(
                name="both_sides",
                comparator="le",
                lhs=(
                    Term(ref="u", coefficient=2, role="lhs"),
                    Term(constant=3, role="lhs"),
                    Term(ref="w", sign=-1, role="lhs"),
                ),
                rhs=(
                    Term(ref="w", role="rhs"),
                    Term(constant=7, role="rhs"),
                ),
            ),
            # u + u >= 4   ==>  2u >= 4 (duplicate refs accumulate)
            ConstraintTemplate(
                name="dupes",
                comparator="ge",
                lhs=(
                    Term(ref="u", role="lhs"),
                    Term(ref="u", role="lhs"),
                ),
                rhs=(Term(constant=4, role="rhs"),),
            ),
        ),
    )
    gm = ground(f)
    both = gm.constraints[0]
    assert dict((v, c) for c, v in both.terms) == {"u": 2.0, "w": -2.0}
    assert both.rhs == 4.0
    dupes = gm.constraints[1]
    assert dupes.terms == ((2.0, "u"),)
    assert dupes.rhs == 4.0


def test_flat_ground_objective_constant():
    f = _models.mix_min()
    gm = ground(f)
    assert gm.sense == "min"
    assert gm.objective_constant == 5.0
    assert dict((v, c) for c, v in gm.objective) == {"a": 2.0, "b": 3.0}


def test_template_model_grounds_through_pulp():
    pytest.importorskip("pulp")
    f, inst = _models.assignment_template()
    gm = ground(f, inst)
    assert len(gm.variables) == 4
    assert all(v.domain == "binary" for v in gm.variables)
    assert len(gm.constraints) == 4  # 2 rows + 2 cols
    from lp2graph.solve.grounder import solve

    assert solve(f, inst).objective == pytest.approx(3.0)


def test_to_formulation_roundtrips_flat_ground(known_model):
    f, _ = known_model
    gm = ground(f)
    g = to_formulation(gm)
    assert ground(g) == gm  # the hub is a fixpoint for flat models


def test_to_formulation_sanitizes_and_disambiguates_names():
    gm = GroundedModel(
        id="Messy Names!",
        name="messy",
        sense="min",
        variables=(
            GroundedVar(name="x(1,2)", domain="continuous"),
            GroundedVar(name="x_1_2_", domain="continuous"),
            GroundedVar(name="2fast", domain="continuous"),
        ),
        objective=((1.0, "x(1,2)"), (1.0, "x_1_2_"), (1.0, "2fast")),
    )
    g = to_formulation(gm)
    names = [v.name for v in g.variables]
    assert names == ["x_1_2_", "x_1_2__2", "_2fast"]
    assert g.id == "messy_names"


def test_undeclared_variable_is_an_error():
    gm = GroundedModel(
        id="bad",
        name="bad",
        sense="min",
        variables=(GroundedVar(name="u", domain="continuous"),),
        objective=((1.0, "ghost"),),
    )
    with pytest.raises(InteropError, match="ghost"):
        to_formulation(gm)


def test_namemap_is_deterministic():
    a, b = NameMap(), NameMap()
    seq = ["x", "x!", "x_", "x!", "y y"]
    assert [a.get(s, fallback="v") for s in seq] == [b.get(s, fallback="v") for s in seq]


@pytest.mark.parametrize(
    ("value", "text"),
    [(1.0, "1"), (-12.0, "-12"), (4.5, "4.5"), (0.1, "0.1"), (1e30, "1e+30")],
)
def test_format_number(value, text):
    assert format_number(value) == text
