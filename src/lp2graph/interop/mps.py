"""MPS file format, both directions (free-format, pure Python).

``to_mps_string`` writes a deterministic free-format MPS file including
``OBJSENSE`` (so maximization survives the round-trip) and explicit
bounds for every integer variable (sidestepping the historic
``INTORG`` default-bound ambiguity). ``from_mps_string`` parses the
sections mainstream writers produce: NAME, OBJSENSE, ROWS, COLUMNS
(with INTORG/INTEND markers), RHS, BOUNDS, ENDATA. RANGES and multiple
objective (``N``) rows raise
:class:`~lp2graph.interop._grounded.InteropError` rather than being
dropped.

The objective constant follows the MPS convention: an RHS entry on the
objective row stores the *negated* constant.
"""

from __future__ import annotations

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
from lp2graph.solve.instance import Instance

__all__ = ["from_mps_string", "to_mps_string"]

_ROW_TYPE = {"le": "L", "ge": "G", "eq": "E"}
_TYPE_CMP = {"L": "le", "G": "ge", "E": "eq"}


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def to_mps_string(f: Formulation, instance: Instance | None = None) -> str:
    """Emit ``f`` as a deterministic free-format MPS string."""
    gm = ground(f, instance)
    out: list[str] = [f"* lp2graph model {gm.id}", f"NAME          {gm.id}"]
    if gm.sense == "max":
        out.append("OBJSENSE")
        out.append("    MAX")
    out.append("ROWS")
    out.append(" N  obj")
    for c in gm.constraints:
        out.append(f" {_ROW_TYPE[c.comparator]}  {c.name}")

    obj_by_var: dict[str, float] = {}
    for coef, var in gm.objective:
        obj_by_var[var] = obj_by_var.get(var, 0.0) + coef
    rows_by_var: dict[str, list[tuple[str, float]]] = {v.name: [] for v in gm.variables}
    for c in gm.constraints:
        for coef, var in c.terms:
            if var not in rows_by_var:
                raise InteropError(f"constraint {c.name!r} references unknown variable {var!r}")
            rows_by_var[var].append((c.name, coef))

    out.append("COLUMNS")
    in_int = False
    for v in gm.variables:
        is_int = v.domain in ("integer", "binary")
        if is_int and not in_int:
            out.append("    MARKER                 'MARKER'                 'INTORG'")
            in_int = True
        if not is_int and in_int:
            out.append("    MARKER                 'MARKER'                 'INTEND'")
            in_int = False
        entries: list[tuple[str, float]] = []
        if v.name in obj_by_var:
            entries.append(("obj", obj_by_var[v.name]))
        entries.extend(rows_by_var[v.name])
        if not entries:
            entries.append(("obj", 0.0))  # a column must appear to exist
        for row, val in entries:
            out.append(f"    {v.name:<10}{row:<10}{format_number(val)}")
    if in_int:
        out.append("    MARKER                 'MARKER'                 'INTEND'")

    out.append("RHS")
    for c in gm.constraints:
        if c.rhs != 0:
            out.append(f"    RHS       {c.name:<10}{format_number(c.rhs)}")
    if gm.objective_constant:
        out.append(f"    RHS       {'obj':<10}{format_number(-gm.objective_constant)}")

    bound_lines: list[str] = []
    for v in gm.variables:
        bound_lines.extend(_bound_lines(v))
    if bound_lines:
        out.append("BOUNDS")
        out.extend(bound_lines)
    out.append("ENDATA")
    return "\n".join(out) + "\n"


def _bound_lines(v: GroundedVar) -> list[str]:
    name = v.name
    if v.domain == "binary":
        return [f" BV BND       {name}"]
    lo, up = v.lower, v.upper
    if v.domain in ("non_negative", "integer") and lo is None:
        lo = 0.0
    if lo is not None and up is not None and lo == up:
        return [f" FX BND       {name:<10}{format_number(lo)}"]
    lines: list[str] = []
    if v.domain == "integer":
        # Explicit bounds always: readers disagree on INTORG defaults.
        lines.append(f" LO BND       {name:<10}{format_number(lo or 0.0)}")
        lines.append(
            f" UP BND       {name:<10}{format_number(up)}"
            if up is not None
            else f" PL BND       {name}"
        )
        return lines
    if lo is None and up is None:
        return [f" FR BND       {name}"]
    if lo is None:
        lines.append(f" MI BND       {name}")
    elif lo != 0:
        lines.append(f" LO BND       {name:<10}{format_number(lo)}")
    if up is not None:
        lines.append(f" UP BND       {name:<10}{format_number(up)}")
    return lines


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def from_mps_string(text: str, *, model_id: str = "mps_model") -> Formulation:
    """Parse a free-format MPS string into a flat canonical ``Formulation``."""
    name = model_id
    sense = "min"
    obj_row: str | None = None
    row_types: dict[str, str] = {}
    row_order: list[str] = []
    col_order: list[str] = []
    col_coefs: dict[str, dict[str, float]] = {}
    integers: set[str] = set()
    rhs: dict[str, float] = {}
    bounds: dict[str, dict[str, float | None]] = {}

    section = ""
    expect_objsense_value = False
    in_int = False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("*"):
            continue
        is_header = not raw[0].isspace()
        toks = raw.split()
        if is_header:
            section = toks[0].upper()
            expect_objsense_value = False
            if section == "OBJSENSE" and len(toks) > 1:
                sense = _parse_sense(toks[1])
            elif section == "OBJSENSE":
                expect_objsense_value = True
            elif section == "NAME":
                name = toks[1] if len(toks) > 1 else model_id
            elif section == "RANGES":
                raise InteropError("MPS RANGES section is not supported")
            elif section == "ENDATA":
                break
            elif section not in ("ROWS", "COLUMNS", "RHS", "BOUNDS", "OBJSENSE", "NAME"):
                raise InteropError(f"unsupported MPS section {section!r}")
            continue
        if expect_objsense_value:
            sense = _parse_sense(toks[0])
            expect_objsense_value = False
            continue
        if section == "ROWS":
            rtype, rname = toks[0].upper(), toks[1]
            if rtype == "N":
                if obj_row is not None:
                    raise InteropError("multiple objective (N) rows are not supported")
                obj_row = rname
            elif rtype in _TYPE_CMP:
                row_types[rname] = rtype
                row_order.append(rname)
            else:
                raise InteropError(f"unknown MPS row type {rtype!r}")
        elif section == "COLUMNS":
            if len(toks) >= 3 and toks[1].strip("'\"").upper() == "MARKER":
                marker = toks[-1].strip("'\"").upper()
                in_int = marker == "INTORG"
                continue
            col = toks[0]
            if col not in col_coefs:
                col_coefs[col] = {}
                col_order.append(col)
            if in_int:
                integers.add(col)
            for row, val in _pairs(toks[1:], raw):
                col_coefs[col][row] = col_coefs[col].get(row, 0.0) + float(val)
        elif section == "RHS":
            data = toks[1:] if len(toks) % 2 == 1 else toks
            for row, val in _pairs(data, raw):
                rhs[row] = float(val)
        elif section == "BOUNDS":
            _apply_bound(toks, bounds, integers, raw)
        else:
            raise InteropError(f"data line outside a known MPS section: {raw!r}")

    if obj_row is None:
        raise InteropError("MPS file declares no objective (N) row")

    variables: list[GroundedVar] = []
    for col in col_order:
        variables.append(_make_var(col, col in integers, bounds.get(col)))
    obj_terms = tuple(
        (col_coefs[col][obj_row], col) for col in col_order if col_coefs[col].get(obj_row)
    )
    constraints = tuple(
        GroundedConstraint(
            name=row,
            terms=tuple((col_coefs[col][row], col) for col in col_order if col_coefs[col].get(row)),
            comparator=_TYPE_CMP[row_types[row]],
            rhs=rhs.get(row, 0.0),
        )
        for row in row_order
    )
    gm = GroundedModel(
        id=name if name else model_id,
        name=name,
        sense=sense,
        variables=tuple(variables),
        objective=obj_terms,
        objective_constant=-rhs.get(obj_row, 0.0),
        constraints=constraints,
    )
    return to_formulation(gm, source="MPS format")


def _parse_sense(tok: str) -> str:
    up = tok.upper()
    if up in ("MAX", "MAXIMIZE"):
        return "max"
    if up in ("MIN", "MINIMIZE"):
        return "min"
    raise InteropError(f"unknown OBJSENSE value {tok!r}")


def _pairs(toks: list[str], raw: str) -> list[tuple[str, str]]:
    if len(toks) % 2 != 0:
        raise InteropError(f"malformed MPS data line (odd field count): {raw.strip()!r}")
    return [(toks[i], toks[i + 1]) for i in range(0, len(toks), 2)]


_BOUND_WITH_VALUE = {"UP", "LO", "FX", "LI", "UI"}
_BOUND_NO_VALUE = {"FR", "MI", "PL", "BV"}


def _apply_bound(
    toks: list[str],
    bounds: dict[str, dict[str, float | None]],
    integers: set[str],
    raw: str,
) -> None:
    btype = toks[0].upper()
    if btype in _BOUND_WITH_VALUE:
        if len(toks) == 4:
            col, val = toks[2], float(toks[3])
        elif len(toks) == 3:
            col, val = toks[1], float(toks[2])
        else:
            raise InteropError(f"malformed MPS bound line: {raw.strip()!r}")
    elif btype in _BOUND_NO_VALUE:
        col, val = toks[-1], 0.0
    else:
        raise InteropError(f"unsupported MPS bound type {btype!r}")
    b = bounds.setdefault(col, {})
    if btype in ("UP", "UI"):
        b["upper"] = val
    elif btype in ("LO", "LI"):
        b["lower"] = val
    elif btype == "FX":
        b["lower"] = b["upper"] = val
    elif btype == "FR":
        b["lower"] = b["upper"] = None
    elif btype == "MI":
        b["lower"] = None
    elif btype == "PL":
        b["upper"] = None
    elif btype == "BV":
        b["lower"], b["upper"] = 0.0, 1.0
        integers.add(col)
    if btype in ("LI", "UI"):
        integers.add(col)


def _make_var(name: str, is_int: bool, bound: dict[str, float | None] | None) -> GroundedVar:
    lower: float | None = 0.0
    upper: float | None = None
    if bound is not None:
        if "lower" in bound:
            lower = bound["lower"]
        if "upper" in bound:
            upper = bound["upper"]
    if is_int:
        if lower == 0.0 and upper == 1.0:
            return GroundedVar(name=name, domain="binary", lower=0.0, upper=1.0)
        return GroundedVar(name=name, domain="integer", lower=lower, upper=upper)
    return GroundedVar(name=name, domain="continuous", lower=lower, upper=upper)
