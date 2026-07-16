"""AMPL scalar models (.mod), both directions.

``to_ampl`` writes a scalar AMPL model file. ``from_ampl`` parses that
scalar-linear subset back: ``var`` declarations with ``binary`` /
``integer`` / bound attributes, one ``maximize``/``minimize``
declaration, and ``subject to`` constraints (including ranged
``lb <= expr <= ub``, which splits into two constraints). ``set`` /
``param`` / indexed declarations are outside the subset and raise
:class:`~lp2graph.interop._grounded.InteropError`.
"""

from __future__ import annotations

import re

from lp2graph.core.model import Formulation
from lp2graph.interop._grounded import (
    GroundedConstraint,
    GroundedModel,
    GroundedVar,
    InteropError,
    format_number,
    ground,
    header_model_id,
    to_formulation,
)
from lp2graph.interop._linexpr import parse_linexpr
from lp2graph.solve.instance import Instance

__all__ = ["from_ampl", "to_ampl"]


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def to_ampl(f: Formulation, instance: Instance | None = None) -> str:
    """Emit ``f`` as a deterministic scalar AMPL model."""
    gm = ground(f, instance)
    out: list[str] = [f"# lp2graph model {gm.id}"]
    for v in gm.variables:
        out.append(f"var {v.name}{_var_attrs(v)};")
    sense = "maximize" if gm.sense == "max" else "minimize"
    obj = _expr(gm.objective)
    if gm.objective_constant:
        obj = (
            f"{obj} {_signed(gm.objective_constant)}"
            if obj
            else format_number(gm.objective_constant)
        )
    out.append(f"{sense} obj: {obj or '0'};")
    cmp_ = {"le": "<=", "ge": ">=", "eq": "="}
    for c in gm.constraints:
        out.append(
            f"subject to {c.name}: {_expr(c.terms) or '0'} {cmp_[c.comparator]} "
            f"{format_number(c.rhs)};"
        )
    return "\n".join(out) + "\n"


def _var_attrs(v: GroundedVar) -> str:
    if v.domain == "binary":
        return " binary"
    attrs: list[str] = []
    if v.domain == "integer":
        attrs.append("integer")
    lo = 0.0 if v.domain == "non_negative" and v.lower is None else v.lower
    if lo is not None and v.upper is not None and lo == v.upper:
        attrs.append(f"= {format_number(lo)}")
    else:
        if lo is not None:
            attrs.append(f">= {format_number(lo)}")
        if v.upper is not None:
            attrs.append(f"<= {format_number(v.upper)}")
    return (" " + ", ".join(attrs)) if attrs else ""


def _expr(terms: tuple[tuple[float, str], ...]) -> str:
    parts: list[str] = []
    for coef, var in terms:
        mag = abs(coef)
        piece = var if mag == 1 else f"{format_number(mag)}*{var}"
        if not parts:
            parts.append(f"-{piece}" if coef < 0 else piece)
        else:
            parts.append(f"{'-' if coef < 0 else '+'} {piece}")
    return " ".join(parts)


def _signed(x: float) -> str:
    return f"{'-' if x < 0 else '+'} {format_number(abs(x))}"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_VAR = re.compile(r"^var\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<attrs>.*)$", re.DOTALL)
_OBJ = re.compile(
    r"^(?P<sense>maximize|minimize)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<body>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_CON = re.compile(
    r"^(?:subject\s+to|s\.t\.|st)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<body>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_CMP_SPLIT = re.compile(r"(<=|>=|==|=|<|>)")
_CMP_IN = {"<=": "le", "<": "le", ">=": "ge", ">": "ge", "=": "eq", "==": "eq"}


def from_ampl(text: str, *, model_id: str | None = None) -> Formulation:
    """Parse a scalar AMPL model into a flat canonical ``Formulation``.

    ``model_id`` overrides the id recovered from the header comment.
    """
    model_id = model_id or header_model_id(text, "ampl_model")
    variables: list[GroundedVar] = []
    declared: dict[str, None] = {}
    sense: str | None = None
    obj_terms: dict[str, float] = {}
    obj_const = 0.0
    constraints: list[GroundedConstraint] = []

    for stmt in _statements(text):
        low = stmt.lower()
        if low.startswith(("set", "param", "data", "model", "option", "solve", "display")):
            if low.startswith(("set", "param")):
                raise InteropError(
                    "AMPL set/param declarations are outside the scalar subset "
                    f"lp2graph parses: {stmt[:60]!r}"
                )
            continue
        m = _VAR.match(stmt)
        if m:
            name = m.group("name")
            if "{" in stmt:
                raise InteropError(f"indexed var {name!r} is outside the scalar subset")
            variables.append(_parse_var(name, m.group("attrs")))
            declared[name] = None
            continue
        m = _OBJ.match(stmt)
        if m:
            if sense is not None:
                raise InteropError("multiple objectives are not supported")
            sense = "max" if m.group("sense").lower() == "maximize" else "min"
            coefs, obj_const = parse_linexpr(m.group("body"))
            obj_terms = coefs
            continue
        m = _CON.match(stmt)
        if m:
            constraints.extend(_parse_constraint(m.group("name"), m.group("body")))
            continue
        raise InteropError(f"cannot parse AMPL statement: {stmt[:80]!r}")

    if sense is None:
        raise InteropError("AMPL model declares no maximize/minimize objective")
    used: dict[str, None] = dict.fromkeys(obj_terms)
    for c in constraints:
        used.update(dict.fromkeys(var for _, var in c.terms))
    missing = [v for v in used if v not in declared]
    if missing:
        raise InteropError(f"variables used but never declared: {missing}")

    gm = GroundedModel(
        id=model_id,
        name=model_id,
        sense=sense,
        variables=tuple(variables),
        objective=tuple((coef, var) for var, coef in obj_terms.items() if coef != 0),
        objective_constant=obj_const,
        constraints=tuple(constraints),
    )
    return to_formulation(gm, source="AMPL")


def _statements(text: str) -> list[str]:
    no_comments = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    return [s.strip() for s in no_comments.split(";") if s.strip()]


def _parse_var(name: str, attrs: str) -> GroundedVar:
    domain = "continuous"
    lo: float | None = None
    up: float | None = None
    for attr in (a.strip() for a in attrs.split(",") if a.strip()):
        low = attr.lower()
        if low == "binary":
            domain = "binary"
        elif low == "integer":
            domain = "integer"
        elif low.startswith(">="):
            lo = float(attr[2:])
        elif low.startswith("<="):
            up = float(attr[2:])
        elif low.startswith(":="):
            continue  # initial value, irrelevant to the formulation
        elif low.startswith("="):
            lo = up = float(attr[1:])
        else:
            raise InteropError(f"unsupported attribute {attr!r} on var {name!r}")
    if domain == "binary":
        return GroundedVar(name=name, domain="binary", lower=0.0, upper=1.0)
    if domain == "integer" and lo is None:
        lo = None  # AMPL integers default to free; keep it explicit
    return GroundedVar(name=name, domain=domain, lower=lo, upper=up)


def _parse_constraint(name: str, body: str) -> list[GroundedConstraint]:
    parts = _CMP_SPLIT.split(body)
    if len(parts) == 3:
        lhs, cmp_, rhs = parts
        lc, lconst = parse_linexpr(lhs)
        rc, rconst = parse_linexpr(rhs)
        for var, coef in rc.items():
            lc[var] = lc.get(var, 0.0) - coef
        return [
            GroundedConstraint(
                name=name,
                terms=tuple((coef, var) for var, coef in lc.items() if coef != 0),
                comparator=_CMP_IN[cmp_],
                rhs=rconst - lconst,
            )
        ]
    if len(parts) == 5:  # ranged: lb <= expr <= ub
        lb_text, c1, mid, c2, ub_text = parts
        if _CMP_IN[c1] != "le" or _CMP_IN[c2] != "le":
            raise InteropError(f"unsupported ranged constraint {name!r}: {body!r}")
        mc, mconst = parse_linexpr(mid)
        _, lb = parse_linexpr(lb_text)
        _, ub = parse_linexpr(ub_text)
        terms = tuple((coef, var) for var, coef in mc.items() if coef != 0)
        return [
            GroundedConstraint(name=f"{name}_lo", terms=terms, comparator="ge", rhs=lb - mconst),
            GroundedConstraint(name=f"{name}_up", terms=terms, comparator="le", rhs=ub - mconst),
        ]
    raise InteropError(f"constraint {name!r} is not 'expr <cmp> expr': {body!r}")
