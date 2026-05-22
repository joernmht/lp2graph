"""Ground view: fully instantiated graph at given index cardinalities.

The ground view materializes every variable instance and every
constraint instance for the supplied cardinalities. It applies
*degeneracy filters*:

- **Out-of-range offsets.** A binding ``t-1`` for a non-cyclic index is
  dropped at ``t = 0``; the corresponding constraint instance loses
  that term. If the constraint has *any* such drop, the instance is
  emitted but flagged with ``data={"degenerate": True}`` so the
  renderer can dim it.
- **i != j (and friends).** Pair quantifiers with ``ne_other``,
  ``lt_other``, etc. exclude tuples that fail the restriction.
- **Ordered pairs.** ``ordered_pair`` keeps only ``(i, j)`` with
  ``i < j``.

Cyclic indices wrap modulo their cardinality; the modulo binding field
overrides the per-index ``cyclic`` flag.

The ground view is *expensive* at large cardinalities. The library
performs no caching; callers should ground sparingly and at small
cardinalities for visual purposes (typically 3 ≤ |I|, |T| ≤ 8).
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from typing import Any

from lp2graph.core.graph import Graph
from lp2graph.core.model import (
    Binding,
    ConstraintTemplate,
    Formulation,
    Index,
    Objective,
    Quantifier,
    Term,
    VariableTemplate,
)


def ground(
    f: Formulation,
    cardinalities: Mapping[str, int],
    parameter_values: Mapping[str, Any] | None = None,
) -> Graph:
    """Derive the ground view of ``f`` at the given index cardinalities.

    Args:
        f: the formulation.
        cardinalities: positive integer cardinality for every index
            family. All declared indices must be present.
        parameter_values: optional concrete values for parameters. Each
            entry maps a parameter name to either a flat sequence (for
            1-D parameters) or a mapping from index tuples to values
            (for any rank). Required for any parameter referenced by a
            quantifier ``where``-clause.

    Raises:
        ValueError: if a required index cardinality is missing or not
            positive, or a parameter value required by a ``where``-
            clause is not supplied.
    """
    cards = dict(cardinalities)
    for idx in f.indices:
        if idx.name not in cards:
            raise ValueError(f"missing cardinality for index {idx.name!r}")
        if cards[idx.name] <= 0:
            raise ValueError(
                f"cardinality for index {idx.name!r} must be positive (got {cards[idx.name]})"
            )

    pvals = dict(parameter_values) if parameter_values is not None else {}
    _check_where_parameters(f, pvals)

    g = Graph(view="ground")
    index_map = f.index_map()
    var_map = f.variable_map()

    # 1. Materialize every variable instance.
    for v in f.variables:
        for tup in _enumerate_shape(v.shape, cards):
            inst_id = _var_instance_id(v.name, tup)
            g.add_node(
                inst_id,
                cls="instance_variable",
                subtype=v.domain,
                label=_var_instance_label(v.name, tup),
                data={
                    "template": v.name,
                    "indices": dict(tup),
                    "role": v.role,
                    "lower": v.lower,
                    "upper": v.upper,
                },
            )

    # 2. Materialize every constraint instance, applying degeneracy filters.
    for c in f.constraints:
        _ground_constraint(g, c, cards, index_map, var_map, pvals)

    # 3. Materialize the objective as a single node connected to every
    #    instance variable that appears in any objective term.
    if f.objective is not None:
        _ground_objective(g, f.objective, cards, index_map, var_map)

    return g


def _check_where_parameters(
    f: Formulation, pvals: Mapping[str, Any]
) -> None:
    """Every ``where``-clause parameter must have a concrete value supplied."""
    for c in f.constraints:
        for q in c.quantifiers:
            if q.where is None:
                continue
            if q.where.parameter not in pvals:
                raise ValueError(
                    f"constraint {c.name!r}: quantifier {q.index!r} where-clause "
                    f"requires parameter_values for {q.where.parameter!r}"
                )


def _lookup_parameter_value(
    values: Any, key: tuple[int, ...]
) -> Any:
    """Read a value out of either a flat sequence (1-D) or a mapping."""
    if isinstance(values, Mapping):
        if key in values:
            return values[key]
        if len(key) == 1 and key[0] in values:
            return values[key[0]]
        raise KeyError(key)
    if len(key) == 1:
        return values[key[0]]
    raise TypeError(
        "multi-index parameter values must be supplied as a Mapping"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enumerate_shape(
    shape: tuple[str, ...], cards: Mapping[str, int]
) -> list[tuple[tuple[str, int], ...]]:
    """Enumerate every index tuple for a shape, in declaration order."""
    if not shape:
        return [tuple()]
    ranges = [range(cards[s]) for s in shape]
    out: list[tuple[tuple[str, int], ...]] = []
    for combo in itertools.product(*ranges):
        out.append(tuple(zip(shape, combo, strict=True)))
    return out


def _var_instance_id(name: str, tup: tuple[tuple[str, int], ...]) -> str:
    if not tup:
        return f"varinst:{name}"
    suffix = "_".join(f"{k}{v}" for k, v in tup)
    return f"varinst:{name}_{suffix}"


def _var_instance_label(name: str, tup: tuple[tuple[str, int], ...]) -> str:
    if not tup:
        return name
    return f"{name}[{','.join(str(v) for _, v in tup)}]"


def _constraint_instance_id(name: str, tup: tuple[tuple[str, int], ...]) -> str:
    if not tup:
        return f"cinst:{name}"
    suffix = "_".join(f"{k}{v}" for k, v in tup)
    return f"cinst:{name}_{suffix}"


def _constraint_instance_label(name: str, tup: tuple[tuple[str, int], ...]) -> str:
    if not tup:
        return name
    return f"{name}[{','.join(str(v) for _, v in tup)}]"


def _enumerate_quantifiers(
    quantifiers: tuple[Quantifier, ...],
    cards: Mapping[str, int],
    pvals: Mapping[str, Any],
) -> list[dict[str, int]]:
    """Enumerate every binding of the constraint's quantifiers, applying restrictions."""
    if not quantifiers:
        return [{}]
    ranges = [range(cards[q.over]) for q in quantifiers]
    out: list[dict[str, int]] = []
    for combo in itertools.product(*ranges):
        binding = {q.index: v for q, v in zip(quantifiers, combo, strict=True)}
        if not _restrictions_pass(quantifiers, binding):
            continue
        if not _where_clauses_pass(quantifiers, binding, pvals):
            continue
        out.append(binding)
    return out


def _where_clauses_pass(
    quantifiers: tuple[Quantifier, ...],
    binding: dict[str, int],
    pvals: Mapping[str, Any],
) -> bool:
    for q in quantifiers:
        if q.where is None:
            continue
        idx_value = binding[q.index]
        actual = _lookup_parameter_value(pvals[q.where.parameter], (idx_value,))
        if actual != q.where.equals:
            return False
    return True


def _restrictions_pass(quantifiers: tuple[Quantifier, ...], binding: dict[str, int]) -> bool:
    for q in quantifiers:
        if q.restriction == "none":
            continue
        other = q.restriction_other
        assert other is not None
        a = binding[q.index]
        b = binding[other]
        if q.restriction == "ne_other" and a == b:
            return False
        if q.restriction == "lt_other" and not (a < b):
            return False
        if q.restriction == "le_other" and not (a <= b):
            return False
        if q.restriction == "gt_other" and not (a > b):
            return False
        if q.restriction == "ge_other" and not (a >= b):
            return False
        if q.restriction == "ordered_pair" and not (a < b):
            return False
    return True


def _resolve_binding(
    binding: Binding,
    quant_binding: dict[str, int],
    cards: Mapping[str, int],
    index_map: dict[str, Index],
) -> int | None:
    """Resolve a binding's index value under the current quantifier scope.

    Returns ``None`` if the resolved value falls out of range and the
    target index is not cyclic (and the binding does not declare a
    modulo).
    """
    # The binding's expr is parsed for the simple offset case (the
    # offset field carries it). The binding's ``index`` here is the
    # *position name on the referenced template*; the ``expr`` is in
    # the constraint's quantifier scope.

    # We need the *base* quantifier variable name from the expr. The
    # offset is given. The expr's leading token (before any +/- offset)
    # is the quantifier variable name. We rely on the offset field
    # already extracted; we look up the quantifier value via expr's
    # leading identifier.
    base = _expr_base(binding.expr)
    if base not in quant_binding:
        # The binding references an index that is not in the constraint's
        # quantifier scope. This is malformed and would have been caught
        # by validation; defensively, skip the term.
        return None
    raw = quant_binding[base] + binding.offset

    # Determine if wrapping applies.
    wrap_index = binding.modulo
    if wrap_index is None:
        # Fall back to the target index family's cyclic flag, if any.
        target_idx = index_map.get(binding.index)
        if target_idx is not None and target_idx.cyclic:
            wrap_index = binding.index

    if wrap_index is not None:
        n = cards[wrap_index]
        return raw % n

    if 0 <= raw < cards[binding.index]:
        return raw
    return None


def _expr_base(expr: str) -> str:
    """Extract the leading identifier from a binding expression."""
    s = expr.strip()
    out = []
    for ch in s:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            break
    return "".join(out)


def _ground_constraint(
    g: Graph,
    c: ConstraintTemplate,
    cards: Mapping[str, int],
    index_map: dict[str, Index],
    var_map: dict[str, VariableTemplate],
    pvals: Mapping[str, Any],
) -> None:
    for quant_binding in _enumerate_quantifiers(c.quantifiers, cards, pvals):
        cinst_id = _constraint_instance_id(
            c.name, tuple(sorted(quant_binding.items()))
        )
        # Stable ID using declaration order of quantifiers, not sorted.
        cinst_id = _constraint_instance_id(
            c.name, tuple((q.index, quant_binding[q.index]) for q in c.quantifiers)
        )
        degenerate = False
        edges_to_add: list[dict[str, Any]] = []

        for side, terms in (("lhs", c.lhs), ("rhs", c.rhs)):
            for i, term in enumerate(terms):
                if term.ref_kind != "variable":
                    continue
                # If the term is aggregated, expand the aggregation.
                if term.operator == "sum":
                    edge_specs = _ground_sum_term(
                        term, quant_binding, cards, index_map
                    )
                    for spec in edge_specs:
                        edges_to_add.append({**spec, "side": side, "pos": i})
                else:
                    resolved = _resolve_term(term, quant_binding, cards, index_map)
                    if resolved is None:
                        degenerate = True
                        continue
                    edges_to_add.append(
                        {
                            "var_template": term.ref,
                            "indices": resolved,
                            "sign": term.sign,
                            "coefficient": term.coefficient,
                            "role": term.role,
                            "side": side,
                            "pos": i,
                        }
                    )

        g.add_node(
            cinst_id,
            cls="instance_constraint",
            subtype=c.kind,
            label=_constraint_instance_label(
                c.name, tuple((q.index, quant_binding[q.index]) for q in c.quantifiers)
            ),
            data={
                "template": c.name,
                "quantifiers": dict(quant_binding),
                "comparator": c.comparator,
                "degenerate": degenerate,
            },
        )
        for spec in edges_to_add:
            v_template = spec["var_template"]
            v_shape = var_map[v_template].shape
            tup = tuple((s, spec["indices"][s]) for s in v_shape)
            target = _var_instance_id(v_template, tup)
            if not g.has_node(target):
                # Should not happen; defensive.
                continue
            g.add_edge(
                cinst_id,
                target,
                "ground_var_in_constraint",
                role=spec["role"],
                label=f"{spec['side']}[{spec['pos']}]",
                data={"sign": spec["sign"], "coefficient": spec["coefficient"]},
            )


def _resolve_term(
    term: Term,
    quant_binding: dict[str, int],
    cards: Mapping[str, int],
    index_map: dict[str, Index],
) -> dict[str, int] | None:
    """Resolve a non-aggregated term's bindings; returns None if out of range."""
    out: dict[str, int] = {}
    for b in term.bindings:
        v = _resolve_binding(b, quant_binding, cards, index_map)
        if v is None:
            return None
        out[b.index] = v
    return out


def _ground_sum_term(
    term: Term,
    quant_binding: dict[str, int],
    cards: Mapping[str, int],
    index_map: dict[str, Index],
) -> list[dict[str, Any]]:
    """Expand a ``sum_{k in K}`` term into per-instance edges."""
    out: list[dict[str, Any]] = []
    op_indices = list(term.operator_over)
    op_ranges = [range(cards[k]) for k in op_indices]
    for combo in itertools.product(*op_ranges):
        scope = dict(quant_binding)
        for k, idx_val in zip(op_indices, combo, strict=True):
            scope[k] = idx_val
        resolved: dict[str, int] = {}
        skip = False
        for b in term.bindings:
            v = _resolve_binding(b, scope, cards, index_map)
            if v is None:
                skip = True
                break
            resolved[b.index] = v
        if skip:
            continue
        out.append(
            {
                "var_template": term.ref,
                "indices": resolved,
                "sign": term.sign,
                "coefficient": term.coefficient,
                "role": term.role,
            }
        )
    return out


def _ground_objective(
    g: Graph,
    obj: Objective,
    cards: Mapping[str, int],
    index_map: dict[str, Index],
    var_map: dict[str, VariableTemplate],
) -> None:
    o_id = "objinst:0"
    g.add_node(
        o_id,
        cls="objective",
        subtype=obj.sense,
        label=obj.name,
        data={"combination": obj.combination},
    )
    for i, term in enumerate(obj.terms):
        if term.ref_kind != "variable":
            continue
        if term.operator == "sum":
            specs = _ground_sum_term(term, {}, cards, index_map)
        else:
            r = _resolve_term(term, {}, cards, index_map)
            specs = (
                []
                if r is None
                else [
                    {
                        "var_template": term.ref,
                        "indices": r,
                        "sign": term.sign,
                        "coefficient": term.coefficient,
                        "role": term.role,
                    }
                ]
            )
        for spec in specs:
            v_shape = var_map[spec["var_template"]].shape
            tup = tuple((s, spec["indices"][s]) for s in v_shape)
            target = _var_instance_id(spec["var_template"], tup)
            if not g.has_node(target):
                continue
            g.add_edge(
                o_id,
                target,
                "ground_var_in_constraint",
                role=spec["role"],
                label=f"obj[{i}]",
                data={"sign": spec["sign"], "coefficient": spec["coefficient"]},
            )


__all__ = ["ground"]
