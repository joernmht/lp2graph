"""Intra-cluster schema-graph isomorphism rate (M6).

Once the taxonomy has grouped formulations into clusters, a reader validating
one representative anchor per cluster needs to know how *representative* that
anchor is structurally. This module answers that with the schema-graph
isomorphism rate inside each cluster, computed through the existing NetworkX
export.

Two formulations are *schema-graph isomorphic* when their schema views are
isomorphic as typed directed multigraphs, matching node ``(cls, subtype)`` and
edge ``(type, role)`` — i.e. the same topology of variable/constraint/index
templates regardless of names. The report gives, per cluster:

- the pairwise isomorphism rate (fraction of member pairs that are isomorphic);
- the structural equivalence classes and the largest one;
- the whole-cluster rate (largest class size / cluster size), i.e. the share
  of the cluster the most common structure covers.

Isomorphism is an equivalence relation, so equivalence classes are built by
comparing each member to one representative per existing class — exact and
deterministic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lp2graph.core.model import Formulation
from lp2graph.export.networkx_adapter import to_networkx
from lp2graph.views.schema import schema

if TYPE_CHECKING:
    import networkx as nx


def _require_networkx() -> Any:
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - exercised only without networkx
        raise ImportError(
            "the isomorphism report requires networkx; install with "
            "'pip install lp2graph[networkx]'"
        ) from exc
    return nx


def schema_nx(f: Formulation) -> nx.MultiDiGraph:
    """The schema view of ``f`` as a NetworkX ``MultiDiGraph``."""
    return to_networkx(schema(f))


def are_isomorphic(f1: Formulation, f2: Formulation) -> bool:
    """True if the schema graphs of ``f1`` and ``f2`` are isomorphic.

    Nodes match on ``(cls, subtype)`` and edges on ``(type, role)``; labels,
    names, and descriptions are ignored, so the test is purely structural.
    """
    nx = _require_networkx()
    from networkx.algorithms.isomorphism import (
        categorical_multiedge_match,
        categorical_node_match,
    )

    g1 = schema_nx(f1)
    g2 = schema_nx(f2)
    node_match = categorical_node_match(["cls", "subtype"], ["", ""])
    edge_match = categorical_multiedge_match(["type", "role"], ["", ""])
    return bool(nx.is_isomorphic(g1, g2, node_match=node_match, edge_match=edge_match))


@dataclass(frozen=True, slots=True)
class ClusterIsomorphism:
    """Isomorphism diagnostics for one cluster.

    ``equivalence_classes`` holds the member indices (into the cluster's own
    member list) grouped by structural equivalence, classes sorted by
    descending size then smallest member. ``pairwise_rate`` is the fraction of
    member pairs that are isomorphic; ``whole_cluster_rate`` is the largest
    class size over the cluster size.
    """

    name: str
    size: int
    n_pairs: int
    n_isomorphic_pairs: int
    pairwise_rate: float
    equivalence_classes: tuple[tuple[int, ...], ...]
    largest_class_size: int
    whole_cluster_rate: float
    representative: int


def _equivalence_classes(members: Sequence[Formulation]) -> list[list[int]]:
    """Group member indices by schema-graph isomorphism (deterministic)."""
    classes: list[list[int]] = []
    for i, f in enumerate(members):
        placed = False
        for cls in classes:
            if are_isomorphic(members[cls[0]], f):
                cls.append(i)
                placed = True
                break
        if not placed:
            classes.append([i])
    return classes


def cluster_isomorphism(name: str, members: Sequence[Formulation]) -> ClusterIsomorphism:
    """Compute the isomorphism report for a single cluster."""
    size = len(members)
    classes = _equivalence_classes(members)
    # Sort classes by descending size, then by smallest member index.
    classes.sort(key=lambda c: (-len(c), min(c)))
    class_tuples = tuple(tuple(sorted(c)) for c in classes)

    n_pairs = size * (size - 1) // 2
    n_iso_pairs = sum(len(c) * (len(c) - 1) // 2 for c in classes)
    largest = max((len(c) for c in classes), default=0)
    pairwise_rate = (n_iso_pairs / n_pairs) if n_pairs else 1.0
    whole_rate = (largest / size) if size else 0.0
    # Representative: a member of the largest class with the smallest index.
    representative = min(classes[0]) if classes else -1

    return ClusterIsomorphism(
        name=name,
        size=size,
        n_pairs=n_pairs,
        n_isomorphic_pairs=n_iso_pairs,
        pairwise_rate=pairwise_rate,
        equivalence_classes=class_tuples,
        largest_class_size=largest,
        whole_cluster_rate=whole_rate,
        representative=representative,
    )


def isomorphism_report(
    clusters: Mapping[str, Sequence[Formulation]],
) -> dict[str, ClusterIsomorphism]:
    """Per-cluster schema-graph isomorphism report.

    ``clusters`` maps a cluster name to its member formulations. Returns a
    name → :class:`ClusterIsomorphism` mapping; iteration order follows the
    sorted cluster names for determinism.
    """
    return {name: cluster_isomorphism(name, list(clusters[name])) for name in sorted(clusters)}


def clusters_from_labels(
    formulations: Sequence[Formulation],
    labels: Sequence[int],
    names: Mapping[int, str],
) -> dict[str, list[Formulation]]:
    """Adapter: turn an M3 model-level clustering into name → formulations.

    ``labels[i]`` is the cluster id of ``formulations[i]`` and ``names`` maps
    cluster ids to names (both come straight from a
    :class:`~lp2graph.mining.cluster.operator.NamedClustering`). The explicit
    ``unassigned`` part is included like any other cluster.
    """
    if len(formulations) != len(labels):
        raise ValueError("formulations and labels must have equal length")
    out: dict[str, list[Formulation]] = {}
    for f, lab in zip(formulations, labels, strict=True):
        out.setdefault(names[lab], []).append(f)
    return out


__all__ = [
    "ClusterIsomorphism",
    "are_isomorphic",
    "cluster_isomorphism",
    "clusters_from_labels",
    "isomorphism_report",
    "schema_nx",
]
