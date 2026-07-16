"""The text-format round-trip matrix: LP, MPS, GAMS, AMPL, JuMP.

Every format is exercised ``code -> graph -> code`` against models with
hand-verified optima: emit, re-parse, solve with CBC, and require the
known objective. Emitters must also be fixpoints (emit(parse(emit)) ==
emit) and deterministic (same input, same string).
"""

from __future__ import annotations

import _models
import pytest

from lp2graph.interop import (
    InteropError,
    from_ampl,
    from_gams,
    from_jump,
    from_lp_string,
    from_mps_string,
    to_ampl,
    to_gams,
    to_jump,
    to_lp_string,
    to_mps_string,
)
from lp2graph.interop._linexpr import parse_linexpr

FORMATS = {
    "lp": (to_lp_string, from_lp_string),
    "mps": (to_mps_string, from_mps_string),
    "gams": (to_gams, from_gams),
    "ampl": (to_ampl, from_ampl),
    "jump": (to_jump, from_jump),
}


@pytest.fixture(params=sorted(FORMATS), ids=str)
def fmt(request):
    return request.param


# ---------------------------------------------------------------------------
# The matrix: 3 known-optimum models x 5 formats
# ---------------------------------------------------------------------------


def test_roundtrip_solves_to_known_optimum(known_model, fmt):
    f, optimum = known_model
    emit, parse = FORMATS[fmt]
    g = parse(emit(f))
    assert _models.solve_cbc(g) == pytest.approx(optimum)


def test_emit_is_deterministic_and_a_fixpoint(known_model, fmt):
    f, _ = known_model
    emit, parse = FORMATS[fmt]
    text = emit(f)
    assert emit(f) == text  # deterministic
    assert emit(parse(text)) == text  # fixpoint under re-parse


def test_template_model_exports_through_grounding(fmt):
    """A template-level formulation exports via the PuLP grounding path."""
    pytest.importorskip("pulp")
    f, inst = _models.assignment_template()
    emit, parse = FORMATS[fmt]
    g = parse(emit(f, inst))
    assert _models.solve_cbc(g) == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Hand-authored external sources with known optima
# ---------------------------------------------------------------------------


def test_lp_gurobi_style_source():
    """Gurobi's LP dialect: objective constant via a fixed 'Constant' var."""
    text = """\\ Model express_freight
\\ LP format - for model browsing.
Maximize
  4 x1 + 10 x2 - 12 y + 7 Constant
Subject To
 hours: 2 x1 + 3 x2 <= 18
 link: x2 - 5 y <= 0
Bounds
 Constant = 1
Binaries
 y
End
"""
    g = from_lp_string(text)
    assert _models.solve_cbc(g) == pytest.approx(51.0)


def test_mps_external_source_with_objsense_and_markers():
    text = """* toy knapsack (Z* = 220)
NAME knap
OBJSENSE
    MAXIMIZE
ROWS
 N  profit
 L  cap
COLUMNS
    MARKER                 'MARKER'                 'INTORG'
    a         profit    60   cap       10
    b         profit    100  cap       20
    c         profit    120  cap       30
    MARKER                 'MARKER'                 'INTEND'
RHS
    RHS       cap       50
BOUNDS
 BV BND       a
 BV BND       b
 BV BND       c
ENDATA
"""
    g = from_mps_string(text)
    assert g.family == "milp"
    assert _models.solve_cbc(g) == pytest.approx(220.0)


def test_gams_external_source():
    text = """
* toy knapsack
Binary Variables a, b, c;
Variables profit 'objective value';
Equations obj 'objective', cap 'capacity';
obj .. profit =e= 60*a + 100*b + 120*c;
cap .. 10*a + 20*b + 30*c =l= 50;
Model knap / all /;
Solve knap using mip maximizing profit;
"""
    g = from_gams(text)
    assert g.id == "knap"
    assert _models.solve_cbc(g) == pytest.approx(220.0)


def test_ampl_external_source_with_ranged_constraint():
    text = """
# diet-style toy: min cost with a ranged nutrient window
var meat >= 0;
var beans >= 0;
minimize cost: 4*meat + 1*beans;
subject to protein: 2 <= 0.5*meat + 0.25*beans <= 4;
"""
    g = from_ampl(text)
    # cheapest way to reach 0.5 m + 0.25 b >= 2 is beans = 8 -> cost 8
    assert _models.solve_cbc(g) == pytest.approx(8.0)
    assert {c.name for c in g.constraints} == {"protein_lo", "protein_up"}


def test_jump_external_source_implicit_multiplication():
    text = """
using JuMP, HiGHS
model = Model(HiGHS.Optimizer)
@variable(model, a, Bin)
@variable(model, b, Bin)
@variable(model, c, Bin)
@variable(model, 0 <= slack <= 100)
@objective(model, Max, 60a + 100b + 120c)
@constraint(model, cap, 10a + 20b + 30c <= 50)
@constraint(model, 0 <= slack <= 100)
optimize!(model)
println(objective_value(model))
"""
    g = from_jump(text)
    assert _models.solve_cbc(g) == pytest.approx(220.0)


# ---------------------------------------------------------------------------
# Honest failures: unsupported constructs raise, nothing drops silently
# ---------------------------------------------------------------------------


def test_lp_sos_section_raises():
    with pytest.raises(InteropError, match="SOS"):
        from_lp_string("Minimize\n obj: x\nSubject To\n c: x >= 1\nSOS\n s1: S1:: x:1\nEnd\n")


def test_mps_ranges_section_raises():
    text = "NAME r\nROWS\n N obj\n L c\nCOLUMNS\n x obj 1 c 1\nRANGES\n R c 5\nENDATA\n"
    with pytest.raises(InteropError, match="RANGES"):
        from_mps_string(text)


def test_gams_sets_raise():
    with pytest.raises(InteropError, match="scalar subset"):
        from_gams("Set i /1*3/;\nVariables z;\nSolve m using lp minimizing z;")


def test_ampl_params_raise():
    with pytest.raises(InteropError, match="scalar subset"):
        from_ampl("param n; var x >= 0; minimize obj: x;")


def test_jump_indexed_variable_raises():
    with pytest.raises(InteropError, match="scalar subset"):
        from_jump("@variable(model, x[1:3] >= 0)\n@objective(model, Min, 0)")


def test_linexpr_rejects_nonlinear_products():
    with pytest.raises(InteropError):
        parse_linexpr("3 x * y")
    with pytest.raises(InteropError):
        parse_linexpr("2 / x")


def test_linexpr_affine_forms():
    coefs, const = parse_linexpr("- 3 x1 + 4.5*x2 - x3 + 2e-1 x4 + 7 - 2 + x1")
    assert coefs == {"x1": -2.0, "x2": 4.5, "x3": -1.0, "x4": 0.2}
    assert const == pytest.approx(5.0)
