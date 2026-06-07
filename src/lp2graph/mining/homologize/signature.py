"""Type signatures ``τ(s)`` read from the canonical model (M2).

Lexical concepts capture what an entity is *called*; the type signature
captures what it *is*, structurally — its domain/role facets, its shape over
index families, its kind, and (for constraints) its quantifier structure.
Signatures are read directly from the canonical ``Formulation`` (the single
source of truth), so they are exact rather than inferred, and they give the
clustering passes a structural feature channel alongside the lexical one.

A signature exposes a stable :meth:`TypeSignature.canonical` string so it can
be hashed, compared, or turned into a categorical feature deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass

from lp2graph.core.model import (
    ConstraintTemplate,
    Formulation,
    Objective,
    Parameter,
    VariableTemplate,
)


@dataclass(frozen=True, slots=True)
class TypeSignature:
    """The structural signature of one entity.

    Fields mirror the canonical model's additive facets:

    - ``domain`` — the semantic facet (``domain_role`` for variables,
      ``domain_class`` for parameters/constraints), ``""`` if unset.
    - ``role`` — the structural role (variable role; ``"parameter"`` /
      ``"constraint"`` / ``"objective"`` / ``"model"`` for the others).
    - ``kind`` — the declarative kind (variable domain, parameter kind,
      constraint kind, objective sense/combination, or model family).
    - ``shape`` — the index families the entity ranges over.
    - ``quantifiers`` — for constraints, the quantifier index/over/restriction
      pattern; empty otherwise.
    - ``comparator`` — for constraints, the comparison operator (``le`` /
      ``ge`` / ``eq``); ``""`` otherwise. Part of the paper's constraint
      signature ``τ`` (Eq. homologization, Sec. methodology).
    - ``referents`` — for constraints, the multiset of referent kinds
      (``variable`` / ``parameter`` / ``literal``) appearing in the term
      lists, as a sorted tuple with repetition; empty otherwise. Also part of
      the paper's constraint ``τ``.
    """

    domain: str
    role: str
    kind: str
    shape: tuple[str, ...]
    quantifiers: tuple[str, ...]
    comparator: str = ""
    referents: tuple[str, ...] = ()

    @property
    def arity(self) -> int:
        """Number of index families the entity ranges over."""
        return len(self.shape)

    def canonical(self) -> str:
        """A stable, deterministic string form of the signature."""
        shape = ",".join(self.shape)
        quant = ",".join(self.quantifiers)
        refs = ",".join(self.referents)
        return (
            f"domain={self.domain}|role={self.role}|kind={self.kind}"
            f"|shape=[{shape}]|quant=[{quant}]|cmp={self.comparator}|refs=[{refs}]"
        )


def variable_signature(v: VariableTemplate) -> TypeSignature:
    """Signature of a variable template."""
    return TypeSignature(
        domain=v.domain_role or "",
        role=v.role,
        kind=v.domain,
        shape=tuple(v.shape),
        quantifiers=(),
    )


def parameter_signature(p: Parameter) -> TypeSignature:
    """Signature of a parameter."""
    return TypeSignature(
        domain=p.domain_class or "",
        role="parameter",
        kind=p.kind,
        shape=tuple(p.shape),
        quantifiers=(),
    )


def _quantifier_tokens(c: ConstraintTemplate) -> tuple[str, ...]:
    tokens: list[str] = []
    for q in c.quantifiers:
        token = f"{q.index}:{q.over}"
        if q.restriction != "none":
            token += f":{q.restriction}"
        tokens.append(token)
    return tuple(tokens)


def _referent_multiset(c: ConstraintTemplate) -> tuple[str, ...]:
    """The sorted multiset of referent kinds across the constraint's terms.

    Realizes the ``multiset of referent kinds in its terms`` component of the
    paper's constraint type signature ``τ`` (Eq. homologization).
    """
    kinds = [t.ref_kind for t in (*c.lhs, *c.rhs)]
    return tuple(sorted(kinds))


def constraint_signature(c: ConstraintTemplate) -> TypeSignature:
    """Signature of a constraint template.

    Mirrors the paper's ``τ(constraint)`` — the comparator, the
    quantifier/restriction structure, and the multiset of referent kinds in
    its terms — while also retaining the declarative ``kind`` and
    ``domain_class`` facets the lp2graph model adds.
    """
    shape = tuple(q.over for q in c.quantifiers)
    return TypeSignature(
        domain=c.domain_class or "",
        role="constraint",
        kind=c.kind,
        shape=shape,
        quantifiers=_quantifier_tokens(c),
        comparator=c.comparator,
        referents=_referent_multiset(c),
    )


def objective_signature(o: Objective) -> TypeSignature:
    """Signature of the objective section."""
    return TypeSignature(
        domain="objective_defining",
        role="objective",
        kind=f"{o.sense}/{o.combination}",
        shape=(),
        quantifiers=(),
    )


def model_signature(f: Formulation) -> TypeSignature:
    """Whole-model signature (Level M): family + index-family shape."""
    return TypeSignature(
        domain="",
        role="model",
        kind=f.family,
        shape=tuple(i.name for i in f.indices),
        quantifiers=(),
    )


__all__ = [
    "TypeSignature",
    "constraint_signature",
    "model_signature",
    "objective_signature",
    "parameter_signature",
    "variable_signature",
]
