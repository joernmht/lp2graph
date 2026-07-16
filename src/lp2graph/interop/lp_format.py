"""CPLEX/Gurobi LP file format, both directions.

``to_lp_string`` writes a deterministic LP file from any formulation
(flat directly; template-level through the grounder with an instance).
``from_lp_string`` parses the linear subset the mainstream writers
(CPLEX, Gurobi, PuLP, and this module) produce: objective, constraints,
bounds, general/binary sections. SOS, semi-continuous, and quadratic
sections raise :class:`~lp2graph.interop._grounded.InteropError`.
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

__all__ = ["from_lp_string", "to_lp_string"]

_CMP_OUT = {"le": "<=", "ge": ">=", "eq": "="}
_CMP_IN = {"<=": "le", "<": "le", "=<": "le", ">=": "ge", ">": "ge", "=>": "ge", "=": "eq"}


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def to_lp_string(f: Formulation, instance: Instance | None = None) -> str:
    """Emit ``f`` as a deterministic CPLEX-LP-format string."""
    gm = ground(f, instance)
    out: list[str] = [f"\\ lp2graph model {gm.id}"]
    out.append("Maximize" if gm.sense == "max" else "Minimize")
    obj = _expr(gm.objective)
    if gm.objective_constant:
        const = gm.objective_constant
        obj = f"{obj} {_signed(const)}" if obj else format_number(const)
    out.append(f" obj: {obj or '0'}")
    out.append("Subject To")
    for c in gm.constraints:
        out.append(
            f" {c.name}: {_expr(c.terms) or '0'} {_CMP_OUT[c.comparator]} {format_number(c.rhs)}"
        )
    bounds = [_bound_line(v) for v in gm.variables]
    bounds = [b for b in bounds if b]
    if bounds:
        out.append("Bounds")
        out.extend(bounds)
    generals = [v.name for v in gm.variables if v.domain == "integer"]
    if generals:
        out.append("Generals")
        out.extend(f" {n}" for n in generals)
    binaries = [v.name for v in gm.variables if v.domain == "binary"]
    if binaries:
        out.append("Binaries")
        out.extend(f" {n}" for n in binaries)
    out.append("End")
    return "\n".join(out) + "\n"


def _expr(terms: tuple[tuple[float, str], ...]) -> str:
    parts: list[str] = []
    for coef, var in terms:
        if not parts:
            lead = "-" if coef < 0 else ""
            parts.append(f"{lead}{_coef(abs(coef))}{var}")
        else:
            parts.append(f"{'-' if coef < 0 else '+'} {_coef(abs(coef))}{var}")
    return " ".join(parts)


def _coef(c: float) -> str:
    return "" if c == 1 else f"{format_number(c)} "


def _signed(x: float) -> str:
    return f"{'-' if x < 0 else '+'} {format_number(abs(x))}"


def _bound_line(v: GroundedVar) -> str:
    if v.domain == "binary":
        return ""
    lo, up = v.lower, v.upper
    if v.domain in ("non_negative", "integer") and lo is None:
        lo = 0.0
    if lo is not None and up is not None:
        if lo == up:
            return f" {v.name} = {format_number(lo)}"
        return f" {format_number(lo)} <= {v.name} <= {format_number(up)}"
    if lo is None and up is None:
        return f" {v.name} free" if v.domain == "continuous" else ""
    if up is not None:  # lower is -inf
        return f" -infinity <= {v.name} <= {format_number(up)}"
    assert lo is not None  # every other bound shape returned above
    if lo == 0:
        return ""  # LP-format default bound
    return f" {v.name} >= {format_number(lo)}"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_SECTIONS: dict[str, str] = {
    "maximize": "objective_max",
    "maximise": "objective_max",
    "max": "objective_max",
    "maximum": "objective_max",
    "minimize": "objective_min",
    "minimise": "objective_min",
    "min": "objective_min",
    "minimum": "objective_min",
    "subject to": "constraints",
    "such that": "constraints",
    "st": "constraints",
    "s.t.": "constraints",
    "st.": "constraints",
    "bounds": "bounds",
    "bound": "bounds",
    "generals": "integer",
    "general": "integer",
    "gen": "integer",
    "integers": "integer",
    "integer": "integer",
    "binaries": "binary",
    "binary": "binary",
    "bin": "binary",
    "semi-continuous": "unsupported",
    "semis": "unsupported",
    "semi": "unsupported",
    "sos": "unsupported",
    "end": "end",
}

_LABEL = re.compile(r"^\s*([A-Za-z0-9_\.\[\]\(\),#\$%&/]+)\s*:")
_CMP_SPLIT = re.compile(r"(<=|>=|=<|=>|<|>|=)")
_INF = {"inf", "+inf", "-inf", "infinity", "+infinity", "-infinity", "1e30", "-1e30"}


def from_lp_string(text: str, *, model_id: str | None = None) -> Formulation:
    """Parse an LP-format string into a flat canonical ``Formulation``.

    ``model_id`` overrides the id recovered from the header comment.
    """
    model_id = model_id or header_model_id(text, "lp_model")
    sections = _split_sections(text)
    sense = "max" if "objective_max" in sections else "min"
    obj_text = sections.get("objective_max", sections.get("objective_min", ""))
    obj_text = _LABEL.sub("", obj_text.strip(), count=1)
    obj_coefs, obj_const = parse_linexpr(obj_text)

    constraints: list[GroundedConstraint] = []
    order: dict[str, None] = dict.fromkeys(obj_coefs)
    for k, (name, body) in enumerate(_constraint_chunks(sections.get("constraints", ""))):
        parts = _CMP_SPLIT.split(body)
        if len(parts) != 3:
            raise InteropError(f"constraint {name or k + 1} is not 'expr <cmp> expr': {body!r}")
        lhs_coefs, lhs_const = parse_linexpr(parts[0])
        rhs_coefs, rhs_const = parse_linexpr(parts[2])
        for var, coef in rhs_coefs.items():
            lhs_coefs[var] = lhs_coefs.get(var, 0.0) - coef
        order.update(dict.fromkeys(lhs_coefs))
        constraints.append(
            GroundedConstraint(
                name=name or f"c{k + 1}",
                terms=tuple((coef, var) for var, coef in lhs_coefs.items() if coef != 0),
                comparator=_CMP_IN[parts[1]],
                rhs=rhs_const - lhs_const,
            )
        )

    integers = set(sections.get("integer", "").split())
    binaries = set(sections.get("binary", "").split())
    bounds = _parse_bounds(sections.get("bounds", ""))
    order.update(dict.fromkeys(sorted(integers | binaries | set(bounds) - set(order))))

    variables = []
    for var in order:
        lo, up = bounds.get(var, (0.0, None))
        if var in binaries:
            variables.append(GroundedVar(name=var, domain="binary", lower=0.0, upper=1.0))
        elif var in integers:
            variables.append(GroundedVar(name=var, domain="integer", lower=lo, upper=up))
        else:
            variables.append(GroundedVar(name=var, domain="continuous", lower=lo, upper=up))

    gm = GroundedModel(
        id=model_id,
        name=model_id,
        sense=sense,
        variables=tuple(variables),
        objective=tuple((coef, var) for var, coef in obj_coefs.items() if coef != 0),
        objective_constant=obj_const,
        constraints=tuple(constraints),
    )
    return to_formulation(gm, source="LP format")


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("\\", 1)[0] for line in text.splitlines())


def _split_sections(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in _strip_comments(text).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        key = _section_key(stripped)
        if key is not None:
            if current is not None:
                out[current] = "\n".join(buf)
            if key == "unsupported":
                raise InteropError(
                    f"LP section {stripped.split()[0]!r} (SOS/semi-continuous) is not supported"
                )
            if key == "end":
                current, buf = None, []
                break
            current, buf = key, []
            rest = _section_rest(stripped)
            if rest:
                buf.append(rest)
        elif current is not None:
            buf.append(stripped)
        else:
            raise InteropError(f"unexpected line before objective section: {stripped!r}")
    if current is not None:
        out[current] = "\n".join(buf)
    return out


def _section_key(stripped: str) -> str | None:
    low = stripped.lower()
    for kw in sorted(_SECTIONS, key=len, reverse=True):
        if low == kw or low.startswith(kw + " ") or low.startswith(kw + "\t"):
            return _SECTIONS[kw]
    return None


def _section_rest(stripped: str) -> str:
    low = stripped.lower()
    for kw in sorted(_SECTIONS, key=len, reverse=True):
        if low == kw:
            return ""
        if low.startswith(kw + " ") or low.startswith(kw + "\t"):
            return stripped[len(kw) :].strip()
    return ""


def _constraint_chunks(text: str) -> list[tuple[str, str]]:
    """Split the constraints section into (label, body) chunks.

    Labeled constraints may wrap across lines; an unlabeled line that is
    not a continuation starts an anonymous constraint.
    """
    chunks: list[tuple[str, str]] = []
    for line in text.splitlines():
        m = _LABEL.match(line)
        if m:
            chunks.append((m.group(1), line[m.end() :].strip()))
        elif chunks and not _CMP_SPLIT.search(chunks[-1][1]):
            chunks[-1] = (chunks[-1][0], chunks[-1][1] + " " + line.strip())
        elif line.strip():
            chunks.append(("", line.strip()))
    return [(name, body) for name, body in chunks if body]


def _parse_bounds(text: str) -> dict[str, tuple[float | None, float | None]]:
    out: dict[str, tuple[float | None, float | None]] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        toks = stripped.split()
        if len(toks) == 2 and toks[1].lower() == "free":
            out[toks[0]] = (None, None)
            continue
        parts = _CMP_SPLIT.split(stripped.replace(" ", ""))
        if len(parts) == 5:  # lb <= x <= ub
            lo, var, up = _num(parts[0]), parts[2], _num(parts[4])
            if parts[1] not in ("<=", "<") or parts[3] not in ("<=", "<"):
                raise InteropError(f"unsupported bound line: {stripped!r}")
            out[var] = (lo, up)
        elif len(parts) == 3:
            a, cmp_, b = parts
            if _is_num(a) and not _is_num(b):  # const cmp var
                a, cmp_, b = b, _flip(cmp_), a
            if not _is_num(b):
                raise InteropError(f"unsupported bound line: {stripped!r}")
            prev = out.get(a, (0.0, None))
            if cmp_ in ("<=", "<"):
                out[a] = (prev[0], _num(b))
            elif cmp_ in (">=", ">"):
                out[a] = (_num(b), prev[1])
            else:  # fixed
                out[a] = (_num(b), _num(b))
        else:
            raise InteropError(f"unsupported bound line: {stripped!r}")
    return out


def _flip(cmp_: str) -> str:
    return {"<=": ">=", "<": ">", ">=": "<=", ">": "<", "=": "="}[cmp_]


def _is_num(tok: str) -> bool:
    if tok.lower() in _INF:
        return True
    try:
        float(tok)
        return True
    except ValueError:
        return False


def _num(tok: str) -> float | None:
    """A bound token as a float; infinities map to None (unbounded)."""
    if tok.lower() in _INF:
        return None
    return float(tok)
