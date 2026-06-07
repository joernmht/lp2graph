"""Thin corpus & provenance manager facade (M5).

:class:`CorpusManager` ties the pieces together: it holds the regeneration
:class:`~lp2graph.mining.corpusmgr.manifest.CorpusManifest` plus the list of
``(Formulation, ProvenanceRecord)`` entries, and exposes the deterministic
operations (deduplicate, representative selection) and the manifest
(de)serialization that make the corpus *"regenerable from queries + freeze
date"*. It deliberately stays thin — all logic lives in the dedicated
modules.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from lp2graph.core.model import Formulation
from lp2graph.mining.corpusmgr.dedup import DedupResult, deduplicate
from lp2graph.mining.corpusmgr.manifest import CorpusManifest
from lp2graph.mining.corpusmgr.record import ProvenanceRecord
from lp2graph.mining.corpusmgr.select import (
    RepresentativeChoice,
    select_representatives,
)


@dataclass(frozen=True, slots=True)
class CorpusManager:
    """A corpus = a regeneration manifest + provenance-tagged formulations."""

    manifest: CorpusManifest
    entries: tuple[tuple[Formulation, ProvenanceRecord], ...] = field(default_factory=tuple)

    @classmethod
    def build(
        cls,
        manifest: CorpusManifest,
        entries: Iterable[tuple[Formulation, ProvenanceRecord]],
    ) -> CorpusManager:
        """Construct a manager from a manifest and an iterable of entries."""
        return cls(manifest=manifest, entries=tuple(entries))

    @property
    def records(self) -> tuple[ProvenanceRecord, ...]:
        """The provenance records, positionally aligned with :attr:`entries`."""
        return tuple(r for _, r in self.entries)

    def deduplicate(self) -> DedupResult:
        """Deterministically deduplicate the corpus entries."""
        return deduplicate(self.entries)

    def representatives(
        self,
        clusters: Mapping[str, Sequence[int]],
        *,
        benchmark_fallback: Mapping[str, int] | None = None,
    ) -> dict[str, RepresentativeChoice]:
        """Pick a reproducible representative per named cluster."""
        return select_representatives(clusters, self.records, benchmark_fallback=benchmark_fallback)

    def to_manifest_dict(self) -> dict[str, Any]:
        """Serialize the regeneration manifest to a plain dict."""
        return self.manifest.to_dict()

    @classmethod
    def from_manifest_dict(
        cls,
        data: dict[str, Any],
        entries: Iterable[tuple[Formulation, ProvenanceRecord]] = (),
    ) -> CorpusManager:
        """Rebuild a manager from a serialized manifest (+ optional entries)."""
        return cls(
            manifest=CorpusManifest.from_dict(data),
            entries=tuple(entries),
        )


__all__ = ["CorpusManager"]
