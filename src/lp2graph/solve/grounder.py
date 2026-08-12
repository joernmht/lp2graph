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
- objective with ``sum`` / ``weighted_sum`` combination;
- ``abs`` terms, epigraph-lifted where the lifting is exact (see below);
- ``lexicographic`` objectives, via :func:`solve_lexicographic`.

``abs`` terms are linearized by replacing ``|e|`` with a fresh
non-negative auxiliary ``d`` constrained by ``d >= e`` and ``d >= -e``.
That relaxation is *exact* only where the model pushes ``d`` down onto
``|e|``: in a minimized objective with a positive term sign, in the LHS
of a ``<=`` constraint, and their mirror images. Anywhere else (a
maximized objective, a ``>=`` bound on a magnitude, any ``==``) the
lifted model would admit solutions the original forbids, so the
grounder refuses rather than silently solving a different problem.
Like ``\\sum``, an ``abs`` term aggregates over the index bases its
bindings leave free, giving ``sum_i |e_i|``.

Not yet supported (raise :class:`UnsupportedModel`): ``max`` / ``min`` /
``indicator`` / ``modulo`` *operators* on terms, and indicator *trigger*
constraints. Big-M and PESP modulo are expressible as plain linear
constraints and ARE supported.
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
# Term sign for which epigraph-lifting an ``abs`` term is exact, per side and
# comparator. ``d >= e, d >= -e`` only pins ``d`` down to ``|e|`` when the
# model has an incentive to *shrink* it; where the constraint would instead be
# relaxed by a larger ``d`` (and for every ``==``) there is no exact linear
# lifting, and ``None`` makes the grounder say so.
_ABS_LHS: dict[str, int | None] = {"le": 1, "ge": -1, "eq": None}
_ABS_RHS: dict[str, int | None] = {"le": -1, "ge": 1, "eq": None}


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


@dataclass
class LexicographicResult:
    """Outcome of a staged lexicographic solve.

    ``objectives`` holds one value per priority level, in the order the
    objective declares them; ``status`` is that of the *last* stage
    solved. A stage that does not reach ``optimal`` stops the ladder, so
    ``objectives`` may be shorter than the objective's term list.
    """

    status: str
    objectives: tuple[float, ...]
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
    prob, vmap, _ = _build(f, instance, name=name)
    return prob, vmap


def _build(
    f: Formulation, instance: Instance, *, name: str | None = None
) -> tuple[pulp.LpProblem, dict[str, dict[tuple[int, ...], pulp.LpVariable]], _Ctx]:
    """``build_problem`` plus the evaluation context, for callers that need to
    re-express objective terms against this problem's variables (the staged
    lexicographic solve)."""
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

    ctx = _Ctx(f=f, cards=cards, pvals=pvals, vmap=vmap, var_index=var_index, prob=prob)

    # 2. Objective.
    if f.objective is not None:
        prob += _objective_expr(ctx, f.objective), "objective"

    # 3. Constraints.
    for c in f.constraints:
        for k, binding in enumerate(_enum_quantifiers(c.quantifiers, cards, pvals)):
            expr_l, drop_l = _side_expr(ctx, c.lhs, binding, abs_sign=_ABS_LHS[c.comparator])
            expr_r, drop_r = _side_expr(ctx, c.rhs, binding, abs_sign=_ABS_RHS[c.comparator])
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

    return prob, vmap, ctx


def default_solver(
    msg: bool = False,
    *,
    threads: int = 1,
    time_limit: float | None = None,
    gap_rel: float | None = None,
) -> pulp.LpSolver:
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
    opts: dict[str, object] = {"msg": msg, "threads": threads}
    if time_limit is not None:
        opts["timeLimit"] = time_limit
    if gap_rel is not None:
        opts["gapRel"] = gap_rel
    solver = pulp.COIN_CMD(**opts)
    if not solver.available():
        path = getattr(pulp.PULP_CBC_CMD, "pulp_cbc_path", None)
        if path:
            solver = pulp.COIN_CMD(path=path, **opts)
    return solver


def solve(
    f: Formulation,
    instance: Instance,
    *,
    solver: pulp.LpSolver | str | None = None,
    msg: bool = False,
) -> SolveResult:
    """Ground ``f`` at ``instance`` and solve it.

    ``solver`` selects the back-end: a solver name (``"cbc"``, ``"highs"``,
    ``"gurobi"`` — see :mod:`lp2graph.solve.solvers`), a pre-built
    ``pulp.LpSolver`` instance, or ``None`` for the deterministic CBC default.
    """
    prob, vmap = build_problem(f, instance)
    s = _coerce_solver(solver, msg=msg)
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


def solve_lexicographic(
    f: Formulation,
    instance: Instance,
    *,
    solver: pulp.LpSolver | str | None = None,
    msg: bool = False,
    tolerance: float = 1e-9,
) -> LexicographicResult:
    """Solve a ``lexicographic`` objective one priority level at a time.

    The objective's terms are its priority levels, highest first. Level
    *k* is optimized subject to every higher-priority level being held at
    the value it achieved, within ``tolerance``. The ladder stops at the
    first level that does not reach optimality, and ``objectives`` then
    reports only the levels that did.

    ``tolerance`` is the slack on those held values. Exact equality is
    the textbook statement, but pinning a floating-point optimum with an
    equality can render the next stage infeasible on rounding alone; the
    default is tight enough not to change the ordering and loose enough
    to survive that.

    Passing a pre-built ``pulp.LpSolver`` reuses it across stages. The
    native-API back-ends are stateful (``pulp.GUROBI`` carries one
    ``gurobipy.Model``), so prefer a solver *name* here, which builds a
    fresh back-end per stage.
    """
    obj = f.objective
    if obj is None or obj.combination != "lexicographic":
        raise UnsupportedModel(
            "solve_lexicographic requires an objective with combination='lexicographic'"
        )
    if not obj.terms:
        raise UnsupportedModel("lexicographic objective declares no priority levels")

    abs_sign = 1 if obj.sense == "min" else -1
    achieved: list[float] = []
    status = "not solved"
    variables: dict[str, float] = {}
    solver_name = ""
    n_vars = n_constraints = 0

    for k in range(len(obj.terms)):
        prob, vmap, ctx = _build(
            _stage_formulation(f, obj, k), instance, name=f"{_safe(f.id)}_lex{k}"
        )
        for j, held in enumerate(achieved):
            expr, _ = _side_expr(ctx, (obj.terms[j],), {}, abs_sign=abs_sign)
            prob += (expr <= held + tolerance), f"_lexfix{j}_up"
            prob += (expr >= held - tolerance), f"_lexfix{j}_lo"

        s = _coerce_solver(solver, msg=msg)
        prob.solve(s)
        status = pulp.LpStatus[prob.status].lower()
        solver_name = type(s).__name__
        n_vars, n_constraints = len(prob.variables()), prob.numConstraints()
        variables = {v.name: v.value() for cells in vmap.values() for v in cells.values()}
        if status != "optimal":
            break
        value = pulp.value(prob.objective)
        achieved.append(0.0 if value is None else float(value))

    return LexicographicResult(
        status=status,
        objectives=tuple(achieved),
        n_vars=n_vars,
        n_constraints=n_constraints,
        solver=solver_name,
        variables=variables,
    )


def _stage_formulation(f: Formulation, obj: Objective, k: int) -> Formulation:
    """``f`` with its objective narrowed to priority level ``k`` alone.

    ``model_copy`` rather than a dump/validate round-trip: both models are
    already validated, and only the objective's term tuple changes.
    """
    stage_obj = obj.model_copy(update={"combination": "sum", "terms": (obj.terms[k],)})
    return f.model_copy(update={"objective": stage_obj})


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


def _coerce_solver(solver: pulp.LpSolver | str | None, *, msg: bool) -> pulp.LpSolver:
    """Resolve the ``solver`` argument to a concrete ``pulp.LpSolver``."""
    if solver is None:
        return default_solver(msg)
    if isinstance(solver, str):
        from lp2graph.solve.solvers import make_solver

        return make_solver(solver, msg=msg)
    return solver


@dataclass
class _Ctx:
    f: Formulation
    cards: dict[str, int]
    pvals: Mapping[str, Any]
    vmap: dict[str, dict[tuple[int, ...], pulp.LpVariable]]
    var_index: dict[str, Any]
    prob: pulp.LpProblem
    n_aux: int = 0


def _objective_expr(ctx: _Ctx, obj: Objective) -> Any:
    if obj.combination == "lexicographic":
        raise UnsupportedModel(
            "lexicographic objective is not solvable as a single LP; "
            "use lp2graph.solve.solve_lexicographic to optimize the "
            "priorities sequentially"
        )
    expr, _ = _side_expr(ctx, obj.terms, {}, abs_sign=1 if obj.sense == "min" else -1)
    return expr


def _side_expr(
    ctx: _Ctx,
    terms: tuple[Term, ...],
    binding: dict[str, int],
    *,
    abs_sign: int | None = None,
) -> tuple[Any, bool]:
    """Build a pulp affine expression for one side.

    Returns ``(expr, dropped)``. ``dropped`` is True if a *non-aggregated*
    term referenced an out-of-range index — the signal that the enclosing
    constraint instance is a degenerate boundary case and should be omitted.
    Aggregated (``\\sum``) terms silently drop out-of-range summands (a
    windowed sum), which is normal and does not set ``dropped``.

    ``abs_sign`` is the term sign for which epigraph-lifting an ``abs`` term
    in this position is exact (``None`` if no sign is).
    """
    expr = pulp.LpAffineExpression()
    dropped = False
    for t in terms:
        contrib, d = _term_expr(ctx, t, binding, abs_sign=abs_sign)
        expr += contrib
        dropped = dropped or d
    return expr, dropped


def _term_expr(
    ctx: _Ctx, t: Term, binding: dict[str, int], *, abs_sign: int | None = None
) -> tuple[Any, bool]:
    """Return ``(contribution, dropped)``. ``dropped`` is True only when a
    non-aggregated term's referenced index falls out of a non-cyclic range."""
    if t.operator in ("max", "min", "indicator", "modulo"):
        raise UnsupportedModel(f"term operator {t.operator!r} is not solvable")

    if t.operator == "abs":
        return _abs_expr(ctx, t, binding, abs_sign=abs_sign), False

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


def _abs_expr(ctx: _Ctx, t: Term, binding: dict[str, int], *, abs_sign: int | None) -> Any:
    """Epigraph-lift ``|e|``, aggregating over the term's free index bases.

    Like ``\\sum``, an ``abs`` term loops over the bindings whose base is not
    already bound by the enclosing scope, so ``|t_i|`` under a free ``i``
    grounds to ``sum_i |t_i|``. Each occurrence gets its own auxiliary.
    """
    if abs_sign is None:
        raise UnsupportedModel(
            f"abs term on {t.ref!r} has no exact linearization in this position "
            "(an equality, or a bound that a larger |e| would relax); "
            "reformulate the model with explicit deviation variables"
        )
    if t.sign != abs_sign:
        want = "minimized objective / <= upper bound" if abs_sign == 1 else "the mirrored form"
        raise UnsupportedModel(
            f"abs term on {t.ref!r} carries sign {t.sign:+d}, which the epigraph "
            f"lifting would relax rather than tighten here; it is exact only for "
            f"sign {abs_sign:+d} ({want})"
        )
    total = pulp.LpAffineExpression()
    for scope in _sum_scopes(ctx, t, binding):
        idx = _resolve_indices(ctx, t, scope)
        if idx is None:
            continue
        # ``_one_occurrence`` folds the sign in; the sign belongs *outside*
        # the magnitude, so undo it here and reapply it to the auxiliary.
        inner = t.sign * _one_occurrence(ctx, t, scope, idx)
        ctx.n_aux += 1
        d = ctx.prob.add_variable(f"_abs{ctx.n_aux}_{_safe(t.ref)}", lowBound=0, cat="Continuous")
        ctx.prob += (d >= inner), f"_absp{ctx.n_aux}"
        ctx.prob += (d >= -inner), f"_absn{ctx.n_aux}"
        total += t.sign * d
    return total


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
