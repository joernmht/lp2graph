"""Solver-free tests for the deterministic indicator ⇄ big-M transform."""

import pytest

from lp2graph.transform import (
    Bounds,
    IndicatorConstraint,
    LinearConstraint,
    UnboundedExpressionError,
    expr_extremum,
    minimal_big_m,
    to_big_m,
)


def _box(**kw):
    return {v: Bounds(lo, hi) for v, (lo, hi) in kw.items()}


def test_expr_extremum_picks_corners():
    coeffs = {"x": 2.0, "y": -3.0}
    b = _box(x=(0, 10), y=(1, 4))
    assert expr_extremum(coeffs, b, maximize=True) == 2 * 10 - 3 * 1  # 17
    assert expr_extremum(coeffs, b, maximize=False) == 2 * 0 - 3 * 4  # -12


def test_minimal_M_le():
    # body: x <= 3, with 0 <= x <= 10  =>  M = max(x) - 3 = 7
    ind = IndicatorConstraint("y", 1, LinearConstraint({"x": 1.0}, "le", 3.0))
    assert minimal_big_m(ind, _box(x=(0, 10))) == 7.0


def test_minimal_M_ge():
    # body: x >= 8, with 0 <= x <= 10  =>  M = 8 - min(x) = 8
    ind = IndicatorConstraint("y", 1, LinearConstraint({"x": 1.0}, "ge", 8.0))
    assert minimal_big_m(ind, _box(x=(0, 10))) == 8.0


def test_minimal_M_never_negative():
    # body already always satisfied over the box => M clamped to 0
    ind = IndicatorConstraint("y", 1, LinearConstraint({"x": 1.0}, "le", 100.0))
    assert minimal_big_m(ind, _box(x=(0, 10))) == 0.0


def test_to_big_m_le_active_one():
    # if y=1 then x <= 3   =>   x + 7 y <= 10   (vacuous at y=0: x<=10; tight at y=1: x<=3)
    ind = IndicatorConstraint("y", 1, LinearConstraint({"x": 1.0}, "le", 3.0))
    (lc,) = to_big_m(ind, _box(x=(0, 10)))
    assert lc.sense == "le"
    assert lc.coeffs == {"x": 1.0, "y": 7.0}
    assert lc.rhs == 10.0


def test_to_big_m_le_active_zero():
    # if y=0 then x <= 3   =>   x - 7 y <= 3   (vacuous at y=1: x<=10)
    ind = IndicatorConstraint("y", 0, LinearConstraint({"x": 1.0}, "le", 3.0))
    (lc,) = to_big_m(ind, _box(x=(0, 10)))
    assert lc.coeffs == {"x": 1.0, "y": -7.0}
    assert lc.rhs == 3.0


def test_to_big_m_ge_active_one():
    # if y=1 then x >= 8  =>  x - 8 y >= 0   (vacuous at y=0: x>=-8; tight at y=1: x>=8)
    ind = IndicatorConstraint("y", 1, LinearConstraint({"x": 1.0}, "ge", 8.0))
    (lc,) = to_big_m(ind, _box(x=(0, 10)))
    assert lc.sense == "ge"
    assert lc.coeffs == {"x": 1.0, "y": -8.0}
    assert lc.rhs == 0.0


def test_eq_is_split_into_two_rows():
    ind = IndicatorConstraint("y", 1, LinearConstraint({"x": 1.0}, "eq", 5.0))
    rows = to_big_m(ind, _box(x=(0, 10)))
    assert {r.sense for r in rows} == {"le", "ge"}
    assert len(rows) == 2


def test_explicit_M_override_when_unbounded():
    ind = IndicatorConstraint("y", 1, LinearConstraint({"x": 1.0}, "le", 3.0))
    # x has no upper bound -> tight M impossible, but explicit m works
    with pytest.raises(UnboundedExpressionError):
        to_big_m(ind, {"x": Bounds(0, None)})
    (lc,) = to_big_m(ind, {"x": Bounds(0, None)}, m=1000.0)
    assert lc.coeffs == {"x": 1.0, "y": 1000.0}
    assert lc.rhs == 1003.0


def test_gating_binary_must_not_be_in_body():
    with pytest.raises(ValueError):
        IndicatorConstraint("y", 1, LinearConstraint({"y": 1.0}, "le", 3.0))
