"""Canonical normal form for round-trip comparison.

The LaTeX codec preserves the mathematical model exactly but normalizes a
small set of *incidental* fields that have no algebraic surface form and
no effect on grounding/solving:

- A literal term's ``ref`` name (e.g. ``"one"``, ``"_const"``) is folded
  to ``"_const"`` — only its numeric ``coefficient`` matters.
- A binding's ``offset`` is recomputed from its own ``expr`` so a stored
  offset that disagrees with the expression text is corrected.
- ``coefficient`` ``None`` is folded to ``1`` (the schema default).
- A negative numeric ``coefficient`` is folded into ``sign`` (the LaTeX
  surface carries the sign explicitly, the coefficient magnitude bare).
- A term's ``role`` is folded to the default for the side it sits on
  (``lhs``/``rhs``/``objective``). ``role`` only drives edge coloring in
  rendered graphs; it has no algebraic surface form and no effect on
  grounding or solving.

Two formulations that share a canonical normal form are
solve-equivalent and structurally identical up to these labels.
"""

from __future__ import annotations

import re

from lp2graph.core.model import Binding, Formulation, Term

_OFFSET_RE = re.compile(r"[+-]\s*\d+\s*$")


def _norm_offset_from_expr(expr: str) -> int:
    m = _OFFSET_RE.search(expr.replace(" ", ""))
    if not m:
        return 0
    return int(m.group(0).replace(" ", ""))


def _norm_binding(b: Binding) -> Binding:
    return b.model_copy(update={"offset": _norm_offset_from_expr(b.expr)})


_SIDE_DEFAULT = {"lhs": "lhs", "rhs": "rhs"}


def _norm_term(t: Term, side: str) -> Term:
    update: dict[str, object] = {
        "bindings": tuple(_norm_binding(b) for b in t.bindings),
        "role": _SIDE_DEFAULT.get(side, side),
    }
    coef = 1 if t.coefficient is None else t.coefficient
    sign = t.sign
    if isinstance(coef, (int, float)) and not isinstance(coef, bool) and coef < 0:
        coef = -coef
        sign = -sign
    update["coefficient"] = coef
    update["sign"] = sign
    if t.ref_kind == "literal":
        update["ref"] = "_const"
    return t.model_copy(update=update)


def canonical_normal_form(f: Formulation) -> Formulation:
    """Return ``f`` with incidental labels normalized (see module docstring)."""
    constraints = tuple(
        c.model_copy(
            update={
                "lhs": tuple(_norm_term(t, "lhs") for t in c.lhs),
                "rhs": tuple(_norm_term(t, "rhs") for t in c.rhs),
            }
        )
        for c in f.constraints
    )
    objective = None
    if f.objective is not None:
        objective = f.objective.model_copy(
            update={
                "terms": tuple(_norm_term(t, "objective") for t in f.objective.terms)
            }
        )
    return f.model_copy(update={"constraints": constraints, "objective": objective})


__all__ = ["canonical_normal_form"]
