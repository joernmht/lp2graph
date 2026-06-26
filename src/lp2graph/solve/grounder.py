"""Ground a formulation to a concrete, solvable PuLP model and solve it.

This is the real grounding back-end the v0.1 Pyomo *stub* deferred. Given
a :class:`Formulation` and an :class:`Instance`, it materializes every
variable instance and every constraint instance with concrete numeric
coefficients, builds a ``pulp.LpProblem``, and (optionally) solves it.

Supported (the linear core that covers LP/MIP/MILP and big-M models):

- index families with arbitrary cardinality; ordered/cyclic wrap;
- variable templates over any shape, all four domains, bounds;
- quantified constraints with ``ne_other`` / ``<`` / ``<=`` / ``>`` /
  ``>=`` / ``ordered_pair`` restrictions and ``where``-clause filters;
- terms with numeric or parameter coefficients, signs, index offsets
  (``t-1``), and ``\\sum`` aggregation over index families;
- parameter and literal terms as constants on either side;
- objective with ``sum`` / ``weighted_sum`` combination.

Not yet supported (raise :class:`UnsupportedModel`): ``abs`` / ``max`` /
``min`` / ``indicator`` / ``modulo`` *operators* on terms, indicator
*trigger* constraints, and ``lexicographic`` objectives. Big-M and PESP
modulo are expressible as plain linear constraints and ARE supported.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import pulp

from lp2graph.core.model import (
    Formulation,
    Objective,
    Quantifier,
    Term,
)
from lp2graph.solve.instance import Instance, lookup

_DOMAIN = {
    "continuous": "Continuous",
    "non_negative": "Continuous",
    "integer": "Integer",
    "binary": "Binary",
}
_CMP = {
    "le": lambda a, b: a <= b,
    "ge": lambda a, b: a >= b,
    "eq": lambda a, b: a == b,
}


class UnsupportedModel(Exception):
    """Raised when a formulation uses a feature the grounder cannot solve."""


@dataclass
class SolveResult:
    status: str
    objective: float | None
    n_vars: int
    n_constraints: int
    solver: str
    variables: dict[str, float]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_problem(
    f: Formulation, instance: Instance, *, name: str | None = None
) -> tuple[pulp.LpProblem, dict[str, dict[tuple[int, ...], pulp.LpVariable]]]:
    """Build (but do not solve) a ``pulp.LpProblem`` for ``f`` at ``instance``."""
    _check_supported(f)
    cards = _check_cards(f, instance)
    pvals = instance.parameters

    sense = pulp.LpMaximize if (f.objective and f.objective.sense == "max") else pulp.LpMinimize
    prob = pulp.LpProblem(name or _safe(f.id), sense)

    # 1. Variables, indexed positionally by their shape.
    var_index = f.variable_map()
    vmap: dict[str, dict[tuple[int, ...], pulp.LpVariable]] = {}
    for v in f.variables:
        cat = _DOMAIN[v.domain]
        lo = v.lower
        if lo is None and v.domain == "non_negative":
            lo = 0.0
        if lo is None and v.domain == "binary":
            lo = 0.0
        cells: dict[tuple[int, ...], pulp.LpVariable] = {}
        for tup in _tuples(v.shape, cards):
            vname = _safe(f"{v.name}_" + "_".join(map(str, tup))) if tup else _safe(v.name)
            # ``prob.add_variable`` (vs the deprecated ``LpVariable(...)`` direct
            # constructor, removed in PuLP 4.0) attaches the variable to ``prob``
            # at creation. ``prob.variables()`` still returns only variables that
            # appear in the objective/constraints, so ``n_vars`` is unchanged.
            cells[tup] = prob.add_variable(vname, lowBound=lo, upBound=v.upper, cat=cat)
        vmap[v.name] = cells

    ctx = _Ctx(f=f, cards=cards, pvals=pvals, vmap=vmap, var_index=var_index)

    # 2. Objective.
    if f.objective is not None:
        prob += _objective_expr(ctx, f.objective), "objective"

    # 3. Constraints.
    for c in f.constraints:
        for k, binding in enumerate(_enum_quantifiers(c.quantifiers, cards, pvals)):
            expr_l, drop_l = _side_expr(ctx, c.lhs, binding)
            expr_r, drop_r = _side_expr(ctx, c.rhs, binding)
            if drop_l or drop_r:
                # A non-sum term referenced an out-of-range index (a boundary
                # like ``t_{i-1}`` at ``i=0``): the constraint instance is
                # degenerate and is omitted, not partially enforced.
                continue
            cname = (
                _safe(c.name + "_" + "_".join(f"{i}{v}" for i, v in binding.items()))
                or f"{c.name}_{k}"
            )
            prob += _CMP[c.comparator](expr_l, expr_r), cname[:255]

    return prob, vmap


def default_solver(msg: bool = False) -> pulp.LpSolver:
    """Return the default CBC solver, forward-compatible with PuLP 4.0.

    PuLP 4.0 deprecates ``PULP_CBC_CMD`` in favour of ``COIN_CMD`` (the bundled
    CBC moves to the ``pulp[cbc]`` extra). ``COIN_CMD`` does not auto-discover
    PuLP's bundled CBC binary on PuLP 3.x, so when it reports itself unavailable
    we fall back to the bundled path exposed as the
    ``PULP_CBC_CMD.pulp_cbc_path`` *class* attribute — read without instantiating
    the deprecated solver, so no deprecation warning is emitted. Under PuLP 4.0
    with ``pulp[cbc]`` installed, ``COIN_CMD`` finds CBC itself and the fallback
    path is unused. Deterministic: single-threaded, messages off by default.
    """
    solver = pulp.COIN_CMD(msg=msg, threads=1)
    if not solver.available():
        path = getattr(pulp.PULP_CBC_CMD, "pulp_cbc_path", None)
        if path:
            solver = pulp.COIN_CMD(path=path, msg=msg, threads=1)
    return solver


def solve(
    f: Formulation,
    instance: Instance,
    *,
    solver: pulp.LpSolver | None = None,
    msg: bool = False,
) -> SolveResult:
    """Ground ``f`` at ``instance`` and solve it. CBC by default."""
    prob, vmap = build_problem(f, instance)
    s = solver or default_solver(msg)
    prob.solve(s)
    status = pulp.LpStatus[prob.status].lower()
    obj = pulp.value(prob.objective)
    values = {v.name: v.value() for cells in vmap.values() for v in cells.values()}
    return SolveResult(
        status=status,
        objective=None if obj is None else float(obj),
        n_vars=len(prob.variables()),
        # ``prob.numConstraints()`` (vs ``len(prob.constraints)``, whose
        # dict-mapping access is deprecated in PuLP 4.0) returns the count
        # directly without touching the deprecated mapping interface.
        n_constraints=prob.numConstraints(),
        solver=type(s).__name__,
        variables=values,
    )


def to_lp_string(f: Formulation, instance: Instance) -> str:
    """Ground and return the model in CPLEX LP format (for cross-solving)."""
    import tempfile
    from pathlib import Path

    prob, _ = build_problem(f, instance)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "model.lp"
        prob.writeLP(str(p))
        return p.read_text()


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


@dataclass
class _Ctx:
    f: Formulation
    cards: dict[str, int]
    pvals: Mapping[str, Any]
    vmap: dict[str, dict[tuple[int, ...], pulp.LpVariable]]
    var_index: dict[str, Any]


def _objective_expr(ctx: _Ctx, obj: Objective) -> Any:
    if obj.combination == "lexicographic":
        raise UnsupportedModel(
            "lexicographic objective is not solvable as a single LP; "
            "optimize priorities sequentially instead"
        )
    expr, _ = _side_expr(ctx, obj.terms, {})
    return expr


def _side_expr(ctx: _Ctx, terms: tuple[Term, ...], binding: dict[str, int]) -> tuple[Any, bool]:
    """Build a pulp affine expression for one side.

    Returns ``(expr, dropped)``. ``dropped`` is True if a *non-aggregated*
    term referenced an out-of-range index — the signal that the enclosing
    constraint instance is a degenerate boundary case and should be omitted.
    Aggregated (``\\sum``) terms silently drop out-of-range summands (a
    windowed sum), which is normal and does not set ``dropped``.
    """
    expr = pulp.LpAffineExpression()
    dropped = False
    for t in terms:
        contrib, d = _term_expr(ctx, t, binding)
        expr += contrib
        dropped = dropped or d
    return expr, dropped


def _term_expr(ctx: _Ctx, t: Term, binding: dict[str, int]) -> tuple[Any, bool]:
    """Return ``(contribution, dropped)``. ``dropped`` is True only when a
    non-aggregated term's referenced index falls out of a non-cyclic range."""
    if t.operator in ("abs", "max", "min", "indicator", "modulo"):
        raise UnsupportedModel(f"term operator {t.operator!r} is not solvable")

    if t.operator == "sum":
        total = pulp.LpAffineExpression()
        for scope in _sum_scopes(ctx, t, binding):
            idx = _resolve_indices(ctx, t, scope)
            if idx is not None:
                total += _one_occurrence(ctx, t, scope, idx)
        return total, False

    idx = _resolve_indices(ctx, t, binding)
    if idx is None:
        return pulp.LpAffineExpression(), True
    return _one_occurrence(ctx, t, binding, idx), False


def _one_occurrence(ctx: _Ctx, t: Term, scope: dict[str, int], idx: tuple[int, ...]) -> Any:
    sign = t.sign
    if t.ref_kind == "literal":
        val = t.coefficient if t.coefficient is not None else 1
        return sign * float(val)
    coef = _coef_value(ctx, t, scope, idx)
    if t.ref_kind == "parameter":
        return sign * coef * lookup(ctx.pvals[t.ref], idx)
    return sign * coef * ctx.vmap[t.ref][idx]


def _coef_value(ctx: _Ctx, t: Term, scope: dict[str, int], ref_idx: tuple[int, ...]) -> float:
    """Resolve a term's coefficient to a number."""
    coef = t.coefficient
    if coef is None:
        return 1.0
    if isinstance(coef, (int, float)):
        return float(coef)
    # Parameter coefficient: scalar, or shaped like the referent.
    param = ctx.f.parameter_map().get(coef)
    if param is None:
        raise UnsupportedModel(f"coefficient {coef!r} is not a declared parameter")
    if not param.shape:
        return lookup(ctx.pvals[coef], ())
    # Shaped coefficient: index it by the referent's resolved tuple when the
    # shapes line up (the common ``sum_i c_i x_i`` pattern).
    ref_shape = ctx.var_index[t.ref].shape if t.ref in ctx.var_index else ()
    if param.shape == tuple(ref_shape):
        return lookup(ctx.pvals[coef], ref_idx)
    # Otherwise index by the scope values matching the coefficient's families.
    key = tuple(_first_scope_value(scope, fam) for fam in param.shape)
    return lookup(ctx.pvals[coef], key)


def _first_scope_value(scope: dict[str, int], fam: str) -> int:
    if fam in scope:
        return scope[fam]
    raise UnsupportedModel(f"cannot resolve coefficient index family {fam!r}")


def _resolve_indices(ctx: _Ctx, t: Term, scope: dict[str, int]) -> tuple[int, ...] | None:
    """Resolve a term's bindings positionally into an index tuple, or None
    if an offset falls out of a non-cyclic range."""
    out: list[int] = []
    for b in t.bindings:
        base = _base(b.expr)
        if base not in scope:
            return None
        raw = scope[base] + b.offset
        wrap = b.modulo or _cyclic_family(ctx, b.index)
        if wrap is not None:
            out.append(raw % ctx.cards[wrap])
        elif 0 <= raw < ctx.cards.get(b.index, raw + 1):
            out.append(raw)
        else:
            return None
    return tuple(out)


def _cyclic_family(ctx: _Ctx, family: str) -> str | None:
    idx = ctx.f.index_map().get(family)
    return family if (idx is not None and idx.cyclic) else None


def _sum_scopes(ctx: _Ctx, t: Term, binding: dict[str, int]) -> Iterator[dict[str, int]]:
    """Enumerate the summation scopes for a ``\\sum`` term: the cartesian
    product over the loop variables that are bound by the sum (those binding
    exprs whose base is not already in the enclosing quantifier scope)."""
    sumvars: list[tuple[str, str]] = []
    seen: set[str] = set()
    for b in t.bindings:
        base = _base(b.expr)
        if base not in binding and base not in seen:
            sumvars.append((base, b.index))
            seen.add(base)
    if not sumvars:
        yield dict(binding)
        return
    ranges = [range(ctx.cards[fam]) for _, fam in sumvars]
    for combo in itertools.product(*ranges):
        scope = dict(binding)
        for (vn, _), val in zip(sumvars, combo, strict=True):
            scope[vn] = val
        yield scope


def _enum_quantifiers(
    quantifiers: tuple[Quantifier, ...], cards: Mapping[str, int], pvals: Mapping[str, Any]
) -> list[dict[str, int]]:
    if not quantifiers:
        return [{}]
    ranges = [range(cards[q.over]) for q in quantifiers]
    out = []
    for combo in itertools.product(*ranges):
        binding = {q.index: v for q, v in zip(quantifiers, combo, strict=True)}
        if not _restrictions_ok(quantifiers, binding):
            continue
        if not _where_ok(quantifiers, binding, pvals):
            continue
        out.append(binding)
    return out


def _restrictions_ok(quantifiers: tuple[Quantifier, ...], b: dict[str, int]) -> bool:
    for q in quantifiers:
        if q.restriction == "none":
            continue
        a, o = b[q.index], b[q.restriction_other]  # type: ignore[index]
        if q.restriction == "ne_other" and a == o:
            return False
        if q.restriction == "lt_other" and not a < o:
            return False
        if q.restriction == "le_other" and not a <= o:
            return False
        if q.restriction == "gt_other" and not a > o:
            return False
        if q.restriction == "ge_other" and not a >= o:
            return False
        if q.restriction == "ordered_pair" and not a < o:
            return False
    return True


def _where_ok(
    quantifiers: tuple[Quantifier, ...], b: dict[str, int], pvals: Mapping[str, Any]
) -> bool:
    for q in quantifiers:
        if q.where is None:
            continue
        if q.where.parameter not in pvals:
            raise UnsupportedModel(f"where-clause needs parameter values for {q.where.parameter!r}")
        if lookup(pvals[q.where.parameter], (b[q.index],)) != q.where.equals:
            return False
    return True


def _check_supported(f: Formulation) -> None:
    for c in f.constraints:
        if c.indicator is not None:
            raise UnsupportedModel(
                f"constraint {c.name!r} uses an indicator trigger; linearize it first"
            )


def _check_cards(f: Formulation, instance: Instance) -> dict[str, int]:
    cards = dict(instance.cardinalities)
    for idx in f.indices:
        if idx.name not in cards:
            raise ValueError(f"instance is missing cardinality for index {idx.name!r}")
        if cards[idx.name] <= 0:
            raise ValueError(f"cardinality for {idx.name!r} must be positive")
    return cards


def _tuples(shape: tuple[str, ...], cards: Mapping[str, int]) -> list[tuple[int, ...]]:
    if not shape:
        return [()]
    return list(itertools.product(*[range(cards[s]) for s in shape]))


def _base(expr: str) -> str:
    out = []
    for ch in expr.strip():
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            break
    return "".join(out)


def _safe(name: str) -> str:
    return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name)


__all__ = [
    "Instance",
    "SolveResult",
    "UnsupportedModel",
    "build_problem",
    "default_solver",
    "solve",
    "to_lp_string",
]
