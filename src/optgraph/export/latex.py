"""LaTeX export of a formulation's algebraic form.

Produces a LaTeX ``align*`` block for the objective and constraints.
Useful for embedding in papers and for visual inspection of the parsed
model. Does *not* render the graph — that is what
:mod:`optgraph.render` is for.
"""

from __future__ import annotations

from optgraph.core.model import (
    Formulation,
    Quantifier,
    Term,
)

_CMP = {"le": r"\le", "ge": r"\ge", "eq": "="}


def to_latex(f: Formulation) -> str:
    """Render the formulation's algebraic form as LaTeX."""
    lines: list[str] = []
    lines.append(r"\begin{align*}")
    if f.objective is not None:
        sense = r"\min" if f.objective.sense == "min" else r"\max"
        body = _render_term_sum(f.objective.terms)
        lines.append(rf"  {sense}\quad & {body} \\")
    for c in f.constraints:
        lhs = _render_term_sum(c.lhs)
        rhs = _render_term_sum(c.rhs) if c.rhs else "0"
        cmp = _CMP[c.comparator]
        quant = _render_quantifiers(c.quantifiers)
        suffix = rf" & \quad {quant}" if quant else ""
        lines.append(rf"  & {lhs} {cmp} {rhs}{suffix} \\")
    # Variable domains as a final block.
    for v in f.variables:
        shape = _render_shape(v.shape)
        if v.domain == "binary":
            lines.append(rf"  & {v.name}{shape} \in \{{0,1\}} \\")
        elif v.domain == "integer":
            lines.append(rf"  & {v.name}{shape} \in \mathbb{{Z}} \\")
        elif v.domain == "non_negative":
            lines.append(rf"  & {v.name}{shape} \ge 0 \\")
        else:
            lines.append(rf"  & {v.name}{shape} \in \mathbb{{R}} \\")
    lines.append(r"\end{align*}")
    return "\n".join(lines)


def _render_term_sum(terms: tuple[Term, ...]) -> str:
    if not terms:
        return "0"
    parts: list[str] = []
    for i, t in enumerate(terms):
        s = _render_term(t)
        if i == 0:
            parts.append(("-" + s) if t.sign == -1 else s)
        else:
            sep = "-" if t.sign == -1 else "+"
            parts.append(f"{sep} {s}")
    return " ".join(parts)


def _render_term(t: Term) -> str:
    if t.ref_kind == "literal":
        return str(t.coefficient if t.coefficient is not None else 1)
    coef = ""
    if isinstance(t.coefficient, str) or (isinstance(t.coefficient, (int, float)) and t.coefficient != 1):
        coef = f"{t.coefficient} \\cdot "
    body = t.ref
    if t.bindings:
        idx = ",".join(b.expr for b in t.bindings)
        body = f"{t.ref}_{{{idx}}}"
    if t.operator == "sum":
        sub = ",".join(t.operator_over)
        return rf"\sum_{{{sub}}} {coef}{body}"
    if t.operator == "max":
        return rf"\max\;{coef}{body}"
    if t.operator == "min":
        return rf"\min\;{coef}{body}"
    if t.operator == "abs":
        return rf"\left|{coef}{body}\right|"
    return f"{coef}{body}"


def _render_quantifiers(quantifiers: tuple[Quantifier, ...]) -> str:
    if not quantifiers:
        return ""
    parts = [rf"\forall {q.index} \in {q.over}" for q in quantifiers]
    restr = []
    for q in quantifiers:
        if q.restriction == "ne_other":
            restr.append(rf"{q.index} \ne {q.restriction_other}")
        elif q.restriction == "lt_other":
            restr.append(rf"{q.index} < {q.restriction_other}")
        elif q.restriction == "le_other":
            restr.append(rf"{q.index} \le {q.restriction_other}")
        elif q.restriction == "gt_other":
            restr.append(rf"{q.index} > {q.restriction_other}")
        elif q.restriction == "ge_other":
            restr.append(rf"{q.index} \ge {q.restriction_other}")
        elif q.restriction == "ordered_pair":
            restr.append(rf"{q.index} < {q.restriction_other}")
        if q.where is not None:
            restr.append(
                rf"{q.where.parameter}_{{{q.index}}} = {_render_value(q.where.equals)}"
            )
    out = ", ".join(parts)
    if restr:
        out += ", " + ", ".join(restr)
    return out


def _render_value(v: bool | int | float | str) -> str:
    if isinstance(v, bool):
        return r"\mathrm{true}" if v else r"\mathrm{false}"
    return str(v)


def _render_shape(shape: tuple[str, ...]) -> str:
    if not shape:
        return ""
    return f"_{{{','.join(shape)}}}"


__all__ = ["to_latex"]
