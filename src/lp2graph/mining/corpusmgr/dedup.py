"""Deterministic deduplication of corpus formulations (M5).

Two formulations are *duplicates* if they share either of two signals:

- the **schema-graph hash** — a stable digest of the schema view's
  *structure only* (node classes/subtypes/shapes + typed edges), ignoring
  every cosmetic name, description, and id. Two structurally identical
  formulations with different naming therefore collide.
- the **bibliographic key** — a normalized ``venue + year + source_id`` key,
  catching the same publication ingested twice.

:func:`deduplicate` clusters items that share *either* signal, transitively
(union-find), and picks a representative per group by citation count with
documented, deterministic tie-breaks. Everything is sorted so repeated runs
over the same input produce byte-identical output.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass

from lp2graph.core.graph import Graph
from lp2graph.core.model import Formulation
from lp2graph.mining.corpusmgr.record import ProvenanceRecord
from lp2graph.views.schema import schema

_PUNCT_RE = re.compile(r"[^\w]+")


def _canonicalize_graph(g: Graph) -> str:
    """Render ``g`` as a canonical, name-free, sorted structural string.

    Node *ids* and *labels* (which carry user-chosen names) are dropped; we
    map each node id to a structural signature ``(cls, subtype, shape)`` and
    describe edges by the structural signatures of their endpoints plus the
    edge ``type`` and ``role``. Sorting every component makes the result
    invariant to insertion order and to cosmetic renaming.
    """
    sig: dict[str, str] = {}
    for n in g.nodes:
        sig[n.id] = f"{n.cls}|{n.subtype}|{','.join(n.shape)}"

    node_lines = sorted(sig.values())
    edge_lines = sorted(f"{sig[e.src]}->{sig[e.dst]}|{e.type}|{e.role}" for e in g.edges)

    return "N\n" + "\n".join(node_lines) + "\nE\n" + "\n".join(edge_lines)


def schema_graph_hash(f: Formulation) -> str:
    """Return a stable hex digest of the schema-graph *structure* of ``f``.

    The digest is derived from node classes/subtypes/shapes and typed edges
    of the schema view only — never from names, descriptions, or ids — so
    two structurally identical formulations hash equal regardless of
    cosmetic naming. Uses SHA-256 and sorts all components for determinism.
    """
    canonical = _canonicalize_graph(schema(f))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    """Casefold and collapse non-word runs to single spaces; strip ends."""
    return _PUNCT_RE.sub(" ", text).casefold().strip()


def bibliographic_key(record: ProvenanceRecord) -> str:
    """Return a normalized bibliographic match key for ``record``.

    Built from ``venue + year + source_id``, casefolded with punctuation and
    whitespace normalized, so trivially different spellings of the same
    citation collapse to one key.
    """
    year = "" if record.year is None else str(record.year)
    parts = [_normalize(record.venue), year, _normalize(record.source_id)]
    return "|".join(parts)


@dataclass(frozen=True, slots=True)
class DedupResult:
    """The outcome of :func:`deduplicate`.

    ``groups`` are the duplicate clusters as tuples of indices into the
    input sequence; each group is sorted ascending, and the groups
    themselves are sorted. ``representatives`` gives, positionally aligned
    with ``groups``, the chosen representative index for each group.
    """

    groups: tuple[tuple[int, ...], ...]
    representatives: tuple[int, ...]

    def representative_index(self, group_position: int) -> int:
        """Representative input-index of the group at ``group_position``."""
        return self.representatives[group_position]


class _UnionFind:
    __slots__ = ("_parent",)

    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # path compression
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # attach larger root index under smaller for stable representatives
            lo, hi = (ra, rb) if ra < rb else (rb, ra)
            self._parent[hi] = lo


def _pick_representative(
    members: Sequence[int],
    records: Sequence[ProvenanceRecord],
) -> int:
    """Highest citation_count; tie -> best quality tier; tie -> lowest index."""
    return min(
        members,
        key=lambda i: (
            -records[i].citation_count,
            records[i].quality_rank,
            i,
        ),
    )


def deduplicate(
    items: Sequence[tuple[Formulation, ProvenanceRecord]],
) -> DedupResult:
    """Group ``items`` that share a schema-graph hash OR a bibliographic key.

    Grouping is transitive (union-find): if A matches B structurally and B
    matches C bibliographically, all three land in one group. Within each
    group the representative is the item with the highest
    ``citation_count``, ties broken by best quality tier then lowest input
    index. Fully deterministic.
    """
    n = len(items)
    uf = _UnionFind(n)

    by_hash: dict[str, int] = {}
    by_bib: dict[str, int] = {}

    for i, (formulation, record) in enumerate(items):
        h = schema_graph_hash(formulation)
        if h in by_hash:
            uf.union(i, by_hash[h])
        else:
            by_hash[h] = i

        b = bibliographic_key(record)
        if b in by_bib:
            uf.union(i, by_bib[b])
        else:
            by_bib[b] = i

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(uf.find(i), []).append(i)

    records = [r for _, r in items]
    groups = sorted(tuple(sorted(members)) for members in clusters.values())
    representatives = tuple(_pick_representative(g, records) for g in groups)

    return DedupResult(groups=tuple(groups), representatives=representatives)


__all__ = [
    "DedupResult",
    "bibliographic_key",
    "deduplicate",
    "schema_graph_hash",
]
