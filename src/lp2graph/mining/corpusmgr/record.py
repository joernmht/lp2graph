"""Provenance records for corpus entries (M5).

A :class:`ProvenanceRecord` is the bibliographic + categorization sidecar
for one extracted :class:`~lp2graph.core.model.Formulation`. It captures the
fields the corpus & provenance manager needs to deduplicate and to select a
representative per cluster: *where* a formulation came from (``source_id``,
``venue``, ``year``), *how strong* the citation signal is at the freeze date
(``citation_count``, ``quality_tier``), and *where it sits* in the priority
matrix (``domain_shell``, ``activity``, ``priority_cell``).

Like the other mining records, this is a dependency-free frozen dataclass:
it describes provenance *about* a formulation, not the formulation itself.
Every field is an explicit input — ``citation_count`` is the count *at the
freeze date*, never fetched at runtime — so a record is a reproducible,
diffable artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

#: Quality tier of a publication venue, used to break selection ties.
QualityTier = Literal["A_star", "A", "B", "C", "preprint", "unranked"]

#: Quality tiers ordered best -> worst. The index of a tier in this tuple is
#: its rank; lower is better. Used by dedup/selection tie-breaks so that the
#: ordering is explicit and deterministic.
QUALITY_TIERS: Final[tuple[QualityTier, ...]] = (
    "A_star",
    "A",
    "B",
    "C",
    "preprint",
    "unranked",
)

#: Priority cell of the sampling matrix (``P1`` highest priority .. ``P5``).
PriorityCell = Literal["P1", "P2", "P3", "P4", "P5"]

#: The valid priority cells, highest -> lowest.
PRIORITY_CELLS: Final[tuple[PriorityCell, ...]] = ("P1", "P2", "P3", "P4", "P5")


def quality_rank(tier: QualityTier) -> int:
    """Return the rank of ``tier`` (0 = best). Unknown tiers sort last."""
    try:
        return QUALITY_TIERS.index(tier)
    except ValueError:
        return len(QUALITY_TIERS)


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Bibliographic + categorization provenance for one corpus entry.

    ``source_id`` is a stable identifier for the source artifact (typically
    the repository or paper id, matching the canonical formulation ``id``).
    ``venue`` is the publication / repository venue; ``quality_tier`` ranks
    it (see :data:`QUALITY_TIERS`). ``year`` is the publication year (or
    ``None`` when unknown). ``citation_count`` is the citation count *as
    measured at the corpus freeze date* — it is an input, never fetched.

    ``domain_shell`` and ``activity`` place the entry in the domain
    taxonomy; ``priority_cell`` is its cell in the sampling-priority matrix
    (one of :data:`PRIORITY_CELLS`).
    """

    source_id: str
    venue: str
    quality_tier: QualityTier
    year: int | None
    citation_count: int
    domain_shell: str
    activity: str
    priority_cell: PriorityCell

    def __post_init__(self) -> None:
        if self.priority_cell not in PRIORITY_CELLS:
            raise ValueError(
                f"priority_cell {self.priority_cell!r} is not one of {PRIORITY_CELLS!r}"
            )
        if self.quality_tier not in QUALITY_TIERS:
            raise ValueError(f"quality_tier {self.quality_tier!r} is not one of {QUALITY_TIERS!r}")
        if self.citation_count < 0:
            raise ValueError("citation_count must be non-negative")

    @property
    def quality_rank(self) -> int:
        """Rank of this record's quality tier (0 = best)."""
        return quality_rank(self.quality_tier)


__all__ = [
    "PRIORITY_CELLS",
    "QUALITY_TIERS",
    "PriorityCell",
    "ProvenanceRecord",
    "QualityTier",
    "quality_rank",
]
