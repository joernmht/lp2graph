"""Deterministic graph -> natural-language problem description.

The reverse of "read a problem, get a model": given a canonical model
(the graph), emit a fitting, human-readable *problem description* in
Markdown — sets, input data, decisions, constraints (one sentence each,
generated structurally from the quantifiers/terms/comparator), and the
objective. With an :class:`~lp2graph.solve.instance.Instance`, the
declared parameters are rendered as concrete **data tables**.

There is no model in the loop: the same formulation always yields the
same prose. This direction cannot be validated against a ground-truth
number (there is none), only structurally/grammatically — every sentence
is well-formed, terminated, and references only declared symbols.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lp2graph.core.model import (
    ConstraintTemplate,
    Formulation,
    Objective,
    Quantifier,
    Term,
)

_FAMILY = {
    "lp": "linear program",
    "mip": "mixed-integer program",
    "milp": "mixed-integer linear program",
}
_DOMAIN = {
    "binary": "binary (0/1)",
    "integer": "integer",
    "non_negative": "continuous, non-negative",
    "continuous": "continuous",
}
_CMP = {"le": "must be at most", "ge": "must be at least", "eq": "must equal"}
_RESTR = {
    "ne_other": "{a} ≠ {b}",
    "lt_other": "{a} < {b}",
    "le_other": "{a} ≤ {b}",
    "gt_other": "{a} > {b}",
    "ge_other": "{a} ≥ {b}",
    "ordered_pair": "{a} < {b}",
}


def describe(f: Formulation, instance: Any | None = None) -> str:
    """Render ``f`` as a Markdown problem description.

    Args:
        f: the formulation (graph) to describe.
        instance: optional :class:`Instance`; when given, parameter values
            are rendered as data tables.
    """
    pvals = instance.parameters if instance is not None else {}
    cards = instance.cardinalities if instance is not None else {}
    out: list[str] = []
    a = out.append

    a(f"# {f.name}")
    a("")
    if f.description:
        a(f.description.strip())
        a("")
    a(
        f"This is a **{_FAMILY.get(f.family, f.family)}**"
        + (f" ({', '.join(f.tags)})." if f.tags else ".")
    )
    a("")

    if f.indices:
        a("## Index sets")
        a("")
        for idx in f.indices:
            note = []
            if idx.ordered:
                note.append("ordered")
            if idx.cyclic:
                note.append("cyclic / periodic")
            extra = f" _({', '.join(note)})_" if note else ""
            card = f" — {cards[idx.name]} elements" if idx.name in cards else ""
            a(f"- **{idx.name}**{card}: {_sent(idx.description) or 'an index set.'}{extra}")
        a("")

    if f.parameters:
        a("## Input data")
        a("")
        for p in f.parameters:
            shape = f"[{', '.join(p.shape)}]" if p.shape else " (scalar)"
            dc = f" _{p.domain_class.replace('_', ' ')}_" if p.domain_class else ""
            a(f"- **{p.name}{shape}** — {_sent(p.description) or 'a model parameter.'}{dc}")
        a("")
        if pvals:
            tables = _data_tables(f, pvals)
            if tables:
                a("### Data values")
                a("")
                out.extend(tables)

    a("## Decision variables")
    a("")
    for v in f.variables:
        shape = f"[{', '.join(v.shape)}]" if v.shape else ""
        role = f" _({v.role})_" if v.role != "primary" else ""
        dsc = _sent(v.description) or "a decision variable"
        a(f"- **{v.name}{shape}** — {dsc}. It is {_DOMAIN.get(v.domain, v.domain)}.{role}")
    a("")

    if f.constraints:
        a("## Constraints")
        a("")
        for i, c in enumerate(f.constraints, 1):
            a(f"{i}. {_describe_constraint(c)}")
        a("")

    if f.objective is not None:
        a("## Objective")
        a("")
        a(_describe_objective(f.objective))
        a("")

    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Constraints / objective
# ---------------------------------------------------------------------------


def _describe_constraint(c: ConstraintTemplate) -> str:
    quant = _quantifier_phrase(c.quantifiers)
    lhs = _render_terms(c.lhs)
    rhs = _render_terms(c.rhs) if c.rhs else "0"
    body = f"{lhs} {_CMP[c.comparator]} {rhs}"
    prefix = f"{quant}, " if quant else ""
    sentence = f"{prefix}{body}.".strip()
    sentence = sentence[0].upper() + sentence[1:]
    gloss = f" _({_sent(c.description)})_" if c.description else ""
    return f"**{c.name}** — {sentence}{gloss}"


def _describe_objective(o: Objective) -> str:
    verb = "Minimize" if o.sense == "min" else "Maximize"
    body = _render_terms(o.terms)
    label = _sent(o.description) or _sent(o.name.replace("_", " "))
    combo = ""
    if o.combination == "lexicographic":
        combo = " The terms are prioritized lexicographically (earlier terms dominate)."
    elif o.combination == "weighted_sum":
        combo = " The terms are combined as a weighted sum."
    if label and label.lower().startswith(("minimize", "maximize")):
        head = f"{label}: "
    elif label:
        head = f"{verb} {label}: "
    else:
        head = f"{verb}: "
    return f"{head}{body}.{combo}"


def _quantifier_phrase(quantifiers: tuple[Quantifier, ...]) -> str:
    if not quantifiers:
        return ""
    parts = [f"{q.index} ∈ {q.over}" for q in quantifiers]
    conds = []
    for q in quantifiers:
        if q.restriction != "none":
            conds.append(_RESTR[q.restriction].format(a=q.index, b=q.restriction_other))
        if q.where is not None:
            conds.append(f"{q.where.parameter}[{q.index}] = {q.where.equals}")
    phrase = "for every " + ", ".join(parts)
    if conds:
        phrase += " with " + " and ".join(conds)
    return phrase


# ---------------------------------------------------------------------------
# Term rendering (symbolic but readable inline text)
# ---------------------------------------------------------------------------


def _render_terms(terms: tuple[Term, ...]) -> str:
    if not terms:
        return "0"
    parts: list[str] = []
    for i, t in enumerate(terms):
        s = _render_term(t)
        if i == 0:
            parts.append(("-" + s) if t.sign == -1 else s)
        else:
            parts.append(("- " if t.sign == -1 else "+ ") + s)
    return " ".join(parts)


def _render_term(t: Term) -> str:
    if t.ref_kind == "literal":
        return _num(t.coefficient if t.coefficient is not None else 1)
    sub = ""
    if t.bindings:
        sub = "[" + ", ".join(b.expr for b in t.bindings) + "]"
    body = f"{t.ref}{sub}"
    if isinstance(t.coefficient, str):
        body = f"{t.coefficient}·{body}"
    elif isinstance(t.coefficient, (int, float)) and t.coefficient != 1:
        body = f"{_num(t.coefficient)}·{body}"
    if t.operator == "sum":
        over = ", ".join(t.operator_over)
        return f"the total over {over} of {body}"
    if t.operator == "abs":
        return f"|{body}|"
    if t.operator in ("max", "min"):
        return f"{t.operator}({body})"
    if t.operator == "indicator":
        return f"\U0001d7d9[{body}]"
    return body


# ---------------------------------------------------------------------------
# Data tables
# ---------------------------------------------------------------------------


def _data_tables(f: Formulation, pvals: Mapping[str, Any]) -> list[str]:
    from lp2graph.solve.instance import lookup

    lines: list[str] = []
    scalars: list[str] = []
    for p in f.parameters:
        if p.name not in pvals:
            continue
        if not p.shape:
            scalars.append(f"- **{p.name}** = {_num(pvals[p.name])}")
        elif len(p.shape) == 1:
            n = _dim(pvals[p.name])
            header = f"| {p.shape[0]} | {p.name} |"
            lines.append(f"**{p.name}** (indexed by {p.shape[0]}):")
            lines.append("")
            lines.append(header)
            lines.append("|" + "---|" * 2)
            for i in range(n):
                lines.append(f"| {i} | {_num(lookup(pvals[p.name], (i,)))} |")
            lines.append("")
        elif len(p.shape) == 2:
            rows = _dim(pvals[p.name])
            cols = _dim2(pvals[p.name])
            lines.append(f"**{p.name}** (rows {p.shape[0]}, columns {p.shape[1]}):")
            lines.append("")
            lines.append(
                "| "
                + p.shape[0]
                + "\\"
                + p.shape[1]
                + " | "
                + " | ".join(str(j) for j in range(cols))
                + " |"
            )
            lines.append("|" + "---|" * (cols + 1))
            for i in range(rows):
                vals = " | ".join(_num(lookup(pvals[p.name], (i, j))) for j in range(cols))
                lines.append(f"| **{i}** | {vals} |")
            lines.append("")
    if scalars:
        lines = ["**Scalars:**", "", *scalars, "", *lines]
    return lines


def _dim(v: Any) -> int:
    if isinstance(v, Mapping):
        keys = [k for k in v]
        return int(max((k[0] if isinstance(k, (tuple, list)) else k) for k in keys)) + 1
    return len(v)


def _dim2(v: Any) -> int:
    if isinstance(v, Mapping):
        return int(max(k[1] for k in v if isinstance(k, (tuple, list)))) + 1
    return len(v[0])


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _sent(s: str) -> str:
    s = " ".join((s or "").split()).rstrip(".")
    return s


def _num(x: Any) -> str:
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, (int, float)) and float(x).is_integer():
        return str(int(x))
    return str(x)


__all__ = ["describe"]
