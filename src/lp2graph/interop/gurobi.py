"""Gurobi interface, both directions.

- :func:`from_gurobipy` reads a built ``gurobipy.Model`` into a canonical
  :class:`~lp2graph.core.model.Formulation`, coefficient-faithfully.
- :func:`to_gurobipy` builds a live ``gurobipy.Model`` from any
  formulation (flat directly; template-level with an instance).
- :func:`to_gurobipy_code` emits a standalone, runnable gurobipy script.

``gurobipy`` is imported lazily; only the two live-model functions need
it. Non-linear content (quadratic objectives/constraints, general
constraints, SOS, semi-continuous variables, multiple objectives) raises
:class:`~lp2graph.interop._grounded.InteropError` — never a silent drop.
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

__all__ = ["from_gurobipy", "to_gurobipy", "to_gurobipy_code"]

_INF = 1e29  # gurobi's GRB.INFINITY is 1e100; anything this large is "unbounded"
_SENSE_IN = {"<": "le", ">": "ge", "=": "eq"}


# ---------------------------------------------------------------------------
# gurobipy.Model -> Formulation
# ---------------------------------------------------------------------------


def from_gurobipy(model: Any) -> Formulation:
    """Read a built ``gurobipy.Model`` into a flat canonical formulation."""
    import gurobipy as gp
    from gurobipy import GRB

    if not isinstance(model, gp.Model):
        raise InteropError(f"expected gurobipy.Model, got {type(model).__name__}")
    model.update()

    for attr, what in (
        ("NumQConstrs", "quadratic constraints"),
        ("NumGenConstrs", "general constraints"),
        ("NumSOS", "SOS constraints"),
    ):
        if getattr(model, attr, 0):
            raise InteropError(f"gurobipy model uses {what}, which are not representable")
    if getattr(model, "NumObj", 1) > 1:
        raise InteropError("gurobipy model has multiple objectives, which are not representable")

    obj = model.getObjective()
    if not isinstance(obj, gp.LinExpr):
        raise InteropError("gurobipy model has a non-linear objective")

    variables: list[GroundedVar] = []
    for v in model.getVars():
        if v.VType in (GRB.SEMICONT, GRB.SEMIINT):
            raise InteropError(f"variable {v.VarName!r} is semi-continuous, not representable")
        domain = {GRB.BINARY: "binary", GRB.INTEGER: "integer", GRB.CONTINUOUS: "continuous"}[
            v.VType
        ]
        variables.append(
            GroundedVar(
                name=v.VarName,
                domain=domain,
                lower=None if v.LB <= -_INF else float(v.LB),
                upper=None if v.UB >= _INF else float(v.UB),
            )
        )

    obj_terms = tuple((float(obj.getCoeff(i)), obj.getVar(i).VarName) for i in range(obj.size()))
    constraints = tuple(
        GroundedConstraint(
            name=c.ConstrName,
            terms=tuple((float(row.getCoeff(i)), row.getVar(i).VarName) for i in range(row.size())),
            comparator=_SENSE_IN[c.Sense],
            rhs=float(c.RHS),
        )
        for c, row in ((c, model.getRow(c)) for c in model.getConstrs())
    )

    name = model.ModelName or "gurobi_model"
    gm = GroundedModel(
        id=name,
        name=name,
        sense="max" if model.ModelSense == GRB.MAXIMIZE else "min",
        variables=tuple(variables),
        objective=obj_terms,
        objective_constant=float(obj.getConstant()),
        constraints=constraints,
    )
    return to_formulation(gm, source="gurobipy")


# ---------------------------------------------------------------------------
# Formulation -> gurobipy.Model
# ---------------------------------------------------------------------------


def to_gurobipy(f: Formulation, instance: Instance | None = None, *, env: Any = None) -> Any:
    """Build a live ``gurobipy.Model`` from ``f`` (solve it with
    ``model.optimize()``). Pass ``env=gurobipy.Env(params={"OutputFlag": 0})``
    for a quiet model."""
    import gurobipy as gp
    from gurobipy import GRB

    gm = ground(f, instance)
    model = gp.Model(gm.id, env=env) if env is not None else gp.Model(gm.id)
    vtypes = {"binary": GRB.BINARY, "integer": GRB.INTEGER}
    xs: dict[str, Any] = {}
    for v in gm.variables:
        lo = 0.0 if v.domain in ("non_negative", "binary") and v.lower is None else v.lower
        xs[v.name] = model.addVar(
            lb=-GRB.INFINITY if lo is None else lo,
            ub=GRB.INFINITY if v.upper is None else v.upper,
            vtype=vtypes.get(v.domain, GRB.CONTINUOUS),
            name=v.name,
        )
    sense = GRB.MAXIMIZE if gm.sense == "max" else GRB.MINIMIZE
    model.setObjective(
        gp.quicksum(coef * xs[var] for coef, var in gm.objective) + gm.objective_constant,
        sense,
    )
    gsense = {"le": GRB.LESS_EQUAL, "ge": GRB.GREATER_EQUAL, "eq": GRB.EQUAL}
    for c in gm.constraints:
        model.addLConstr(
            gp.quicksum(coef * xs[var] for coef, var in c.terms),
            gsense[c.comparator],
            c.rhs,
            name=c.name,
        )
    model.update()
    return model


def to_gurobipy_code(f: Formulation, instance: Instance | None = None) -> str:
    """Emit a standalone, runnable gurobipy script for ``f``."""
    gm = ground(f, instance)
    out: list[str] = [
        f'"""Auto-generated by lp2graph interop: model {gm.id}."""',
        "",
        "import gurobipy as gp",
        "from gurobipy import GRB",
        "",
        "",
        "def build_model(env=None):",
        f"    m = gp.Model({gm.id!r}, env=env) if env is not None else gp.Model({gm.id!r})",
        "    v = {}",
    ]
    for v in gm.variables:
        out.append(f"    v[{v.name!r}] = m.addVar({_var_args(v)}name={v.name!r})")
    sense = "GRB.MAXIMIZE" if gm.sense == "max" else "GRB.MINIMIZE"
    out.append(f"    m.setObjective({py_linexpr(gm.objective, gm.objective_constant)}, {sense})")
    cmp_ = {"le": "<=", "ge": ">=", "eq": "=="}
    for c in gm.constraints:
        out.append(
            f"    m.addConstr({py_linexpr(c.terms, 0.0)} {cmp_[c.comparator]} "
            f"{format_number(c.rhs)}, name={c.name!r})"
        )
    out += [
        "    m.update()",
        "    return m",
        "",
        "",
        'if __name__ == "__main__":',
        "    m = build_model()",
        "    m.optimize()",
        "    if m.Status == GRB.OPTIMAL:",
        '        print("objective =", m.ObjVal)',
        "        for var in m.getVars():",
        '            print(var.VarName, "=", var.X)',
        "",
    ]
    return "\n".join(out)


def _var_args(v: GroundedVar) -> str:
    if v.domain == "binary":
        return "vtype=GRB.BINARY, "
    args = []
    if v.domain == "integer":
        args.append("vtype=GRB.INTEGER")
    lo = 0.0 if v.domain == "non_negative" and v.lower is None else v.lower
    if lo is None:
        args.append("lb=-GRB.INFINITY")
    elif lo != 0:
        args.append(f"lb={format_number(lo)}")
    if v.upper is not None:
        args.append(f"ub={format_number(v.upper)}")
    return (", ".join(args) + ", ") if args else ""
