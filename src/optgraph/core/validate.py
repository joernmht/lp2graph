"""Cross-cutting invariants beyond what pydantic and JSON Schema enforce.

Validation runs in two phases:

1. **Schema validation** (handled by :mod:`optgraph.core.loader` via
   pydantic). Catches malformed JSON, wrong types, missing fields,
   invalid enum values.
2. **Semantic validation** (this module). Catches references to
   undefined entities, bindings that do not match a referenced
   template's shape, quantifiers that reference an unknown index, etc.

Semantic errors are aggregated and raised as a single
:class:`ValidationError` carrying a list of human-readable messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from optgraph.core.model import (
        ConstraintTemplate,
        Formulation,
        Objective,
        Term,
    )


class ValidationError(Exception):
    """Aggregated semantic validation error.

    The ``errors`` attribute lists every issue found in a single pass,
    so callers see all problems instead of fixing them one at a time.
    """

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors: list[str] = errors or []


def validate(f: Formulation) -> None:
    """Validate cross-cutting invariants of a formulation.

    Raises :class:`ValidationError` if any invariant is violated.
    """
    errors: list[str] = []

    index_names = {i.name for i in f.indices}
    parameter_names = {p.name for p in f.parameters}
    variable_names = {v.name for v in f.variables}

    # 1. Variable shapes reference declared indices.
    for v in f.variables:
        for s in v.shape:
            if s not in index_names:
                errors.append(
                    f"variable {v.name!r}: shape index {s!r} is not declared"
                )

    # 2. Parameter shapes reference declared indices.
    for p in f.parameters:
        for s in p.shape:
            if s not in index_names:
                errors.append(
                    f"parameter {p.name!r}: shape index {s!r} is not declared"
                )

    # 3. Constraints: quantifiers, references, bindings.
    for c in f.constraints:
        _validate_constraint(
            c,
            index_names=index_names,
            parameter_names=parameter_names,
            variable_names=variable_names,
            variable_shapes={v.name: v.shape for v in f.variables},
            parameter_shapes={p.name: p.shape for p in f.parameters},
            errors=errors,
        )

    # 4. Objective.
    if f.objective is not None:
        _validate_objective(
            f.objective,
            index_names=index_names,
            parameter_names=parameter_names,
            variable_names=variable_names,
            variable_shapes={v.name: v.shape for v in f.variables},
            parameter_shapes={p.name: p.shape for p in f.parameters},
            errors=errors,
        )

    # 5. Family consistency: lp must not have integer/binary variables.
    if f.family == "lp":
        for v in f.variables:
            if v.domain in ("integer", "binary"):
                errors.append(
                    f"family is 'lp' but variable {v.name!r} has domain {v.domain!r}"
                )
    if f.family == "mip":
        # mip permits both integer and continuous; nothing to enforce.
        pass
    if f.family == "milp" and not any(
        v.domain in ("integer", "binary") for v in f.variables
    ):
        errors.append(
            "family is 'milp' but no variable has integer or binary domain"
        )

    if errors:
        raise ValidationError(
            f"{len(errors)} validation error(s) in formulation {f.id!r}",
            errors=errors,
        )


def _validate_constraint(
    c: ConstraintTemplate,
    *,
    index_names: set[str],
    parameter_names: set[str],
    variable_names: set[str],
    variable_shapes: dict[str, tuple[str, ...]],
    parameter_shapes: dict[str, tuple[str, ...]],
    errors: list[str],
) -> None:
    quantifier_indices = {q.index for q in c.quantifiers}

    # Quantifier 'over' is a declared index family.
    for q in c.quantifiers:
        if q.over not in index_names:
            errors.append(
                f"constraint {c.name!r}: quantifier {q.index!r} ranges over "
                f"undeclared index {q.over!r}"
            )
        if q.restriction != "none":
            assert q.restriction_other is not None  # checked by pydantic
            if q.restriction_other not in quantifier_indices:
                errors.append(
                    f"constraint {c.name!r}: quantifier {q.index!r} restriction "
                    f"references unknown quantifier {q.restriction_other!r}"
                )
        if q.where is not None:
            if q.where.parameter not in parameter_names:
                errors.append(
                    f"constraint {c.name!r}: quantifier {q.index!r} where-clause "
                    f"references undeclared parameter {q.where.parameter!r}"
                )
            else:
                p_shape = parameter_shapes[q.where.parameter]
                if p_shape != (q.over,):
                    errors.append(
                        f"constraint {c.name!r}: quantifier {q.index!r} where-clause "
                        f"parameter {q.where.parameter!r} has shape {list(p_shape)} "
                        f"but must be shaped [{q.over!r}]"
                    )

    # Each side's terms validate against the available scope.
    scope = quantifier_indices | index_names  # bindings may use any of these
    for term in c.lhs:
        _validate_term(
            term,
            where=f"constraint {c.name!r} lhs",
            parameter_names=parameter_names,
            variable_names=variable_names,
            variable_shapes=variable_shapes,
            parameter_shapes=parameter_shapes,
            quantifier_scope=scope,
            errors=errors,
        )
    for term in c.rhs:
        _validate_term(
            term,
            where=f"constraint {c.name!r} rhs",
            parameter_names=parameter_names,
            variable_names=variable_names,
            variable_shapes=variable_shapes,
            parameter_shapes=parameter_shapes,
            quantifier_scope=scope,
            errors=errors,
        )


def _validate_objective(
    o: Objective,
    *,
    index_names: set[str],
    parameter_names: set[str],
    variable_names: set[str],
    variable_shapes: dict[str, tuple[str, ...]],
    parameter_shapes: dict[str, tuple[str, ...]],
    errors: list[str],
) -> None:
    # Objective has no quantifiers; aggregations live in operator_over.
    for term in o.terms:
        scope = set(term.operator_over) | index_names
        _validate_term(
            term,
            where=f"objective {o.name!r}",
            parameter_names=parameter_names,
            variable_names=variable_names,
            variable_shapes=variable_shapes,
            parameter_shapes=parameter_shapes,
            quantifier_scope=scope,
            errors=errors,
        )


def _validate_term(
    term: Term,
    *,
    where: str,
    parameter_names: set[str],
    variable_names: set[str],
    variable_shapes: dict[str, tuple[str, ...]],
    parameter_shapes: dict[str, tuple[str, ...]],
    quantifier_scope: set[str],
    errors: list[str],
) -> None:
    if term.ref_kind == "variable":
        if term.ref not in variable_names:
            errors.append(f"{where}: term references unknown variable {term.ref!r}")
            return
        shape = variable_shapes[term.ref]
    elif term.ref_kind == "parameter":
        if term.ref not in parameter_names:
            errors.append(f"{where}: term references unknown parameter {term.ref!r}")
            return
        shape = parameter_shapes[term.ref]
    else:  # literal
        if term.bindings:
            errors.append(f"{where}: literal term must not carry bindings")
        return

    # Bindings must cover exactly the referenced template's shape.
    binding_indices = [b.index for b in term.bindings]
    if set(binding_indices) != set(shape):
        errors.append(
            f"{where}: term ref {term.ref!r} has shape {shape!r} but bindings "
            f"cover {sorted(binding_indices)!r}"
        )

    # Coefficient: if string, must be a parameter name.
    if isinstance(term.coefficient, str) and term.coefficient not in parameter_names:
        errors.append(
            f"{where}: term coefficient {term.coefficient!r} is not a declared parameter"
        )


__all__ = ["ValidationError", "validate"]
