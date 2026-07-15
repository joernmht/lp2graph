"""The grounded-model hub every interop importer and exporter goes through.

``code -> graph`` and ``graph -> code`` conversions meet in one flat,
numeric intermediate: :class:`GroundedModel`. Importers (gurobipy, PuLP,
Pyomo, LP, MPS, GAMS, AMPL, JuMP) translate their source into a
``GroundedModel`` and promote it to a canonical
:class:`~lp2graph.core.model.Formulation` with :func:`to_formulation`.
Exporters call :func:`ground` on any formulation (flat ones directly and
deterministically; template-level ones through the PuLP grounder with an
:class:`~lp2graph.solve.instance.Instance`) and emit the target language
from the same struct.

Everything here is deterministic: dataclasses are frozen, orderings are
insertion orderings, and name sanitization is a pure function of the
input sequence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from lp2graph.core.model import (
    ConstraintTemplate,
    Formulation,
    Objective,
    Term,
    VariableTemplate,
)
from lp2graph.core.validate import validate
from lp2graph.solve.instance import Instance

__all__ = [
    "GroundedConstraint",
    "GroundedModel",
    "GroundedVar",
    "InteropError",
    "NameMap",
    "ground",
    "grounded_from_pulp",
    "to_formulation",
]


class InteropError(Exception):
    """A model cannot be converted faithfully (unsupported feature or
    malformed input). The message names the offending construct; nothing
    is silently dropped."""


# ---------------------------------------------------------------------------
# The hub struct
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroundedVar:
    """One scalar decision variable of a grounded model."""

    name: str
    domain: str  # VariableDomain: continuous | non_negative | integer | binary
    lower: float | None = None
    upper: float | None = None


@dataclass(frozen=True)
class GroundedConstraint:
    """One scalar linear constraint: ``sum(coef * var) <cmp> rhs``."""

    name: str
    terms: tuple[tuple[float, str], ...]  # (coefficient, variable name)
    comparator: str  # le | ge | eq
    rhs: float


@dataclass(frozen=True)
class GroundedModel:
    """A flat, fully numeric LP/MILP: the interop interchange struct."""

    id: str
    name: str
    sense: str  # min | max
    variables: tuple[GroundedVar, ...]
    objective: tuple[tuple[float, str], ...]  # (coefficient, variable name)
    objective_constant: float = 0.0
    constraints: tuple[GroundedConstraint, ...] = ()

    def variable_names(self) -> tuple[str, ...]:
        return tuple(v.name for v in self.variables)


# ---------------------------------------------------------------------------
# Name sanitization
# ---------------------------------------------------------------------------

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class NameMap:
    """Deterministic source-name -> canonical-identifier mapping.

    Sanitizes arbitrary solver names (``x(1,2)``, ``flow[a,b]``) into
    canonical identifiers, disambiguating collisions with numeric
    suffixes in first-come order.
    """

    used: set[str] = field(default_factory=set)
    by_source: dict[str, str] = field(default_factory=dict)

    def get(self, source_name: str, *, fallback: str) -> str:
        if source_name in self.by_source:
            return self.by_source[source_name]
        base = _sanitize(source_name) or fallback
        cand = base
        n = 2
        while cand in self.used:
            cand = f"{base}_{n}"
            n += 1
        self.used.add(cand)
        self.by_source[source_name] = cand
        return cand


def _sanitize(name: str) -> str:
    if _IDENT.match(name):
        return name
    out = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name)
    if out and out[0].isdigit():
        out = "_" + out
    return out.strip() if _IDENT.match(out) else ""


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9_.-]+", "_", name.lower()).strip("_")
    return s or "model"


_HEADER_ID = re.compile(r"lp2graph model (\S+)")


def header_model_id(text: str, fallback: str) -> str:
    """Recover the model id a lp2graph emitter stamped into its header
    comment, so text formats without an intrinsic model name (LP, AMPL,
    JuMP) round-trip their identity."""
    m = _HEADER_ID.search(text)
    return m.group(1) if m else fallback


# ---------------------------------------------------------------------------
# GroundedModel -> canonical Formulation
# ---------------------------------------------------------------------------


def to_formulation(
    gm: GroundedModel,
    *,
    description: str = "",
    source: str = "",
) -> Formulation:
    """Promote a grounded model to a validated canonical ``Formulation``.

    The result is *flat*: scalar variable templates, unquantified
    constraints, numeric coefficients. It grounds back through
    :func:`ground` without an instance, which is what makes
    ``code -> graph -> code`` round-trips closed.
    """
    names = NameMap()
    vmap = {v.name: names.get(v.name, fallback=f"x{i + 1}") for i, v in enumerate(gm.variables)}

    variables = tuple(
        VariableTemplate(
            name=vmap[v.name],
            domain=_canonical_domain(v),
            lower=_canonical_lower(v),
            upper=v.upper,
        )
        for v in gm.variables
    )

    cnames = NameMap(used=set(names.used))
    constraints = tuple(
        ConstraintTemplate(
            name=cnames.get(c.name, fallback=f"c{k + 1}"),
            comparator=_comparator(c.comparator),
            lhs=_terms(c.terms, vmap, role="lhs") or (_const_term(0.0, "lhs"),),
            rhs=(_const_term(c.rhs, "rhs"),),
        )
        for k, c in enumerate(gm.constraints)
    )

    obj_terms = _terms(gm.objective, vmap, role="objective")
    if gm.objective_constant or not obj_terms:
        obj_terms += (_const_term(gm.objective_constant, "objective"),)
    objective = Objective(sense=_sense(gm.sense), name="objective", terms=obj_terms)

    family = "milp" if any(v.domain in ("integer", "binary") for v in variables) else "lp"
    f = Formulation(
        id=_slug(gm.id),
        name=gm.name or gm.id,
        family=family,
        description=description or (f"Imported from {source}." if source else ""),
        variables=variables,
        constraints=constraints,
        objective=objective,
    )
    validate(f)
    return f


def _canonical_domain(v: GroundedVar) -> str:
    if v.domain == "continuous" and v.lower == 0:
        return "non_negative"
    return v.domain


def _canonical_lower(v: GroundedVar) -> float | None:
    if v.domain == "binary":
        return None
    if v.domain == "continuous" and v.lower == 0:
        return None  # implied by non_negative
    return v.lower


def _sense(s: str) -> str:
    if s not in ("min", "max"):
        raise InteropError(f"unknown objective sense {s!r}")
    return s


def _comparator(c: str) -> str:
    if c not in ("le", "ge", "eq"):
        raise InteropError(f"unknown comparator {c!r}")
    return c


def _terms(
    pairs: tuple[tuple[float, str], ...], vmap: dict[str, str], *, role: str
) -> tuple[Term, ...]:
    out: list[Term] = []
    for coef, var in pairs:
        if var not in vmap:
            raise InteropError(f"term references undeclared variable {var!r}")
        out.append(
            Term(
                ref=vmap[var],
                ref_kind="variable",
                coefficient=abs(coef),
                sign=-1 if coef < 0 else 1,
                role=role,
            )
        )
    return tuple(out)


def _const_term(value: float, role: str) -> Term:
    return Term(
        ref="_const",
        ref_kind="literal",
        coefficient=abs(value),
        sign=-1 if value < 0 else 1,
        role=role,
    )


# ---------------------------------------------------------------------------
# Formulation -> GroundedModel
# ---------------------------------------------------------------------------


def ground(f: Formulation, instance: Instance | None = None) -> GroundedModel:
    """Ground a formulation into the flat interchange struct.

    A *flat* formulation (scalar variables, unquantified constraints,
    numeric coefficients) is grounded directly with no third-party
    dependency. A template-level formulation is grounded through the
    PuLP grounder, which requires ``pulp`` and an ``instance`` carrying
    cardinalities and parameter values.
    """
    if _is_flat(f):
        return _ground_flat(f, instance)
    from lp2graph.solve.grounder import build_problem  # requires pulp

    prob, _ = build_problem(f, instance or Instance(cardinalities={}))
    return grounded_from_pulp(prob, model_id=f.id, model_name=f.name)


def _is_flat(f: Formulation) -> bool:
    if f.indices:
        return False
    if any(v.shape for v in f.variables):
        return False
    all_terms: list[Term] = []
    for c in f.constraints:
        if c.quantifiers or c.indicator is not None:
            return False
        all_terms.extend(c.lhs)
        all_terms.extend(c.rhs)
    if f.objective is not None:
        if f.objective.combination == "lexicographic":
            return False
        all_terms.extend(f.objective.terms)
    for t in all_terms:
        if t.bindings or t.operator != "none":
            return False
        if isinstance(t.coefficient, str):
            return False
        if t.ref_kind == "parameter":
            return False
    return True


def _ground_flat(f: Formulation, instance: Instance | None) -> GroundedModel:
    del instance  # flat models need no instance data
    variables = tuple(
        GroundedVar(
            name=v.name,
            domain=v.domain,
            lower=0.0 if (v.domain == "non_negative" and v.lower is None) else v.lower,
            upper=v.upper,
        )
        for v in f.variables
    )
    vnames = {v.name for v in variables}

    constraints: list[GroundedConstraint] = []
    for c in f.constraints:
        coefs, lhs_const = _accumulate(c.lhs, vnames)
        rcoefs, rhs_const = _accumulate(c.rhs, vnames)
        for var, coef in rcoefs.items():
            coefs[var] = coefs.get(var, 0.0) - coef
        constraints.append(
            GroundedConstraint(
                name=c.name,
                terms=tuple((coef, var) for var, coef in coefs.items() if coef != 0),
                comparator=c.comparator,
                rhs=rhs_const - lhs_const,
            )
        )

    sense = "min"
    obj: dict[str, float] = {}
    obj_const = 0.0
    if f.objective is not None:
        sense = f.objective.sense
        obj, obj_const = _accumulate(f.objective.terms, vnames)
    return GroundedModel(
        id=f.id,
        name=f.name,
        sense=sense,
        variables=variables,
        objective=tuple((coef, var) for var, coef in obj.items() if coef != 0),
        objective_constant=obj_const,
        constraints=tuple(constraints),
    )


def _accumulate(terms: tuple[Term, ...], vnames: set[str]) -> tuple[dict[str, float], float]:
    """Fold one side's terms into (variable coefficients, sum of literals).

    The caller normalizes ``lhs <cmp> rhs`` by subtracting RHS variable
    coefficients from the LHS and LHS literals from the RHS.
    """
    coefs: dict[str, float] = {}
    const = 0.0
    for t in terms:
        value = float(t.coefficient if t.coefficient is not None else 1) * t.sign
        if t.ref_kind == "literal":
            const += value
        elif t.ref_kind == "variable":
            if t.ref not in vnames:
                raise InteropError(f"term references undeclared variable {t.ref!r}")
            coefs[t.ref] = coefs.get(t.ref, 0.0) + value
        else:  # pragma: no cover - _is_flat filters parameter refs
            raise InteropError(f"cannot ground term with ref_kind {t.ref_kind!r} directly")
    return coefs, const


# ---------------------------------------------------------------------------
# pulp.LpProblem -> GroundedModel (shared by ground() and interop.pulp_io)
# ---------------------------------------------------------------------------

_PULP_CMP = {-1: "le", 0: "eq", 1: "ge"}


def grounded_from_pulp(
    prob: object, *, model_id: str | None = None, model_name: str | None = None
) -> GroundedModel:
    """Read a ``pulp.LpProblem`` into the flat interchange struct."""
    import pulp

    if not isinstance(prob, pulp.LpProblem):
        raise InteropError(f"expected pulp.LpProblem, got {type(prob).__name__}")

    variables = tuple(_pulp_var(v) for v in prob.variables())
    sense = "max" if prob.sense == pulp.LpMaximize else "min"

    obj_terms: tuple[tuple[float, str], ...] = ()
    obj_const = 0.0
    if prob.objective is not None:
        obj_terms = tuple((float(coef), v.name) for v, coef in prob.objective.items())
        obj_const = float(prob.objective.constant)

    constraints = []
    for cname, con in prob.constraints.items():
        constraints.append(
            GroundedConstraint(
                name=cname,
                terms=tuple((float(coef), v.name) for v, coef in con.items()),
                comparator=_PULP_CMP[con.sense],
                rhs=-float(con.constant),
            )
        )

    raw = model_id or prob.name or "pulp_model"
    return GroundedModel(
        id=_slug(str(raw)),
        name=model_name or str(prob.name or raw),
        sense=sense,
        variables=variables,
        objective=obj_terms,
        objective_constant=obj_const,
        constraints=tuple(constraints),
    )


def _pulp_var(v: object) -> GroundedVar:
    import pulp

    assert isinstance(v, pulp.LpVariable)
    if v.cat == pulp.LpBinary or (v.cat == pulp.LpInteger and v.lowBound == 0 and v.upBound == 1):
        return GroundedVar(name=v.name, domain="binary", lower=0.0, upper=1.0)
    domain = "integer" if v.cat == pulp.LpInteger else "continuous"
    return GroundedVar(
        name=v.name,
        domain=domain,
        lower=None if v.lowBound is None else float(v.lowBound),
        upper=None if v.upBound is None else float(v.upBound),
    )


def format_number(x: float) -> str:
    """Render a coefficient deterministically: integral floats as ints."""
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return repr(float(x))


def py_linexpr(terms: tuple[tuple[float, str], ...], constant: float) -> str:
    """Render an affine expression as Python source over a ``v[...]`` dict.

    Shared by the gurobipy/PuLP/Pyomo code emitters so generated scripts
    format expressions identically.
    """
    parts: list[str] = []
    for coef, var in terms:
        ref = f"v[{var!r}]"
        mag = abs(coef)
        piece = ref if mag == 1 else f"{format_number(mag)} * {ref}"
        if not parts:
            parts.append(f"-{piece}" if coef < 0 else piece)
        else:
            parts.append(f"{'-' if coef < 0 else '+'} {piece}")
    if constant:
        parts.append(
            f"{'-' if constant < 0 else '+'} {format_number(abs(constant))}"
            if parts
            else format_number(constant)
        )
    return " ".join(parts) if parts else "0"


def parameter_values(instance: Instance | None) -> Mapping[str, object]:
    return instance.parameters if instance is not None else {}
