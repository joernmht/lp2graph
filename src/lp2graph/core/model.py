"""Canonical pydantic models for LP/MIP/MILP formulations.

Mirrors ``schema/canonical.schema.json`` one-to-one. Every public class
here corresponds to a ``$defs`` entry in the schema; field names are
identical. The canonical model is the *single source of truth* — every
view, metric, render, and export consumes a ``Formulation`` instance.

The model is deliberately conservative about what it stores: only what
cannot be derived. Anything that is a function of the canonical fields
(grounding, metrics, renders) is computed on demand.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
"""A Python-like identifier. Used for index, parameter, variable, and
constraint names."""


class _Frozen(BaseModel):
    """Base model — strict, frozen, forbid-extra. Determinism by default."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


# ---------------------------------------------------------------------------
# Index families and parameters
# ---------------------------------------------------------------------------


class Index(_Frozen):
    """An index family (set) over which templates may range.

    Examples: ``I`` (trains), ``T`` (time slots). An *ordered* index has
    a natural sequence so that offsets like ``t-1`` are meaningful. A
    *cyclic* index wraps modulo cardinality (PESP-style).
    """

    name: Identifier
    description: str = ""
    ordered: bool = False
    cyclic: bool = False


# Domain facet (additive): semantic class of a parameter, independent of 'kind'.
ParameterDomainClass = Literal[
    "cost_weight",
    "time_duration",
    "capacity",
    "demand",
    "network_structure",
    "penalty_bigM",
    "count_limit",
    "unclassified",
]


class Parameter(_Frozen):
    """A constant input to the formulation.

    Parameters carry a *shape* — the index families they are indexed by —
    and a *kind* tag that classifies them (e.g. ``big_m`` for tightening
    constants, ``tolerance`` for slacks). Concrete numeric values are
    *not* stored; they are supplied at grounding time when needed.
    """

    name: Identifier
    description: str = ""
    shape: tuple[Identifier, ...] = ()
    kind: Literal["scalar", "vector", "matrix", "big_m", "tolerance"] = "scalar"
    domain_class: ParameterDomainClass | None = None


# ---------------------------------------------------------------------------
# Variable templates
# ---------------------------------------------------------------------------


VariableDomain = Literal["continuous", "non_negative", "integer", "binary"]
VariableRole = Literal["primary", "auxiliary", "slack", "indicator"]
# Domain facet (additive): semantic role, independent of the structural 'role'.
VariableDomainRole = Literal[
    "selection_assignment",
    "ordering_precedence",
    "routing_path_column",
    "timing",
    "flow_quantity",
    "auxiliary_linearization",
    "unclassified",
]


class VariableTemplate(_Frozen):
    """A template for a family of decision variables.

    A template ``x[I, T]`` with ``domain="binary"`` represents the
    ``|I| * |T|`` binary variables ``x_{i,t}`` that appear in the
    grounded model. The schema view exposes the template; the ground
    view exposes the instances.
    """

    name: Identifier
    description: str = ""
    shape: tuple[Identifier, ...] = ()
    domain: VariableDomain
    lower: float | None = None
    upper: float | None = None
    role: VariableRole = "primary"
    domain_role: VariableDomainRole | None = None


# ---------------------------------------------------------------------------
# Quantifiers, bindings, terms
# ---------------------------------------------------------------------------


QuantifierRestriction = Literal[
    "none", "ne_other", "lt_other", "le_other", "gt_other", "ge_other", "ordered_pair"
]


class QuantifierWhere(_Frozen):
    """Attribute-based selection predicate on a quantifier.

    Restricts the tuples admitted by the quantifier to those for which a
    parameter (shaped over the quantifier's ``over`` index family)
    equals a given value. For example, with a binary parameter
    ``is_local`` of shape ``[T]``, ``QuantifierWhere(parameter="is_local",
    equals=True)`` keeps only the values of the index where
    ``is_local`` is true. Schema and hybrid views surface this as a
    label on the quantifier; the ground view applies it as a filter at
    materialization time.
    """

    parameter: Identifier
    equals: bool | int | float | str


class Quantifier(_Frozen):
    """A constraint-template quantifier: ``index ∈ over``.

    Optional ``restriction`` references another quantifier (via
    ``restriction_other``). For example, ``j ∈ I, j != i`` is encoded as
    ``Quantifier(index="j", over="I", restriction="ne_other",
    restriction_other="i")``.

    Optional ``where`` adds an attribute-based selection predicate
    (e.g. ``is_local[t] == True``).
    """

    index: Identifier
    over: Identifier
    restriction: QuantifierRestriction = "none"
    restriction_other: Identifier | None = None
    where: QuantifierWhere | None = None

    @model_validator(mode="after")
    def _check_restriction_pair(self) -> Quantifier:
        if self.restriction != "none" and self.restriction_other is None:
            raise ValueError(
                f"quantifier {self.index!r} has restriction {self.restriction!r} "
                "but no restriction_other"
            )
        if self.restriction == "none" and self.restriction_other is not None:
            raise ValueError(
                f"quantifier {self.index!r} sets restriction_other={self.restriction_other!r} "
                "but restriction is 'none'"
            )
        return self


class Binding(_Frozen):
    """The binding of one index slot of a referenced template.

    For a template ``x[I, T]`` referenced inside a constraint quantified
    over ``i ∈ I, t ∈ T``, the binding ``index="T", expr="t-1",
    offset=-1`` resolves to ``x_{i, t-1}``. The ``modulo`` field, when
    set to an index name, indicates that the offset should wrap modulo
    that index's cardinality (PESP).
    """

    index: Identifier
    expr: str
    offset: int = 0
    modulo: Identifier | None = None


TermRefKind = Literal["variable", "parameter", "literal"]
TermRole = Literal["lhs", "rhs", "objective", "slack", "aux"]
TermOperator = Literal["none", "sum", "max", "min", "abs", "indicator", "modulo"]


class Term(_Frozen):
    """A single term in a constraint LHS, constraint RHS, or objective.

    The four-tuple ``(ref, bindings, role, sign)`` is what makes the
    schema/hybrid/ground views derivable from a single source of truth.

    - ``ref`` names the referenced entity (variable, parameter, or
      literal).
    - ``bindings`` resolves each index slot of the referenced template
      to an expression in the enclosing quantifier scope.
    - ``coefficient`` is a parameter name or a numeric literal.
    - ``sign`` is multiplied with the coefficient at evaluation time but
      kept separate so renderers can show it explicitly.
    - ``role`` drives edge coloring in rendered graphs.
    - ``operator`` and ``operator_over`` capture aggregations like
      ``sum_{t in T}`` so they are visible in the schema view.

    For constant terms, prefer the ``constant`` shorthand
    (``{"constant": 3599, "role": "rhs"}``); it is normalized at parse
    time to a literal term whose ``coefficient`` carries the value.
    """

    ref: Identifier = "_const"
    ref_kind: TermRefKind = "variable"
    bindings: tuple[Binding, ...] = ()
    coefficient: float | str | None = 1
    sign: Literal[1, -1] = 1
    role: TermRole
    operator: TermOperator = "none"
    operator_over: tuple[Identifier, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _normalize_constant(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if "constant" not in data:
            return data
        if data.get("ref") is not None or data.get("ref_kind") not in (None, "literal"):
            raise ValueError(
                "term: 'constant' is mutually exclusive with 'ref'/'ref_kind' "
                "(other than ref_kind='literal')"
            )
        if "coefficient" in data and data["coefficient"] not in (None, 1):
            raise ValueError(
                "term: 'constant' is mutually exclusive with 'coefficient'; "
                "the constant's value is its own coefficient"
            )
        if data.get("bindings"):
            raise ValueError("term: constant term must not carry bindings")
        out = {k: v for k, v in data.items() if k != "constant"}
        out["ref"] = "_const"
        out["ref_kind"] = "literal"
        out["coefficient"] = data["constant"]
        return out


# ---------------------------------------------------------------------------
# Constraint and objective
# ---------------------------------------------------------------------------


Comparator = Literal["le", "ge", "eq"]
ConstraintKind = Literal[
    "linear",
    "big_m",
    "indicator",
    "ordering",
    "headway",
    "capacity",
    "flow_balance",
    "modulo",
    "soft",
    "robust",
    "set_packing",
    "block_occupation",
    "moving_block",
    "dwell",
]
# Domain facet (additive): semantic function, independent of structural 'kind'.
ConstraintDomainClass = Literal[
    "assignment_covering",
    "flow_conservation",
    "capacity_resource",
    "precedence_ordering",
    "headway_separation",
    "timing_window",
    "coupling_linking_definition",
    "periodic_modulo_pesp",
    "subtour_connectivity",
    "variable_bound_fix",
    "objective_defining",
    "unclassified",
]


class ConstraintTemplate(_Frozen):
    """A quantified constraint template.

    The template's body is a comparison ``Σ lhs ⋄ Σ rhs`` where ``⋄`` is
    one of ``≤``, ``≥``, ``=``. Each side is a list of :class:`Term`
    instances; the side they appear in determines their default role,
    but a term may carry its own role override (e.g. a slack term
    appearing in the LHS of a soft constraint).
    """

    name: Identifier
    description: str = ""
    quantifiers: tuple[Quantifier, ...] = ()
    comparator: Comparator
    lhs: tuple[Term, ...]
    rhs: tuple[Term, ...]
    kind: ConstraintKind = "linear"
    domain_class: ConstraintDomainClass | None = None


ObjectiveSense = Literal["min", "max"]
ObjectiveCombination = Literal["sum", "lexicographic", "weighted_sum"]


class Objective(_Frozen):
    """The objective function as a first-class section.

    Mirrors the structure of constraints but without quantifiers (the
    objective itself is scalar; its terms may carry ``sum`` operators
    over index families to express ``min Σ_i c_i x_i``).
    """

    sense: ObjectiveSense
    name: str = "objective"
    description: str = ""
    terms: tuple[Term, ...]
    combination: ObjectiveCombination = "sum"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class Provenance(_Frozen):
    """Optional metadata about where the formulation came from."""

    source: str = ""
    reference: str = ""
    author: str = ""
    date: str = ""


# ---------------------------------------------------------------------------
# Formulation
# ---------------------------------------------------------------------------


Family = Literal["lp", "mip", "milp"]


class Formulation(_Frozen):
    """The canonical container.

    A ``Formulation`` is the input to every view, metric, render, and
    export in the library.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")]
    name: str
    family: Family
    description: str = ""
    tags: tuple[str, ...] = ()
    provenance: Provenance | None = None
    indices: tuple[Index, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    variables: tuple[VariableTemplate, ...]
    constraints: tuple[ConstraintTemplate, ...] = ()
    objective: Objective | None = None

    # Convenience indexes for fast lookups -------------------------------

    def index_map(self) -> dict[str, Index]:
        return {i.name: i for i in self.indices}

    def parameter_map(self) -> dict[str, Parameter]:
        return {p.name: p for p in self.parameters}

    def variable_map(self) -> dict[str, VariableTemplate]:
        return {v.name: v for v in self.variables}

    def constraint_map(self) -> dict[str, ConstraintTemplate]:
        return {c.name: c for c in self.constraints}


__all__ = [
    "Binding",
    "Comparator",
    "ConstraintKind",
    "ConstraintTemplate",
    "Family",
    "Formulation",
    "Identifier",
    "Index",
    "Objective",
    "ObjectiveCombination",
    "ObjectiveSense",
    "Parameter",
    "Provenance",
    "Quantifier",
    "QuantifierRestriction",
    "QuantifierWhere",
    "Term",
    "TermOperator",
    "TermRefKind",
    "TermRole",
    "VariableDomain",
    "VariableRole",
    "VariableTemplate",
]


# Union type for term references (variable templates or parameters).
TermReferent = VariableTemplate | Parameter
