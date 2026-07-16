"""GAMS scalar models, both directions.

``to_gams`` writes a complete, runnable scalar GAMS program (objective
variable + defining equation + ``Solve`` statement). ``from_gams``
parses that scalar-linear subset back: variable declarations
(``Variables`` / ``Positive`` / ``Binary`` / ``Integer`` / ``Free``),
bound assignments (``x.lo`` / ``x.up`` / ``x.fx``), equation definitions
(``name .. expr =e=/=l=/=g= expr``), and the ``Solve`` statement, from
which the objective variable is identified and substituted out. Sets,
parameters, indexed equations, and ``$`` conditions are outside the
subset and raise :class:`~lp2graph.interop._grounded.InteropError`.
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
    to_formulation,
)
from lp2graph.interop._linexpr import parse_linexpr
from lp2graph.solve.instance import Instance

__all__ = ["from_gams", "to_gams"]

_REL_OUT = {"le": "=l=", "ge": "=g=", "eq": "=e="}
_REL_IN = {"=l=": "le", "=g=": "ge", "=e=": "eq"}


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def to_gams(f: Formulation, instance: Instance | None = None) -> str:
    """Emit ``f`` as a deterministic, runnable scalar GAMS program."""
    gm = ground(f, instance)
    zname = _fresh("z", {v.name for v in gm.variables})
    out: list[str] = [f"* lp2graph model {gm.id}"]

    frees = [v.name for v in gm.variables if v.domain == "continuous"]
    out.append(f"Variables {', '.join([zname, *frees])};")
    for kw, dom in (("Positive", "non_negative"), ("Binary", "binary"), ("Integer", "integer")):
        names = [v.name for v in gm.variables if v.domain == dom]
        if names:
            out.append(f"{kw} Variables {', '.join(names)};")
    for v in gm.variables:
        if v.domain == "binary":
            continue
        default_lo = 0.0 if v.domain in ("non_negative", "integer") else None
        if v.lower is not None and v.upper is not None and v.lower == v.upper:
            out.append(f"{v.name}.fx = {format_number(v.lower)};")
            continue
        if v.lower is not None and v.lower != default_lo:
            out.append(f"{v.name}.lo = {format_number(v.lower)};")
        if v.upper is not None:
            out.append(f"{v.name}.up = {format_number(v.upper)};")

    eqnames = ["defobj", *(c.name for c in gm.constraints)]
    out.append(f"Equations {', '.join(eqnames)};")
    obj = _expr(gm.objective)
    if gm.objective_constant:
        obj = (
            f"{obj} {_signed(gm.objective_constant)}"
            if obj
            else format_number(gm.objective_constant)
        )
    out.append(f"defobj .. {zname} =e= {obj or '0'};")
    for c in gm.constraints:
        out.append(
            f"{c.name} .. {_expr(c.terms) or '0'} {_REL_OUT[c.comparator]} {format_number(c.rhs)};"
        )

    kind = "mip" if any(v.domain in ("integer", "binary") for v in gm.variables) else "lp"
    direction = "maximizing" if gm.sense == "max" else "minimizing"
    out.append(f"Model {_model_name(gm.id)} / all /;")
    out.append(f"Solve {_model_name(gm.id)} using {kind} {direction} {zname};")
    return "\n".join(out) + "\n"


def _model_name(model_id: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", model_id)
    return name if name and not name[0].isdigit() else f"m_{name}"


def _fresh(base: str, used: set[str]) -> str:
    cand, n = base, 2
    while cand in used:
        cand = f"{base}{n}"
        n += 1
    return cand


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

_DECL = re.compile(
    r"^(?:(?P<kind>positive|negative|binary|integer|free)\s+)?variables?\s+(?P<names>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_EQDEF = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\.\.\s*(?P<body>.*)$", re.DOTALL)
_BOUND = re.compile(
    r"^(?P<var>[A-Za-z_][A-Za-z0-9_]*)\.(?P<attr>lo|up|fx|l|m)\s*=\s*(?P<val>[^=]+)$",
    re.IGNORECASE,
)
_SOLVE = re.compile(
    r"^solve\s+(?P<model>\S+)\s+using\s+(?P<kind>\w+)\s+(?P<dir>maximizing|minimizing)\s+"
    r"(?P<obj>[A-Za-z_][A-Za-z0-9_]*)$",
    re.IGNORECASE,
)
_REL_SPLIT = re.compile(r"(=[elg]=)", re.IGNORECASE)


def from_gams(text: str, *, model_id: str | None = None) -> Formulation:
    """Parse a scalar GAMS program into a flat canonical ``Formulation``.

    ``model_id`` overrides the name recovered from the ``Solve`` statement.
    """
    domains: dict[str, str] = {}
    bounds: dict[str, dict[str, float]] = {}
    equations: list[tuple[str, str]] = []
    sense: str | None = None
    obj_var: str | None = None
    solved_model: str | None = None

    for stmt in _statements(text):
        low = stmt.lower()
        if low.startswith("equations") or low.startswith("equation "):
            continue  # declaration only; definitions carry the content
        if low.startswith(("model ", "model/")):
            continue
        if low.startswith(("set", "parameter", "scalar", "table", "alias")):
            raise InteropError(
                "GAMS sets/parameters/tables are outside the scalar subset "
                f"lp2graph parses: {stmt[:60]!r}"
            )
        m = _SOLVE.match(stmt)
        if m:
            sense = "max" if m.group("dir").lower() == "maximizing" else "min"
            obj_var = m.group("obj")
            solved_model = m.group("model")
            continue
        m = _EQDEF.match(stmt)
        if m:
            equations.append((m.group("name"), m.group("body")))
            continue
        m = _BOUND.match(stmt)
        if m:
            attr = m.group("attr").lower()
            if attr in ("lo", "up", "fx"):
                bounds.setdefault(m.group("var"), {})[attr] = float(m.group("val"))
            continue
        m = _DECL.match(stmt)
        if m:
            kind = (m.group("kind") or "free").lower()
            if kind == "negative":
                raise InteropError("GAMS 'Negative Variables' are not supported")
            for name in _decl_names(m.group("names")):
                domains[name] = kind
            continue
        if low.startswith(("display", "option", "$")):
            continue
        raise InteropError(f"cannot parse GAMS statement: {stmt[:80]!r}")

    if sense is None or obj_var is None:
        raise InteropError("GAMS program has no 'Solve ... maximizing/minimizing z' statement")
    if obj_var not in domains:
        raise InteropError(f"objective variable {obj_var!r} is not declared")

    obj_terms: dict[str, float] | None = None
    obj_const = 0.0
    constraints: list[GroundedConstraint] = []
    order: dict[str, None] = {}
    for name, body in equations:
        parts = _REL_SPLIT.split(body)
        if len(parts) != 3:
            raise InteropError(f"equation {name!r} is not 'expr =rel= expr': {body!r}")
        lhs, rel, rhs = parts
        lc, lconst = parse_linexpr(lhs)
        rc, rconst = parse_linexpr(rhs)
        for var, coef in rc.items():
            lc[var] = lc.get(var, 0.0) - coef
        const = rconst - lconst
        z = lc.pop(obj_var, 0.0)
        if z:
            if rel.lower() != "=e=" or obj_terms is not None:
                raise InteropError(
                    f"objective variable {obj_var!r} must appear in exactly one "
                    "'=e=' defining equation"
                )
            # z*coef + expr = const  ->  z = (const - expr) / coef
            obj_terms = {var: -coef / z for var, coef in lc.items()}
            obj_const = const / z
            order.update(dict.fromkeys(obj_terms))
            continue
        order.update(dict.fromkeys(lc))
        constraints.append(
            GroundedConstraint(
                name=name,
                terms=tuple((coef, var) for var, coef in lc.items() if coef != 0),
                comparator=_REL_IN[rel.lower()],
                rhs=const,
            )
        )
    if obj_terms is None:
        raise InteropError(f"no defining equation found for objective variable {obj_var!r}")

    order.update(dict.fromkeys(n for n in domains if n != obj_var))
    variables = []
    for name in order:
        if name not in domains:
            raise InteropError(f"variable {name!r} is used but never declared")
        variables.append(_make_var(name, domains[name], bounds.get(name, {})))

    mid = model_id or solved_model or "gams_model"
    gm = GroundedModel(
        id=mid,
        name=mid,
        sense=sense,
        variables=tuple(variables),
        objective=tuple((coef, var) for var, coef in obj_terms.items() if coef != 0),
        objective_constant=obj_const,
        constraints=tuple(constraints),
    )
    return to_formulation(gm, source="GAMS")


def _statements(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        if line.startswith("*"):
            continue
        lines.append(line)
    joined = "\n".join(lines)
    joined = re.sub(r"['\"][^'\"]*['\"]", "", joined)  # strip descriptive strings
    return [s.strip() for s in joined.split(";") if s.strip()]


def _decl_names(blob: str) -> list[str]:
    names = []
    for part in re.split(r"[,\n]", blob):
        toks = part.strip().split()
        if toks:
            names.append(toks[0])  # trailing words are descriptions
    return names


def _make_var(name: str, kind: str, b: dict[str, float]) -> GroundedVar:
    if "fx" in b:
        lo: float | None = b["fx"]
        up: float | None = b["fx"]
    else:
        default_lo = 0.0 if kind in ("positive", "binary", "integer") else None
        lo = b.get("lo", default_lo)
        up = b.get("up", 1.0 if kind == "binary" else None)
    domain = {"binary": "binary", "integer": "integer"}.get(kind, "continuous")
    return GroundedVar(name=name, domain=domain, lower=lo, upper=up)
