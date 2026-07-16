"""Pyomo export — generates a model skeleton (stub for v0.1).

Emits a Python module string that, when executed, defines a Pyomo
``ConcreteModel`` with sets, parameters, variables, the objective, and
constraint declarations. The constraint *bodies* are emitted as
docstring placeholders for v0.1; full body translation lands in v1.0.

This is a deliberate v0.1 scope choice — see issue
``open-question/solver-language-export-scope`` and the v1 acceptance
criteria.

The *functional* Pyomo exporters live in :mod:`lp2graph.interop`:
:func:`lp2graph.interop.to_pyomo` builds a live ``ConcreteModel`` with
real constraint bodies and :func:`lp2graph.interop.to_pyomo_code` emits
a runnable script. This template-level skeleton is kept for callers
that want the schema shape (sets/params/quantifiers) rather than a
grounded model.
"""

from __future__ import annotations

from lp2graph.core.model import Formulation


def to_pyomo_stub(f: Formulation) -> str:
    """Generate a Pyomo skeleton string from a formulation."""
    lines: list[str] = []
    lines.append('"""Auto-generated Pyomo skeleton from lp2graph.')
    lines.append("")
    lines.append(f"Formulation: {f.id}  ({f.name})")
    lines.append(f"Family:      {f.family}")
    lines.append('"""')
    lines.append("from pyomo.environ import (")
    lines.append("    ConcreteModel, Set, Param, Var, Constraint, Objective,")
    lines.append("    NonNegativeReals, Reals, Integers, Binary, minimize, maximize,")
    lines.append(")")
    lines.append("")
    lines.append("def build_model() -> ConcreteModel:")
    lines.append("    m = ConcreteModel()")
    for idx in f.indices:
        lines.append(f"    m.{idx.name} = Set()  # ordered={idx.ordered}, cyclic={idx.cyclic}")
    for p in f.parameters:
        if p.shape:
            sets = ", ".join(f"m.{s}" for s in p.shape)
            lines.append(f"    m.{p.name} = Param({sets}, mutable=True)")
        else:
            lines.append(f"    m.{p.name} = Param(mutable=True)")
    for v in f.variables:
        domain = {
            "continuous": "Reals",
            "non_negative": "NonNegativeReals",
            "integer": "Integers",
            "binary": "Binary",
        }[v.domain]
        bounds = ""
        if v.lower is not None or v.upper is not None:
            bounds = f", bounds=({v.lower!r}, {v.upper!r})"
        if v.shape:
            sets = ", ".join(f"m.{s}" for s in v.shape)
            lines.append(f"    m.{v.name} = Var({sets}, domain={domain}{bounds})")
        else:
            lines.append(f"    m.{v.name} = Var(domain={domain}{bounds})")
    if f.objective is not None:
        sense = "minimize" if f.objective.sense == "min" else "maximize"
        lines.append("")
        lines.append("    def _obj_rule(m):")
        lines.append(f'        """{f.objective.description or "Objective"}."""')
        lines.append("        raise NotImplementedError('lp2graph v0.1 emits stubs only')")
        lines.append(f"    m.obj = Objective(rule=_obj_rule, sense={sense})")
    for c in f.constraints:
        lines.append("")
        sets_args = ""
        if c.quantifiers:
            sets_args = ", " + ", ".join(f"m.{q.over}" for q in c.quantifiers)
            arg_names = ", ".join(q.index for q in c.quantifiers)
            lines.append(f"    def _{c.name}_rule(m, {arg_names}):")
        else:
            lines.append(f"    def _{c.name}_rule(m):")
        lines.append(f'        """{c.description or c.name}."""')
        lines.append("        raise NotImplementedError('lp2graph v0.1 emits stubs only')")
        lines.append(f"    m.{c.name} = Constraint(rule=_{c.name}_rule{sets_args})")
    lines.append("")
    lines.append("    return m")
    lines.append("")
    return "\n".join(lines)


__all__ = ["to_pyomo_stub"]
