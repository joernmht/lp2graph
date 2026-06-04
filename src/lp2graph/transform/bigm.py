"""Indicator ⇄ big-M, done deterministically and solver-free.

An **indicator constraint** says: *if* binary ``y`` equals ``active_value``,
*then* the linear body ``Σ cᵢ·xᵢ  {≤,≥,=}  rhs`` must hold.

Two faithful encodings of the same logic:

* **native indicator** — for solvers that support it (Gurobi, CPLEX). Exact;
  no ``M``; immune to the big-M tolerance trap.
* **big-M linearization** — for solvers that do not (HiGHS, CBC, older tools).
  We add ``±M·(1-y)`` (or ``±M·y``) so the body is *switched off* when the
  indicator is inactive. ``M`` is the **tightest valid value**, computed
  exactly from the variable bounds:

  * body ``a·x ≤ b`` :  ``M = max(a·x) - b``  over the variable box;
  * body ``a·x ≥ b`` :  ``M = b - min(a·x)``  over the variable box.

  The extrema of a linear form over a box are attained at a corner, so this
  is pure arithmetic — deterministic and reproducible, no solver needed.

The only thing that prevents a finite ``M`` is a genuinely unbounded
variable; in that case we raise :class:`UnboundedExpressionError` rather than
inventing a number. Callers may supply an explicit ``m`` to override.

Equality bodies are split into a ``≤`` and a ``≥`` part (two big-M rows), as
solvers do internally.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Sense = Literal["le", "ge", "eq"]


class UnboundedExpressionError(ValueError):
    """Raised when a tight finite big-M cannot be computed because a variable
    appearing in the body lacks a finite bound in the relevant direction."""


@dataclass(frozen=True)
class Bounds:
    """Per-variable closed interval; ``None`` means unbounded on that side."""

    lo: float | None = None
    hi: float | None = None


@dataclass(frozen=True)
class LinearConstraint:
    """A grounded scalar linear constraint ``Σ coeffs[v]·v  <sense>  rhs``."""

    coeffs: dict[str, float]
    sense: Sense
    rhs: float

    def pretty(self) -> str:
        body = " + ".join(f"{c:g}*{v}" for v, c in self.coeffs.items())
        op = {"le": "<=", "ge": ">=", "eq": "="}[self.sense]
        return f"{body} {op} {self.rhs:g}"


@dataclass(frozen=True)
class IndicatorConstraint:
    """``if binary == active_value then body``."""

    binary: str
    active_value: int  # 0 or 1
    body: LinearConstraint

    def __post_init__(self) -> None:
        if self.active_value not in (0, 1):
            raise ValueError("active_value must be 0 or 1")
        if self.binary in self.body.coeffs:
            raise ValueError("the gating binary must not appear in the body")


def expr_extremum(coeffs: dict[str, float], bounds: dict[str, Bounds], *, maximize: bool) -> float:
    """max/min of ``Σ coeffs[v]·v`` over the box given by ``bounds``.

    Attained at a corner: for a maximization, take ``hi`` where the coefficient
    is positive and ``lo`` where it is negative (and vice-versa for min).
    Raises :class:`UnboundedExpressionError` if the needed bound is missing.
    """
    total = 0.0
    for v, c in coeffs.items():
        if c == 0:
            continue
        b = bounds.get(v, Bounds())
        take_hi = (c > 0) if maximize else (c < 0)
        edge = b.hi if take_hi else b.lo
        if edge is None:
            side = "upper" if take_hi else "lower"
            raise UnboundedExpressionError(
                f"variable {v!r} has no {side} bound; cannot compute a tight finite M"
            )
        total += c * edge
    return total


def minimal_big_m(ind: IndicatorConstraint, bounds: dict[str, Bounds]) -> float:
    """Smallest M making the big-M relaxation non-binding when the indicator is
    off. ``eq`` must be split first (see :func:`to_big_m`)."""
    b = ind.body
    if b.sense == "le":
        m = expr_extremum(b.coeffs, bounds, maximize=True) - b.rhs
    elif b.sense == "ge":
        m = b.rhs - expr_extremum(b.coeffs, bounds, maximize=False)
    else:
        raise ValueError("split an 'eq' body into 'le' and 'ge' before computing M")
    return max(0.0, m)


def _split_eq(ind: IndicatorConstraint) -> list[IndicatorConstraint]:
    b = ind.body
    if b.sense != "eq":
        return [ind]
    return [
        IndicatorConstraint(ind.binary, ind.active_value, LinearConstraint(dict(b.coeffs), "le", b.rhs)),
        IndicatorConstraint(ind.binary, ind.active_value, LinearConstraint(dict(b.coeffs), "ge", b.rhs)),
    ]


def to_indicator(ind: IndicatorConstraint) -> IndicatorConstraint:
    """Identity: the native-indicator encoding is the canonical logic itself.
    Provided for symmetry with :func:`to_big_m` so a back-end can call one of
    the two by target."""
    return ind


def to_big_m(
    ind: IndicatorConstraint,
    bounds: dict[str, Bounds] | None = None,
    *,
    m: float | None = None,
) -> list[LinearConstraint]:
    """Big-M linearization of an indicator constraint.

    Returns one :class:`LinearConstraint` (two for an ``eq`` body). ``M`` is
    the tightest value from ``bounds`` unless an explicit ``m`` is given. The
    gating binary ``y`` is added to the body with the right sign so the
    constraint is vacuous when the indicator is inactive:

    * ``le`` body, active when ``y=1`` :  ``a·x + M·y ≤ b + M``
    * ``le`` body, active when ``y=0`` :  ``a·x - M·y ≤ b``
    * ``ge`` body, active when ``y=1`` :  ``a·x - M·y ≥ b - M``
    * ``ge`` body, active when ``y=0`` :  ``a·x + M·y ≥ b``
    """
    out: list[LinearConstraint] = []
    for part in _split_eq(ind):
        b = part.body
        big_m = m if m is not None else minimal_big_m(part, bounds or {})
        coeffs = dict(b.coeffs)
        if b.sense == "le":
            if part.active_value == 1:
                coeffs[part.binary] = coeffs.get(part.binary, 0.0) + big_m
                out.append(LinearConstraint(coeffs, "le", b.rhs + big_m))
            else:
                coeffs[part.binary] = coeffs.get(part.binary, 0.0) - big_m
                out.append(LinearConstraint(coeffs, "le", b.rhs))
        else:  # ge
            if part.active_value == 1:
                coeffs[part.binary] = coeffs.get(part.binary, 0.0) - big_m
                out.append(LinearConstraint(coeffs, "ge", b.rhs - big_m))
            else:
                coeffs[part.binary] = coeffs.get(part.binary, 0.0) + big_m
                out.append(LinearConstraint(coeffs, "ge", b.rhs))
    return out
