"""Controlled label vocabularies per (level, dimension) (M4).

A label is only meaningful against a *frozen, versioned* set of admissible
values. The taxonomy passes (M3) seed these sets — the cluster names a level
produces become the controlled vocabulary for that (level, dimension) — and
once seeded the set is frozen and versioned so that every label record can be
checked against, and replayed against, exactly the vocabulary in force when it
was written.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from lp2graph.mining.versions import LABEL_LEXICON_VERSION


@dataclass(frozen=True, slots=True)
class ControlledVocabulary:
    """The frozen set of admissible labels for one (level, dimension)."""

    level: str
    dimension: str
    labels: tuple[str, ...]
    version: str = LABEL_LEXICON_VERSION

    def __post_init__(self) -> None:
        if list(self.labels) != sorted(set(self.labels)):
            raise ValueError("ControlledVocabulary.labels must be sorted and unique")

    def __contains__(self, label: object) -> bool:
        return label in self.labels

    def __len__(self) -> int:
        return len(self.labels)


def seed_vocabulary(
    level: str,
    dimension: str,
    names: Iterable[str],
    *,
    version: str = LABEL_LEXICON_VERSION,
    include_unassigned: bool = True,
) -> ControlledVocabulary:
    """Seed a controlled vocabulary from M3 cluster names.

    ``names`` are typically the names of a taxonomy level's clusters. The
    explicit ``unassigned`` value is included by default so abstentions have a
    place to land.
    """
    labels = set(names)
    if include_unassigned:
        labels.add("unassigned")
    return ControlledVocabulary(
        level=level,
        dimension=dimension,
        labels=tuple(sorted(labels)),
        version=version,
    )


__all__ = ["ControlledVocabulary", "seed_vocabulary"]
