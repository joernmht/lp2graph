"""Schema view: templates and indices, no offsets.

The schema view is the topology of the formulation. It exposes:

- One node per index family.
- One node per parameter.
- One node per variable template.
- One node per constraint template.
- One node for the objective (if present).
- One node per aggregation operator (e.g. ``sum_{t in T}``), inserted
  between an aggregated term and its referenced variable.

Edges:

- ``var_in_constraint`` from constraint to variable template per term.
- ``var_in_objective`` from objective to variable template per term.
- ``uses_index`` from variable template to its shape index families.
- ``uses_parameter`` from constraint or objective to a parameter used
  as a symbolic coefficient (parameters appearing as terms already get
  ``var_in_constraint``/``var_in_objective`` edges).

Offsets are *not* shown in the schema view; that is the hybrid view's
job. Every term, regardless of binding offsets, contributes a single
edge here.
"""

from __future__ import annotations

from lp2graph.core.graph import Graph
from lp2graph.core.model import (
    ConstraintTemplate,
    Formulation,
    Objective,
    Term,
)


def schema(f: Formulation) -> Graph:
    """Derive the schema view of ``f``."""
    g = Graph(view="schema")

    # Indices, parameters, variables.
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

    # Constraints.
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
        _emit_terms_for_container(g, c_id, c, c.lhs, side="lhs")
        _emit_terms_for_container(g, c_id, c, c.rhs, side="rhs")

    # Objective.
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
        _emit_objective_terms(g, o_id, f.objective)

    return g


def _emit_terms_for_container(
    g: Graph,
    container_id: str,
    constraint: ConstraintTemplate,
    terms: tuple[Term, ...],
    *,
    side: str,
) -> None:
    for i, term in enumerate(terms):
        _emit_term_edge(
            g,
            src_id=container_id,
            term=term,
            edge_type="var_in_constraint",
            position=f"{side}[{i}]",
        )


def _emit_objective_terms(g: Graph, container_id: str, obj: Objective) -> None:
    for i, term in enumerate(obj.terms):
        _emit_term_edge(
            g,
            src_id=container_id,
            term=term,
            edge_type="var_in_objective",
            position=f"obj[{i}]",
        )


def _emit_term_edge(
    g: Graph,
    *,
    src_id: str,
    term: Term,
    edge_type: str,
    position: str,
) -> None:
    if term.ref_kind == "literal":
        return  # literals are constants; no edge

    target_prefix = "var:" if term.ref_kind == "variable" else "param:"
    target_id = f"{target_prefix}{term.ref}"

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
        edge_role = term.role
        edge_label = ""
        g.add_edge(
            op_id,
            target_id,
            edge_type,  # type: ignore[arg-type]
            role=edge_role,
            label=edge_label,
            data={
                "sign": term.sign,
                "coefficient": term.coefficient,
            },
        )
        _emit_coefficient_edge(g, src_id, term, position)
        return

    g.add_edge(
        src_id,
        target_id,
        edge_type,  # type: ignore[arg-type]
        role=term.role,
        label=position,
        data={
            "sign": term.sign,
            "coefficient": term.coefficient,
        },
    )
    _emit_coefficient_edge(g, src_id, term, position)


def _emit_coefficient_edge(g: Graph, src_id: str, term: Term, position: str) -> None:
    """A symbolic coefficient references a parameter; expose that use as an edge."""
    if not isinstance(term.coefficient, str):
        return
    coef_id = f"param:{term.coefficient}"
    if g.has_node(coef_id):
        g.add_edge(src_id, coef_id, "uses_parameter", role="coef", label=position)


__all__ = ["schema"]
