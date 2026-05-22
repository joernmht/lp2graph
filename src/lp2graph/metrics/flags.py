"""Presence flags computed directly from the canonical model.

Each flag is a boolean property of the formulation. They are cheap,
exact, and do not require any view derivation.

Adapted from joernmht/raiLPminerExperimentation
(railpminer/analysis/milp_detection.py), MIT License.
"""

from __future__ import annotations

from lp2graph.core.model import Formulation
from lp2graph.metrics.result import MetricResult


def has_big_m(f: Formulation) -> MetricResult:
    """True if any parameter has kind ``big_m`` or any constraint has kind ``big_m``."""
    by_param = any(p.kind == "big_m" for p in f.parameters)
    by_const = any(c.kind == "big_m" for c in f.constraints)
    return MetricResult(
        name="has_big_m",
        value=by_param or by_const,
        explanation="A big-M parameter or big-M constraint is present.",
        data={"by_parameter": by_param, "by_constraint": by_const},
    )


def has_integer_vars(f: Formulation) -> MetricResult:
    """True if any variable template is integer or binary."""
    v = any(v.domain in ("integer", "binary") for v in f.variables)
    return MetricResult(
        name="has_integer_vars",
        value=v,
        explanation="At least one integer or binary variable.",
    )


def has_modulo_offset(f: Formulation) -> MetricResult:
    """True if any term binding declares a modulo wrap.

    Indicates a PESP-style cyclic formulation. Cyclic indices alone do
    not trigger this flag — the binding has to use the modulo.
    """
    for c in f.constraints:
        for term in (*c.lhs, *c.rhs):
            if any(b.modulo for b in term.bindings):
                return MetricResult(
                    name="has_modulo_offset",
                    value=True,
                    explanation="At least one term binding wraps modulo an index.",
                )
    if f.objective is not None:
        for term in f.objective.terms:
            if any(b.modulo for b in term.bindings):
                return MetricResult(
                    name="has_modulo_offset",
                    value=True,
                    explanation="Objective term binding wraps modulo an index.",
                )
    return MetricResult(name="has_modulo_offset", value=False, explanation="No modulo bindings.")


def has_soft_slack(f: Formulation) -> MetricResult:
    """True if any variable has role ``slack`` or any term has role ``slack``."""
    by_var = any(v.role == "slack" for v in f.variables)
    by_term = any(
        any(t.role == "slack" for t in (*c.lhs, *c.rhs))
        for c in f.constraints
    )
    by_obj = bool(f.objective) and any(t.role == "slack" for t in f.objective.terms)  # type: ignore[union-attr]
    return MetricResult(
        name="has_soft_slack",
        value=by_var or by_term or by_obj,
        explanation="Slack variable or slack-role term is present.",
        data={"by_variable": by_var, "by_term": by_term, "by_objective": by_obj},
    )


def has_aggregation_operator(f: Formulation) -> MetricResult:
    """True if any term uses an operator (sum/max/min/abs/indicator/modulo)."""
    for c in f.constraints:
        for term in (*c.lhs, *c.rhs):
            if term.operator != "none":
                return MetricResult(
                    name="has_aggregation_operator",
                    value=True,
                    explanation=f"Operator {term.operator!r} present in {c.name!r}.",
                )
    if f.objective is not None:
        for term in f.objective.terms:
            if term.operator != "none":
                return MetricResult(
                    name="has_aggregation_operator",
                    value=True,
                    explanation=f"Operator {term.operator!r} present in objective.",
                )
    return MetricResult(
        name="has_aggregation_operator",
        value=False,
        explanation="No aggregation operators.",
    )


def presence_flags(f: Formulation) -> dict[str, MetricResult]:
    """Compute every presence flag in a single pass."""
    return {
        m.name: m
        for m in (
            has_big_m(f),
            has_integer_vars(f),
            has_modulo_offset(f),
            has_soft_slack(f),
            has_aggregation_operator(f),
        )
    }


__all__ = [
    "has_aggregation_operator",
    "has_big_m",
    "has_integer_vars",
    "has_modulo_offset",
    "has_soft_slack",
    "presence_flags",
]
