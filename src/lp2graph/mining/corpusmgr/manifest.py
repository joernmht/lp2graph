"""The corpus regeneration manifest (M5).

The acceptance criterion for the corpus manager is *"corpus regenerable from
queries + freeze date"*. A :class:`CorpusManifest` is exactly that record:
the literal query strings that were issued and the frozen search date they
were issued against. Given the manifest, re-running the same queries at the
same freeze date reproduces the same candidate set — so the manifest is the
reproducible provenance of the whole corpus, not of any single entry.

It is a dependency-free frozen dataclass with a plain-``dict`` (JSON
round-trippable) serialization so it can be stored alongside the extracted
JSON and diffed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Bumped when the on-disk manifest dict layout changes.
MANIFEST_SCHEMA_VERSION = "1"


@dataclass(frozen=True, slots=True)
class CorpusManifest:
    """The reproducible record of *what was searched* to build the corpus.

    ``frozen_search_date`` is the ISO-8601 date the searches were frozen at
    (an input string, never ``today``). ``queries`` is the ordered, literal
    tuple of query strings issued. Together they make the candidate set
    regenerable.
    """

    frozen_search_date: str
    queries: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.frozen_search_date:
            raise ValueError("frozen_search_date must be a non-empty ISO date string")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain, JSON-round-trippable dict."""
        return {
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
            "frozen_search_date": self.frozen_search_date,
            "queries": list(self.queries),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorpusManifest:
        """Reconstruct a manifest from its :meth:`to_dict` form."""
        version = data.get("manifest_schema_version", MANIFEST_SCHEMA_VERSION)
        if version != MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported manifest_schema_version {version!r} "
                f"(expected {MANIFEST_SCHEMA_VERSION!r})"
            )
        return cls(
            frozen_search_date=str(data["frozen_search_date"]),
            queries=tuple(str(q) for q in data.get("queries", ())),
            notes=str(data.get("notes", "")),
        )


def manifest_to_dict(manifest: CorpusManifest) -> dict[str, Any]:
    """Free-function form of :meth:`CorpusManifest.to_dict`."""
    return manifest.to_dict()


def manifest_from_dict(data: dict[str, Any]) -> CorpusManifest:
    """Free-function form of :meth:`CorpusManifest.from_dict`."""
    return CorpusManifest.from_dict(data)


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "CorpusManifest",
    "manifest_from_dict",
    "manifest_to_dict",
]
