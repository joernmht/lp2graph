"""Pyomo interface, both directions (coefficient-faithful).

- :func:`from_pyomo` reads a built ``pyomo.environ.ConcreteModel`` into a
  canonical :class:`~lp2graph.core.model.Formulation` with full linear
  term recovery (via Pyomo's ``generate_standard_repn``). This is the
  faithful, solvable counterpart of the *structural* importer
  :func:`lp2graph.mining.ingest.from_pyomo`, which preserves the
  template shell (sets, shapes, quantifiers) but not coefficients.
- :func:`to_pyomo` builds a live, solvable ``ConcreteModel`` with real
  constraint bodies (the historic :func:`lp2graph.export.to_pyomo_stub`
  emitted placeholder bodies only).
- :func:`to_pyomo_code` emits a standalone, runnable Pyomo script.

Nonlinear expressions and Pyomo features outside the grounded linear
core raise :class:`~lp2graph.interop._grounded.InteropError`.
"""

from __future__ import annotations

from typing import Any

from lp2graph.core.model import Formulation
from lp2graph.interop._grounded import (
    GroundedConstraint,
    GroundedModel,
    GroundedVar,
    InteropError,
    format_number,
    ground,
    py_linexpr,
    to_formulation,
)
from lp2graph.solve.instance import Instance

__all__ = ["from_pyomo", "to_pyomo", "to_pyomo_code"]


# ---------------------------------------------------------------------------
# ConcreteModel -> Formulation
# ---------------------------------------------------------------------------


def from_pyomo(model: Any) -> Formulation:
    """Read a built (concrete) Pyomo model, coefficient-faithfully."""
    from pyomo.core.expr.numvalue import value as pyo_value
    from pyomo.environ import Constraint, Objective, Var, maximize
    from pyomo.repn.standard_repn import generate_standard_repn

    variables: list[GroundedVar] = []
    names_by_id: dict[int, str] = {}
    for var in model.component_data_objects(Var, active=True, descend_into=True):
        name = str(var.name)
        names_by_id[id(var)] = name
        if var.is_binary():
            domain = "binary"
        elif var.is_integer():
            domain = "integer"
        elif var.is_continuous():
            domain = "continuous"
        else:
            raise InteropError(f"variable {name!r} has an unsupported domain")
        lb, ub = var.bounds
        if var.fixed:
            lb = ub = pyo_value(var.value)
        variables.append(
            GroundedVar(
                name=name,
                domain=domain,
                lower=None if lb is None else float(lb),
                upper=None if ub is None else float(ub),
            )
        )

    def linear(expr: Any, where: str) -> tuple[tuple[tuple[float, str], ...], float]:
        repn = generate_standard_repn(expr, compute_values=True, quadratic=False)
        if repn.nonlinear_expr is not None:
            raise InteropError(f"{where} has a nonlinear expression, not representable")
        terms = []
        for coef, var in zip(repn.linear_coefs, repn.linear_vars, strict=True):
            if id(var) not in names_by_id:
                raise InteropError(f"{where} references a variable outside the model")
            terms.append((float(coef), names_by_id[id(var)]))
        return tuple(terms), float(repn.constant)

    objectives = list(model.component_data_objects(Objective, active=True, descend_into=True))
    if len(objectives) != 1:
        raise InteropError(f"expected exactly one active objective, found {len(objectives)}")
    obj = objectives[0]
    obj_terms, obj_const = linear(obj.expr, f"objective {obj.name!r}")
    sense = "max" if obj.sense == maximize else "min"

    constraints: list[GroundedConstraint] = []
    for con in model.component_data_objects(Constraint, active=True, descend_into=True):
        cname = str(con.name)
        terms, const = linear(con.body, f"constraint {cname!r}")
        lo = None if con.lower is None else float(pyo_value(con.lower)) - const
        up = None if con.upper is None else float(pyo_value(con.upper)) - const
        if lo is not None and up is not None and lo == up:
            constraints.append(GroundedConstraint(name=cname, terms=terms, comparator="eq", rhs=lo))
            continue
        if lo is None and up is None:
            raise InteropError(f"constraint {cname!r} has neither a lower nor an upper bound")
        if lo is not None:
            suffix = "_lo" if up is not None else ""
            constraints.append(
                GroundedConstraint(name=cname + suffix, terms=terms, comparator="ge", rhs=lo)
            )
        if up is not None:
            suffix = "_up" if lo is not None else ""
            constraints.append(
                GroundedConstraint(name=cname + suffix, terms=terms, comparator="le", rhs=up)
            )

    name = str(getattr(model, "name", "") or "pyomo_model")
    gm = GroundedModel(
        id=name,
        name=name,
        sense=sense,
        variables=tuple(variables),
        objective=obj_terms,
        objective_constant=obj_const,
        constraints=tuple(constraints),
    )
    return to_formulation(gm, source="Pyomo")


# ---------------------------------------------------------------------------
# Formulation -> ConcreteModel
# ---------------------------------------------------------------------------


def to_pyomo(f: Formulation, instance: Instance | None = None) -> Any:
    """Build a live ``pyomo.environ.ConcreteModel`` with real bodies."""
    import pyomo.environ as pyo

    gm = ground(f, instance)
    m = pyo.ConcreteModel(name=gm.id)
    domains = {
        "binary": pyo.Binary,
        "integer": pyo.Integers,
        "non_negative": pyo.NonNegativeReals,
        "continuous": pyo.Reals,
    }
    xs: dict[str, Any] = {}
    for v in gm.variables:
        var = pyo.Var(domain=domains[v.domain], bounds=(v.lower, v.upper))
        setattr(m, v.name, var)
        xs[v.name] = var
    obj_expr = sum(coef * xs[var] for coef, var in gm.objective) + gm.objective_constant
    m.obj = pyo.Objective(expr=obj_expr, sense=pyo.maximize if gm.sense == "max" else pyo.minimize)
    for c in gm.constraints:
        body = sum(coef * xs[var] for coef, var in c.terms)
        if c.comparator == "le":
            expr = body <= c.rhs
        elif c.comparator == "ge":
            expr = body >= c.rhs
        else:
            expr = body == c.rhs
        setattr(m, c.name, pyo.Constraint(expr=expr))
    return m


def to_pyomo_code(f: Formulation, instance: Instance | None = None) -> str:
    """Emit a standalone, runnable Pyomo script for ``f``."""
    gm = ground(f, instance)
    domains = {
        "binary": "pyo.Binary",
        "integer": "pyo.Integers",
        "non_negative": "pyo.NonNegativeReals",
        "continuous": "pyo.Reals",
    }
    out: list[str] = [
        f'"""Auto-generated by lp2graph interop: model {gm.id}."""',
        "",
        "import pyomo.environ as pyo",
        "",
        "",
        "def build_model():",
        f"    m = pyo.ConcreteModel(name={gm.id!r})",
        "    v = {}",
    ]
    for v in gm.variables:
        lo = "None" if v.lower is None else format_number(v.lower)
        up = "None" if v.upper is None else format_number(v.upper)
        out.append(f"    v[{v.name!r}] = pyo.Var(domain={domains[v.domain]}, bounds=({lo}, {up}))")
        out.append(f"    m.{v.name} = v[{v.name!r}]")
    sense = "pyo.maximize" if gm.sense == "max" else "pyo.minimize"
    out.append(
        "    m.obj = pyo.Objective("
        f"expr={py_linexpr(gm.objective, gm.objective_constant)}, sense={sense})"
    )
    cmp_ = {"le": "<=", "ge": ">=", "eq": "=="}
    for c in gm.constraints:
        out.append(
            f"    m.{c.name} = pyo.Constraint(expr={py_linexpr(c.terms, 0.0)} "
            f"{cmp_[c.comparator]} {format_number(c.rhs)})"
        )
    out += [
        "    return m",
        "",
        "",
        'if __name__ == "__main__":',
        "    m = build_model()",
        '    for name in ("appsi_highs", "highs", "cbc", "glpk", "gurobi"):',
        "        solver = pyo.SolverFactory(name)",
        "        if solver.available(exception_flag=False):",
        "            solver.solve(m)",
        '            print("objective =", pyo.value(m.obj))',
        "            break",
        "    else:",
        '        raise SystemExit("no LP/MILP solver available to Pyomo")',
        "",
    ]
    return "\n".join(out)
