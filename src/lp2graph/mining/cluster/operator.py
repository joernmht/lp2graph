"""The cluster-and-name operator ``CN`` (M3 core).

``CN(E)`` partitions a set of entities ``E`` (each carrying a TF-IDF concept
vector) into named parts. It is the single primitive the multi-level taxonomy
passes are built from:

1. Route entities with no concept signal (zero vector) to an explicit
   ``unassigned`` part (label ``-1``) — every entity ends up in exactly one
   part.
2. Cluster the rest in cosine-distance space. Default backend is the
   deterministic average-linkage core; ``fixed_k`` selects K by silhouette;
   ``hdbscan`` is used when the optional dependency is installed.
3. Name each part by aggregated TF-IDF weight: the concept carrying the most
   summed mass across the part's members becomes its name (collisions get a
   deterministic numeric suffix).

The whole operator is deterministic given the versioned
:class:`ClusterConfig`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from lp2graph.mining.cluster.agglomerative import agglomerative
from lp2graph.mining.cluster.distance import distance_matrix, is_zero
from lp2graph.mining.cluster.silhouette import select_k, silhouette_score
from lp2graph.mining.homologize.vectorize import Vocabulary
from lp2graph.mining.versions import CLUSTERING_VERSION

#: Cluster id reserved for entities with no concept signal.
UNASSIGNED = -1

Algorithm = Literal["agglomerative", "fixed_k", "hdbscan"]


@dataclass(frozen=True, slots=True)
class ClusterConfig:
    """Versioned, deterministic configuration for :func:`CN`."""

    algorithm: Algorithm = "agglomerative"
    distance_threshold: float = 0.7
    k: int | None = None
    k_range: tuple[int, int] = (2, 8)
    seed: int = 0
    version: str = CLUSTERING_VERSION


@dataclass(frozen=True, slots=True)
class NamedClustering:
    """The result of :func:`CN`: a named partition over the input entities.

    ``labels`` is aligned to the input order (``-1`` == unassigned).
    ``names`` maps each cluster id to its concept name. ``members`` maps each
    id to the (sorted) input indices it contains. ``silhouette`` is the mean
    silhouette over the assigned points.
    """

    labels: tuple[int, ...]
    names: dict[int, str]
    members: dict[int, tuple[int, ...]]
    config: ClusterConfig
    silhouette: float
    top_concepts: dict[int, tuple[tuple[str, float], ...]] = field(default_factory=dict)

    def name_of(self, index: int) -> str:
        """Name of the cluster the entity at ``index`` belongs to."""
        return self.names[self.labels[index]]

    @property
    def n_clusters(self) -> int:
        """Number of real (non-unassigned) clusters."""
        return len([cid for cid in self.members if cid != UNASSIGNED])


def _aggregate_weights(
    members: Sequence[int], vectors: Sequence[Sequence[float]], vocab: Vocabulary
) -> list[tuple[str, float]]:
    totals = [0.0] * len(vocab)
    for idx in members:
        v = vectors[idx]
        for j, val in enumerate(v):
            if val != 0.0:
                totals[j] += val
    weighted = [(vocab.concepts[j], totals[j]) for j in range(len(vocab)) if totals[j] > 0.0]
    # Sort by descending weight, then concept name for deterministic ties.
    weighted.sort(key=lambda kv: (-kv[1], kv[0]))
    return weighted


def _name_clusters(
    members: dict[int, tuple[int, ...]],
    vectors: Sequence[Sequence[float]],
    vocab: Vocabulary,
) -> tuple[dict[int, str], dict[int, tuple[tuple[str, float], ...]]]:
    names: dict[int, str] = {}
    tops: dict[int, tuple[tuple[str, float], ...]] = {}
    used: dict[str, int] = {}
    # Deterministic order: by cluster id.
    for cid in sorted(members):
        if cid == UNASSIGNED:
            names[cid] = "unassigned"
            tops[cid] = ()
            continue
        weighted = _aggregate_weights(members[cid], vectors, vocab)
        tops[cid] = tuple(weighted[:5])
        base = weighted[0][0] if weighted else f"cluster_{cid}"
        if base in used:
            used[base] += 1
            name = f"{base}_{used[base]}"
        else:
            used[base] = 1
            name = base
        names[cid] = name
    return names, tops


def _hdbscan_labels(dist: Sequence[Sequence[float]], min_cluster_size: int) -> list[int]:
    import hdbscan  # local import; optional dependency

    clusterer = hdbscan.HDBSCAN(metric="precomputed", min_cluster_size=max(2, min_cluster_size))
    rows = [[float(x) for x in row] for row in dist]
    labels = clusterer.fit_predict(rows)
    return [int(x) for x in labels]


def CN(
    entities: Sequence[object],
    vectors: Sequence[Sequence[float]],
    vocab: Vocabulary,
    config: ClusterConfig | None = None,
) -> NamedClustering:
    """Cluster ``entities`` (by ``vectors``) and name the parts.

    ``entities`` is only used for its length and ordering; the partition is
    computed from ``vectors`` and named from ``vocab``. Returns a
    deterministic :class:`NamedClustering`.
    """
    cfg = config or ClusterConfig()
    n = len(vectors)
    if len(entities) != n:
        raise ValueError("entities and vectors must have the same length")

    labels = [UNASSIGNED] * n
    assigned = [i for i in range(n) if not is_zero(vectors[i])]

    if assigned:
        sub_vectors = [vectors[i] for i in assigned]
        sub_dist = distance_matrix(sub_vectors)
        sub_labels = _cluster(sub_dist, cfg)
        # Re-pack sub-cluster ids into a dense 0..K-1 space, ordered by first
        # appearance, then map back to original indices.
        remap: dict[int, int] = {}
        for sub_idx, lab in enumerate(sub_labels):
            if lab < 0:  # hdbscan noise → unassigned
                continue
            if lab not in remap:
                remap[lab] = len(remap)
            labels[assigned[sub_idx]] = remap[lab]

    grouped: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        grouped.setdefault(lab, []).append(i)
    members: dict[int, tuple[int, ...]] = {
        cid: tuple(sorted(idxs)) for cid, idxs in grouped.items()
    }

    names, tops = _name_clusters(members, vectors, vocab)

    real_labels = [labels[i] for i in assigned]
    if assigned and len({lab for lab in real_labels if lab >= 0}) >= 2:
        sub_dist = distance_matrix([vectors[i] for i in assigned])
        sil = silhouette_score(sub_dist, real_labels)
    else:
        sil = 0.0

    return NamedClustering(
        labels=tuple(labels),
        names=names,
        members=members,
        config=cfg,
        silhouette=sil,
        top_concepts=tops,
    )


def _cluster(dist: Sequence[Sequence[float]], cfg: ClusterConfig) -> list[int]:
    n = len(dist)
    if n == 0:
        return []
    if n == 1:
        return [0]
    if cfg.algorithm == "hdbscan":
        return _hdbscan_labels(dist, min_cluster_size=2)
    if cfg.algorithm == "fixed_k":
        k_target = cfg.k
        if k_target is None:
            k_target, _ = select_k(
                dist,
                lambda k: agglomerative(dist, distance_threshold=None, k=k),
                k_min=cfg.k_range[0],
                k_max=cfg.k_range[1],
            )
        k_target = max(1, min(k_target, n))
        return list(agglomerative(dist, distance_threshold=None, k=k_target))
    # default: threshold-based agglomerative
    return list(agglomerative(dist, distance_threshold=cfg.distance_threshold, k=None))


__all__ = [
    "CN",
    "UNASSIGNED",
    "Algorithm",
    "ClusterConfig",
    "NamedClustering",
]
