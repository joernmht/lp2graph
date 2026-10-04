"""Hybrid view: schema view plus offset, sign, and modulo edge labels.

The hybrid view is the schema view enriched with the per-binding offset
information. It is the most informative view at template scale and is
the default for visual inspection and side-by-side comparison.

Specifically, every constraint-to-variable (or objective-to-variable)
edge carries an ``offsets`` data field summarizing the term's bindings:
``{"t": {"expr": "t-1", "offset": -1, "modulo": null}, ...}``, keyed by
the slot's family (numbered ``I.1``, ``I.2`` when a template has several
slots of one family). Edge labels show the same information in a compact
textual form. A quantifier's ``where``-predicate is a ``uses_parameter``
edge (role ``where``) labelled with the compared value.

Offsets are not aggregated across terms; each term produces its own
edge with its own offset signature, even when two terms reference the
same variable template with different offsets. This is by design — it
is what makes time-shifted couplings visually distinguishable.
"""

from __future__ import annotations

from lp2graph.core.graph import Graph
from lp2graph.core.model import (
    Formulation,
    Term,
)
from lp2graph.views.schema import _emit_coefficient_edge, _emit_where_edges


def hybrid(f: Formulation) -> Graph:
    """Derive the hybrid view of ``f``."""
    g = Graph(view="hybrid")

    for idx in f.indices:
        g.add_node(
            f"index:{idx.name}",
            cls="index",
            label=idx.name,
            subtype=("cyclic" if idx.cyclic else "ordered" if idx.ordered else "set"),
            data={"description": idx.description},
        )
    for p in f.parameters:
        g.add_node(
            f"param:{p.name}",
            cls="parameter",
            label=p.name,
            subtype=p.kind,
            shape=p.shape,
            data={"description": p.description},
        )
        for s in p.shape:
            g.add_edge(f"param:{p.name}", f"index:{s}", "uses_index", role="shape")
    for v in f.variables:
        g.add_node(
            f"var:{v.name}",
            cls="variable",
            label=v.name,
            subtype=v.domain,
            shape=v.shape,
            data={
                "description": v.description,
                "role": v.role,
                "lower": v.lower,
                "upper": v.upper,
            },
        )
        for s in v.shape:
            g.add_edge(f"var:{v.name}", f"index:{s}", "uses_index", role="shape")

    for c in f.constraints:
        c_id = f"constraint:{c.name}"
        g.add_node(
            c_id,
            cls="constraint",
            label=c.name,
            subtype=c.kind,
            data={
                "description": c.description,
                "comparator": c.comparator,
                "quantifiers": [
                    {
                        "index": q.index,
                        "over": q.over,
                        "restriction": q.restriction,
                        "restriction_other": q.restriction_other,
                        "where": (
                            None
                            if q.where is None
                            else {"parameter": q.where.parameter, "equals": q.where.equals}
                        ),
                    }
                    for q in c.quantifiers
                ],
            },
        )
        _emit_terms(g, c_id, c.lhs, edge_type="var_in_constraint", side="lhs")
        _emit_terms(g, c_id, c.rhs, edge_type="var_in_constraint", side="rhs")
        _emit_where_edges(g, c_id, c, show_value=True)

    if f.objective is not None:
        o_id = "objective:0"
        g.add_node(
            o_id,
            cls="objective",
            label=f.objective.name,
            subtype=f.objective.sense,
            data={
                "description": f.objective.description,
                "combination": f.objective.combination,
            },
        )
        _emit_terms(g, o_id, f.objective.terms, edge_type="var_in_objective", side="obj")

    return g


def _emit_terms(
    g: Graph,
    src_id: str,
    terms: tuple[Term, ...],
    *,
    edge_type: str,
    side: str,
) -> None:
    for i, term in enumerate(terms):
        if term.ref_kind == "literal":
            continue

        target_prefix = "var:" if term.ref_kind == "variable" else "param:"
        target_id = f"{target_prefix}{term.ref}"
        position = f"{side}[{i}]"

        offsets = {
            key: {
                "expr": b.expr,
                "offset": b.offset,
                "modulo": b.modulo,
            }
            for key, b in zip(_slot_keys(term), term.bindings, strict=True)
        }
        compact_label = _label_for_offsets(offsets, term.sign, term.coefficient)

        if term.operator != "none":
            op_id = f"op:{src_id}/{position}/{term.operator}"
            g.add_node(
                op_id,
                cls="operator",
                subtype=term.operator,
                label=term.operator,
                shape=term.operator_over,
                data={"position": position, "operator_over": list(term.operator_over)},
            )
            g.add_edge(src_id, op_id, "operator_input", role=term.role, label=position)
            g.add_edge(
                op_id,
                target_id,
                edge_type,  # type: ignore[arg-type]
                role=term.role,
                label=compact_label,
                data={
                    "sign": term.sign,
                    "coefficient": term.coefficient,
                    "offsets": offsets,
                },
            )
            _emit_coefficient_edge(g, src_id, term, position)
            continue

        g.add_edge(
            src_id,
            target_id,
            edge_type,  # type: ignore[arg-type]
            role=term.role,
            label=compact_label,
            data={
                "sign": term.sign,
                "coefficient": term.coefficient,
                "offsets": offsets,
            },
        )
        _emit_coefficient_edge(g, src_id, term, position)


def _slot_keys(term: Term) -> list[str]:
    """One key per binding: the slot's family, numbered (``I.1``, ``I.2``) when
    the template has several slots of one family, so ``y_{i,j}`` keeps both
    of its bindings instead of the second overwriting the first."""
    families = [b.index for b in term.bindings]
    seen: dict[str, int] = {}
    keys: list[str] = []
    for fam in families:
        seen[fam] = seen.get(fam, 0) + 1
        keys.append(f"{fam}.{seen[fam]}" if families.count(fam) > 1 else fam)
    return keys


def _label_for_offsets(
    offsets: dict[str, dict[str, str | int | None]],
    sign: int,
    coefficient: float | str | None,
) -> str:
    coef = ""
    if coefficient not in (None, 1):
        coef = (
            f"{coefficient}·"
            if not isinstance(coefficient, (int, float))
            else ("" if coefficient == 1 else f"{coefficient}·")
        )
    sgn = "" if sign == 1 else "-"
    if not offsets:
        return f"{sgn}{coef}".strip("·")
    parts = []
    for k, v in offsets.items():
        modulo = v.get("modulo")
        suffix = f" mod {modulo}" if modulo else ""
        parts.append(f"{k}={v['expr']}{suffix}")
    inner = ", ".join(parts)
    return f"{sgn}{coef}[{inner}]"


__all__ = ["hybrid"]
