"""JuMP (Julia) scalar models, both directions.

``to_jump`` writes a complete, runnable JuMP script (HiGHS optimizer).
``from_jump`` parses the scalar-linear macro subset back:
``@variable(model, ...)`` (bounds, ``Bin``/``Int`` flags),
``@objective(model, Max|Min, expr)``, and
``@constraint(model, [name,] expr)`` including ranged
``lb <= expr <= ub`` forms. Indexed/vectorized macros, nonlinear
expressions, and containers are outside the subset and raise
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

__all__ = ["from_jump", "to_jump"]


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def to_jump(f: Formulation, instance: Instance | None = None) -> str:
    """Emit ``f`` as a deterministic, runnable JuMP script."""
    gm = ground(f, instance)
    out: list[str] = [
        f"# lp2graph model {gm.id}",
        "using JuMP",
        "using HiGHS",
        "",
        "model = Model(HiGHS.Optimizer)",
    ]
    for v in gm.variables:
        out.append(f"@variable(model, {_var_decl(v)})")
    sense = "Max" if gm.sense == "max" else "Min"
    obj = _expr(gm.objective)
    if gm.objective_constant:
        obj = (
            f"{obj} {_signed(gm.objective_constant)}"
            if obj
            else format_number(gm.objective_constant)
        )
    out.append(f"@objective(model, {sense}, {obj or '0'})")
    cmp_ = {"le": "<=", "ge": ">=", "eq": "=="}
    for c in gm.constraints:
        out.append(
            f"@constraint(model, {c.name}, {_expr(c.terms) or '0'} {cmp_[c.comparator]} "
            f"{format_number(c.rhs)})"
        )
    out += [
        "",
        "optimize!(model)",
        'println("objective = ", objective_value(model))',
        "",
    ]
    return "\n".join(out)


def _var_decl(v: GroundedVar) -> str:
    if v.domain == "binary":
        return f"{v.name}, Bin"
    lo = 0.0 if v.domain == "non_negative" and v.lower is None else v.lower
    if lo is not None and v.upper is not None:
        decl = (
            f"{v.name} == {format_number(lo)}"
            if lo == v.upper
            else f"{format_number(lo)} <= {v.name} <= {format_number(v.upper)}"
        )
    elif lo is not None:
        decl = f"{v.name} >= {format_number(lo)}"
    elif v.upper is not None:
        decl = f"{v.name} <= {format_number(v.upper)}"
    else:
        decl = v.name
    return f"{decl}, Int" if v.domain == "integer" else decl


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

_MACRO = re.compile(r"@(?P<macro>variable|objective|constraint)\s*\(", re.IGNORECASE)
_CMP_SPLIT = re.compile(r"(<=|>=|==)")
_CMP_IN = {"<=": "le", ">=": "ge", "==": "eq"}
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def from_jump(text: str, *, model_id: str | None = None) -> Formulation:
    """Parse a scalar JuMP script into a flat canonical ``Formulation``.

    ``model_id`` overrides the id recovered from the header comment.
    """
    model_id = model_id or header_model_id(text, "jump_model")
    variables: list[GroundedVar] = []
    declared: dict[str, None] = {}
    sense: str | None = None
    obj_terms: dict[str, float] = {}
    obj_const = 0.0
    constraints: list[GroundedConstraint] = []
    anon = 0

    no_comments = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    for macro, args in _macros(no_comments):
        if macro == "variable":
            v = _parse_variable(args)
            variables.append(v)
            declared[v.name] = None
        elif macro == "objective":
            if len(args) != 3:
                raise InteropError(f"@objective expects (model, sense, expr), got {args!r}")
            if sense is not None:
                raise InteropError("multiple @objective macros are not supported")
            s = args[1].strip().lower()
            if s not in ("max", "min"):
                raise InteropError(f"unknown JuMP objective sense {args[1]!r}")
            sense = s
            obj_terms, obj_const = parse_linexpr(args[2])
        else:  # constraint
            if len(args) == 3:
                name, body = args[1].strip(), args[2]
                if not _IDENT.match(name):
                    raise InteropError(f"indexed/vector constraint {name!r} is not supported")
            elif len(args) == 2:
                anon += 1
                name, body = f"c{anon}", args[1]
            else:
                raise InteropError(f"@constraint expects (model, [name,] expr), got {args!r}")
            constraints.extend(_parse_constraint(name, body))

    if sense is None:
        raise InteropError("JuMP script declares no @objective")
    used: dict[str, None] = dict.fromkeys(obj_terms)
    for c in constraints:
        used.update(dict.fromkeys(var for _, var in c.terms))
    missing = [v for v in used if v not in declared]
    if missing:
        raise InteropError(f"variables used but never declared with @variable: {missing}")

    gm = GroundedModel(
        id=model_id,
        name=model_id,
        sense=sense,
        variables=tuple(variables),
        objective=tuple((coef, var) for var, coef in obj_terms.items() if coef != 0),
        objective_constant=obj_const,
        constraints=tuple(constraints),
    )
    return to_formulation(gm, source="JuMP")


def _macros(text: str) -> list[tuple[str, list[str]]]:
    """Find every @variable/@objective/@constraint call and split its
    arguments on top-level commas."""
    out: list[tuple[str, list[str]]] = []
    for m in _MACRO.finditer(text):
        depth = 1
        i = m.end()
        start = i
        args: list[str] = []
        while i < len(text) and depth:
            ch = text[i]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
                if depth == 0:
                    args.append(text[start:i])
            elif ch == "," and depth == 1:
                args.append(text[start:i])
                start = i + 1
            i += 1
        if depth:
            raise InteropError(f"unbalanced parentheses in @{m.group('macro')} macro")
        out.append((m.group("macro").lower(), [a.strip() for a in args]))
    return out


def _parse_variable(args: list[str]) -> GroundedVar:
    if len(args) < 2:
        raise InteropError(f"@variable expects (model, decl, ...), got {args!r}")
    decl = args[1]
    flags = {a.strip().lower() for a in args[2:]}
    unknown = flags - {"bin", "int"}
    if unknown:
        raise InteropError(f"unsupported @variable flags {sorted(unknown)!r}")
    if "[" in decl:
        raise InteropError(f"indexed @variable {decl!r} is outside the scalar subset")

    lo: float | None = None
    up: float | None = None
    parts = _CMP_SPLIT.split(decl)
    if len(parts) == 1:
        name = decl.strip()
    elif len(parts) == 3:
        a, cmp_, b = (p.strip() for p in parts)
        if _IDENT.match(a):
            name = a
            val = float(b)
            lo, up = _one_bound(cmp_, val, var_on_left=True)
        elif _IDENT.match(b):
            name = b
            val = float(a)
            lo, up = _one_bound(cmp_, val, var_on_left=False)
        else:
            raise InteropError(f"cannot parse @variable declaration {decl!r}")
    elif len(parts) == 5:  # lb <= x <= ub
        lo_text, c1, mid, c2, up_text = (p.strip() for p in parts)
        if c1 != "<=" or c2 != "<=" or not _IDENT.match(mid):
            raise InteropError(f"cannot parse @variable declaration {decl!r}")
        name, lo, up = mid, float(lo_text), float(up_text)
    else:
        raise InteropError(f"cannot parse @variable declaration {decl!r}")

    if not _IDENT.match(name):
        raise InteropError(f"cannot parse @variable declaration {decl!r}")
    if "bin" in flags:
        return GroundedVar(name=name, domain="binary", lower=0.0, upper=1.0)
    domain = "integer" if "int" in flags else "continuous"
    return GroundedVar(name=name, domain=domain, lower=lo, upper=up)


def _one_bound(cmp_: str, val: float, *, var_on_left: bool) -> tuple[float | None, float | None]:
    if cmp_ == "==":
        return val, val
    is_upper = (cmp_ == "<=") == var_on_left
    return (None, val) if is_upper else (val, None)


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
    if len(parts) == 5:  # ranged
        lb_text, c1, mid, c2, ub_text = parts
        if c1.strip() != "<=" or c2.strip() != "<=":
            raise InteropError(f"unsupported ranged constraint {name!r}: {body!r}")
        mc, mconst = parse_linexpr(mid)
        _, lb = parse_linexpr(lb_text)
        _, ub = parse_linexpr(ub_text)
        terms = tuple((coef, var) for var, coef in mc.items() if coef != 0)
        return [
            GroundedConstraint(name=f"{name}_lo", terms=terms, comparator="ge", rhs=lb - mconst),
            GroundedConstraint(name=f"{name}_up", terms=terms, comparator="le", rhs=ub - mconst),
        ]
    raise InteropError(f"cannot parse @constraint body {body!r}")
