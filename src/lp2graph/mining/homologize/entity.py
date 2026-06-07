"""The mineable *entity* abstraction (M2, shared with M3/M4).

The taxonomy passes operate on *entities*: at Level V the decision variables
and parameters, at Level C the constraints and the objective, at Level M the
whole model. Each entity carries both channels the method needs:

- ``text`` — the name and description, fed to the lexical homologizer to
  produce a concept bag / TF-IDF vector;
- ``signature`` — the structural :class:`~lp2graph.mining.homologize.signature.TypeSignature`
  read from the canonical model.

This module is the single place that walks a ``Formulation`` and emits
entities, so clustering and labeling consume one stable, ordered view.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from lp2graph.core.model import Formulation
from lp2graph.mining.homologize.signature import (
    TypeSignature,
    constraint_signature,
    model_signature,
    objective_signature,
    parameter_signature,
    variable_signature,
)

EntityLevel = Literal["V", "C", "M"]


@dataclass(frozen=True, slots=True)
class Entity:
    """One mineable unit at some taxonomy level.

    ``id`` is unique within a corpus (``"<formulation>::<dimension>::<name>"``).
    ``dimension`` records which kind of entity this is (``variable``,
    ``parameter``, ``constraint``, ``objective``, ``model``). ``text`` is the
    lexical channel; ``signature`` is the structural channel; ``tags`` carries
    any extra free text used by the one-dimensional text clusterings.
    """

    id: str
    formulation_id: str
    level: EntityLevel
    dimension: str
    name: str
    text: str
    signature: TypeSignature
    tags: tuple[str, ...] = field(default_factory=tuple)


def _entity_id(formulation_id: str, dimension: str, name: str) -> str:
    return f"{formulation_id}::{dimension}::{name}"


def level_v_entities(f: Formulation) -> list[Entity]:
    """Level-V entities: decision variables then parameters (declaration order)."""
    out: list[Entity] = []
    for v in f.variables:
        out.append(
            Entity(
                id=_entity_id(f.id, "variable", v.name),
                formulation_id=f.id,
                level="V",
                dimension="variable",
                name=v.name,
                text=f"{v.name} {v.description}".strip(),
                signature=variable_signature(v),
            )
        )
    for p in f.parameters:
        out.append(
            Entity(
                id=_entity_id(f.id, "parameter", p.name),
                formulation_id=f.id,
                level="V",
                dimension="parameter",
                name=p.name,
                text=f"{p.name} {p.description}".strip(),
                signature=parameter_signature(p),
            )
        )
    return out


def level_c_entities(f: Formulation) -> list[Entity]:
    """Level-C entities: constraints then the objective (if present)."""
    out: list[Entity] = []
    for c in f.constraints:
        out.append(
            Entity(
                id=_entity_id(f.id, "constraint", c.name),
                formulation_id=f.id,
                level="C",
                dimension="constraint",
                name=c.name,
                text=f"{c.name} {c.description}".strip(),
                signature=constraint_signature(c),
            )
        )
    if f.objective is not None:
        out.append(
            Entity(
                id=_entity_id(f.id, "objective", f.objective.name),
                formulation_id=f.id,
                level="C",
                dimension="objective",
                name=f.objective.name,
                text=f"{f.objective.name} {f.objective.description}".strip(),
                signature=objective_signature(f.objective),
            )
        )
    return out


def level_m_entity(f: Formulation) -> Entity:
    """The single Level-M entity for the whole model.

    Its ``text`` pools the model name, description, and tags (the lexical
    signal for the one-dimensional *domain* / *solution approach* text
    clusterings); ``tags`` is preserved separately for those dimensions.
    """
    text = " ".join(part for part in (f.name, f.description, *f.tags) if part).strip()
    return Entity(
        id=_entity_id(f.id, "model", f.id),
        formulation_id=f.id,
        level="M",
        dimension="model",
        name=f.name,
        text=text,
        signature=model_signature(f),
        tags=tuple(f.tags),
    )


def entities(f: Formulation, level: EntityLevel) -> list[Entity]:
    """Return the entities of ``f`` at ``level`` (``"V"``, ``"C"``, or ``"M"``)."""
    if level == "V":
        return level_v_entities(f)
    if level == "C":
        return level_c_entities(f)
    return [level_m_entity(f)]


def corpus_entities(formulations: Iterable[Formulation], level: EntityLevel) -> list[Entity]:
    """Flatten the entities of many formulations at one ``level``.

    Order is deterministic: formulations in the given order, entities in
    declaration order within each.
    """
    out: list[Entity] = []
    for f in formulations:
        out.extend(entities(f, level))
    return out


def text_dimension(entity: Entity, dimension: Literal["domain", "solution_approach"]) -> str:
    """Return the text for a one-dimensional model-level text clustering.

    Both dimensions are derived from the Level-M entity's available free text;
    ``domain`` favors the tags + description, ``solution_approach`` favors the
    description prose. The canonical model does not separate these fields, so
    the split is a documented heuristic over the same source text.
    """
    if entity.level != "M":  # pragma: no cover - guarded by callers
        raise ValueError("text dimensions are only defined for Level-M entities")
    if dimension == "domain":
        return " ".join((*entity.tags, entity.text)).strip()
    return entity.text


def signature_documents(items: Sequence[Entity]) -> list[dict[str, int]]:
    """Turn each entity's signature into a categorical concept-count document.

    Lets the structural channel be vectorized by the same TF-IDF machinery as
    the lexical channel: each signature facet becomes a namespaced concept
    token (``role:auxiliary``, ``kind:binary``, ``domain:timing``, ...).
    """
    docs: list[dict[str, int]] = []
    for e in items:
        sig = e.signature
        tokens: list[str] = []
        if sig.domain:
            tokens.append(f"domain:{sig.domain}")
        tokens.append(f"role:{sig.role}")
        tokens.append(f"kind:{sig.kind}")
        tokens.append(f"arity:{sig.arity}")
        tokens.extend(f"over:{s}" for s in sig.shape)
        doc: dict[str, int] = {}
        for tok in tokens:
            doc[tok] = doc.get(tok, 0) + 1
        docs.append(doc)
    return docs


__all__ = [
    "Entity",
    "EntityLevel",
    "corpus_entities",
    "entities",
    "level_c_entities",
    "level_m_entity",
    "level_v_entities",
    "signature_documents",
    "text_dimension",
]
