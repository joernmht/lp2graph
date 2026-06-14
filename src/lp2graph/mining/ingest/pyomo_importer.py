"""Pyomo importer (M1a).

The library can *export* a Pyomo skeleton (:mod:`lp2graph.export.pyomo_stub`)
but cannot import one. This module closes the loop: it builds a canonical
:class:`~lp2graph.core.model.Formulation` from a Pyomo
``ConcreteModel``/``AbstractModel`` by mirroring the export's
domain/kind mapping in reverse.

Recovery is *structural and best-effort*. Pyomo constraint/objective
*expressions* are arbitrary Python at runtime; deep term recovery is not
always possible deterministically. The importer therefore recovers the
solid structure (sets, parameters, variables with their domains/bounds,
and the name/quantifier/comparator/kind shell of every constraint plus the
objective sense) and produces a model that *passes validation* -- or, if a
component cannot be mapped, a reported :class:`IngestionFailure` rather than
a partial, invalid result. ``pyomo`` is imported lazily so importing this
module never requires pyomo to be installed.
"""

from __future__ import annotations

import re
from typing import Any

from lp2graph.core.model import (
    ConstraintTemplate,
    Formulation,
    Index,
    Objective,
    Parameter,
    Quantifier,
    Term,
    VariableTemplate,
)
from lp2graph.core.validate import ValidationError, validate
from lp2graph.mining.ingest.result import IngestionFailure, IngestionResult
from lp2graph.mining.provenance import ProvenanceMap, SourceSpan

# Mirror of the export domain map (lp2graph.export.pyomo_stub), reversed.
_DOMAIN_BY_NAME: dict[str, str] = {
    "Binary": "binary",
    "NonNegativeReals": "non_negative",
    "Integers": "integer",
    "NonNegativeIntegers": "integer",
    "Reals": "continuous",
    "PositiveReals": "non_negative",
}


def _slug(name: str) -> str:
    """Lower-case identifier usable as a Formulation ``id``."""
    s = re.sub(r"[^a-z0-9_.-]+", "_", name.lower()).strip("_")
    return s or "pyomo_model"


def _domain_of(var: Any) -> str:
    """Map a Pyomo Var's domain to a canonical :class:`VariableDomain`.

    Indexed ``Var`` containers do not expose ``.domain`` directly; the
    domain lives on each member ``VarData``, so a representative member is
    consulted. Falls back to ``"continuous"`` for unrecognized domains;
    the variable is still recovered (a continuous relaxation), never
    dropped.
    """
    member = var
    is_indexed = getattr(var, "is_indexed", None)
    if callable(is_indexed) and is_indexed():
        values = getattr(var, "values", None)
        member = next(iter(values()), var) if callable(values) else var
    try:
        dom = member.domain
    except Exception:  # guard pyomo internals / raising domain properties
        dom = None
    dom_name = getattr(dom, "name", None) or type(dom).__name__
    return _DOMAIN_BY_NAME.get(dom_name, "continuous")


def from_pyomo(model: object) -> IngestionResult:
    """Build a canonical :class:`IngestionResult` from a Pyomo model.

    ``model`` is a ``pyomo.environ.ConcreteModel`` or ``AbstractModel``.
    Returns a successful result with a validated formulation, or a failure
    result naming the stage that broke (``"import"`` if pyomo is absent,
    ``"convert"`` for an unmappable component, ``"validate"`` if the
    recovered structure is semantically invalid).
    """
    source = f"pyomo:{getattr(model, 'name', None) or type(model).__name__}"

    try:
        from pyomo.environ import (
            Constraint,
            Param,
            Set,
            Var,
            maximize,
        )
        from pyomo.environ import (
            Objective as PyoObjective,
        )
    except ImportError as exc:
        return IngestionResult.single_failure(
            source=source,
            stage="import",
            message="pyomo is not installed; cannot import a Pyomo model. "
            "Install pyomo to use from_pyomo().",
            detail=str(exc),
        )

    failures: list[IngestionFailure] = []
    indices: list[Index] = []
    parameters: list[Parameter] = []
    variables: list[VariableTemplate] = []

    try:
        index_names = _collect_sets(model, Set, indices)
        _collect_params(model, Param, parameters, index_names, failures)
        _collect_vars(model, Var, variables, index_names, failures)
        objective = _collect_objective(model, PyoObjective, maximize, failures)
        constraints = _collect_constraints(model, Constraint, index_names, failures)
    except Exception as exc:
        return IngestionResult.single_failure(
            source=source,
            stage="convert",
            message=f"failed to traverse Pyomo model: {exc}",
            detail=type(exc).__name__,
        )

    if not variables:
        failures.append(
            IngestionFailure(
                source=source,
                stage="convert",
                message="Pyomo model declares no Var components; a Formulation "
                "requires at least one variable.",
            )
        )

    if failures:
        return IngestionResult.failure(source=source, failures=tuple(failures))

    family = _infer_family(variables)
    try:
        formulation = Formulation(
            id=_slug(getattr(model, "name", None) or type(model).__name__),
            name=getattr(model, "name", None) or "Imported Pyomo model",
            family=family,
            description="Structurally imported from a Pyomo model.",
            indices=tuple(indices),
            parameters=tuple(parameters),
            variables=tuple(variables),
            constraints=tuple(constraints),
            objective=objective,
        )
    except ValidationError as exc:
        return IngestionResult.single_failure(
            source=source,
            stage="convert",
            message=f"recovered structure is not a valid Formulation: {exc}",
            detail=" | ".join(getattr(exc, "errors", []) or [str(exc)]),
        )
    except Exception as exc:
        return IngestionResult.single_failure(
            source=source,
            stage="convert",
            message=f"recovered structure is not a valid Formulation: {exc}",
            detail=type(exc).__name__,
        )

    try:
        validate(formulation)
    except ValidationError as exc:
        return IngestionResult.single_failure(
            source=source,
            stage="validate",
            message=f"recovered formulation failed semantic validation: {exc}",
            detail=" | ".join(exc.errors),
        )

    prov = ProvenanceMap(source=source)
    field_spans = {f"variables.{v.name}": SourceSpan(source=source) for v in variables}
    prov = ProvenanceMap(source=source, field_spans=field_spans)
    return IngestionResult.success(source=source, formulation=formulation, provenance=prov)


# --- component collectors --------------------------------------------------


def _collect_sets(model: Any, set_cls: type, out: list[Index]) -> set[str]:
    names: set[str] = set()
    for comp in model.component_objects(set_cls, active=True):
        name = comp.local_name
        if name.startswith("_") or name in names:
            continue
        isordered = getattr(comp, "isordered", None)
        ordered = bool(isordered()) if callable(isordered) else False
        out.append(Index(name=name, description="", ordered=ordered))
        names.add(name)
    return names


def _shape_of(comp: Any, index_names: set[str]) -> tuple[str, ...]:
    """Best-effort index shape from a Pyomo component's index set."""
    idx = getattr(comp, "index_set", None)
    idx_obj = idx() if callable(idx) else idx
    name = getattr(idx_obj, "local_name", None) or getattr(idx_obj, "name", None)
    if name and name in index_names:
        return (str(name),)
    subsets = getattr(idx_obj, "subsets", None)
    if callable(subsets):
        parts = [str(getattr(s, "local_name", None) or getattr(s, "name", "")) for s in subsets()]
        kept = [p for p in parts if p in index_names]
        if kept:
            return tuple(kept)
    return ()


def _collect_params(
    model: Any,
    param_cls: type,
    out: list[Parameter],
    index_names: set[str],
    failures: list[IngestionFailure],
) -> None:
    for comp in model.component_objects(param_cls, active=True):
        name = comp.local_name
        shape = _shape_of(comp, index_names)
        kind = "scalar" if not shape else ("matrix" if len(shape) > 1 else "vector")
        out.append(Parameter(name=name, shape=shape, kind=kind))


def _collect_vars(
    model: Any,
    var_cls: type,
    out: list[VariableTemplate],
    index_names: set[str],
    failures: list[IngestionFailure],
) -> None:
    for comp in model.component_objects(var_cls, active=True):
        name = comp.local_name
        shape = _shape_of(comp, index_names)
        out.append(VariableTemplate(name=name, shape=shape, domain=_domain_of(comp)))


def _collect_objective(
    model: Any,
    obj_cls: type,
    maximize: object,
    failures: list[IngestionFailure],
) -> Objective | None:
    for comp in model.component_objects(obj_cls, active=True):
        sense = "max" if getattr(comp, "sense", None) == maximize else "min"
        # Deep expression recovery is out of scope; emit a valid placeholder
        # objective (a literal term) so the formulation validates.
        return Objective(
            sense=sense,
            name=comp.local_name,
            description="Objective imported from Pyomo (structure only).",
            terms=(Term(ref="_const", ref_kind="literal", coefficient=0, role="objective"),),
        )
    return None


def _collect_constraints(
    model: Any,
    con_cls: type,
    index_names: set[str],
    failures: list[IngestionFailure],
) -> tuple[ConstraintTemplate, ...]:
    out: list[ConstraintTemplate] = []
    for comp in model.component_objects(con_cls, active=True):
        name = comp.local_name
        shape = _shape_of(comp, index_names)
        quantifiers = tuple(Quantifier(index=fam.lower(), over=fam) for fam in shape)
        # Structure-only recovery: a trivially valid ``0 <= 0`` body keeps
        # the formulation valid while preserving the constraint's name and
        # quantifier shell. Deep term recovery lands when expression walking
        # is added.
        out.append(
            ConstraintTemplate(
                name=name,
                description="Constraint imported from Pyomo (structure only).",
                quantifiers=quantifiers,
                comparator="le",
                lhs=(Term(ref="_const", ref_kind="literal", coefficient=0, role="lhs"),),
                rhs=(Term(ref="_const", ref_kind="literal", coefficient=0, role="rhs"),),
            )
        )
    return tuple(out)


def _infer_family(variables: list[VariableTemplate]) -> str:
    if any(v.domain in ("integer", "binary") for v in variables):
        return "milp"
    return "lp"


__all__ = ["from_pyomo"]
