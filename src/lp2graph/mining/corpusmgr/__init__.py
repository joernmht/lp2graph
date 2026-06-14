"""M5 — corpus & provenance manager.

The corpus manager makes the extracted corpus *regenerable from queries +
freeze date* and makes representative selection a pure, reproducible
function. It provides:

- :class:`ProvenanceRecord` — bibliographic + categorization provenance for
  one corpus entry (``citation_count`` is the count at the freeze date).
- :class:`CorpusManifest` — the reproducible record of what was searched
  (queries + frozen search date), round-trippable to/from a plain dict.
- :func:`schema_graph_hash` / :func:`bibliographic_key` / :func:`deduplicate`
  — deterministic dedup by schema-graph structure OR bibliographic key
  (transitive), with a documented representative tie-break.
- :func:`select_representatives` — reproducible per-cluster representative
  choice with documented citation/quality fallbacks.
- :class:`CorpusManager` — a thin facade tying the manifest and entries
  together.

Everything here is deterministic: identical inputs yield identical output.
"""

from __future__ import annotations

from lp2graph.mining.corpusmgr.dedup import (
    DedupResult,
    bibliographic_key,
    deduplicate,
    schema_graph_hash,
)
from lp2graph.mining.corpusmgr.manager import CorpusManager
from lp2graph.mining.corpusmgr.manifest import (
    MANIFEST_SCHEMA_VERSION,
    CorpusManifest,
    manifest_from_dict,
    manifest_to_dict,
)
from lp2graph.mining.corpusmgr.record import (
    PRIORITY_CELLS,
    QUALITY_TIERS,
    PriorityCell,
    ProvenanceRecord,
    QualityTier,
    quality_rank,
)
from lp2graph.mining.corpusmgr.select import (
    RepresentativeChoice,
    SelectionReason,
    select_representatives,
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "PRIORITY_CELLS",
    "QUALITY_TIERS",
    "CorpusManager",
    "CorpusManifest",
    "DedupResult",
    "PriorityCell",
    "ProvenanceRecord",
    "QualityTier",
    "RepresentativeChoice",
    "SelectionReason",
    "bibliographic_key",
    "deduplicate",
    "manifest_from_dict",
    "manifest_to_dict",
    "quality_rank",
    "schema_graph_hash",
    "select_representatives",
]
