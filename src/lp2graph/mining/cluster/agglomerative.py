"""Deterministic average-linkage agglomerative clustering (M3).

A small, dependency-free clustering core used as the default backend for the
``CN`` operator. Two stopping modes:

- **threshold** — keep merging the two closest clusters until the closest
  average-linkage distance exceeds ``distance_threshold``; this discovers the
  number of clusters (and naturally leaves singletons), the HDBSCAN-style
  behavior the method asks for without the dependency.
- **fixed K** — merge until exactly ``k`` clusters remain.

Determinism is the whole point: ties (equal merge distances) are broken by
the lexicographically smallest cluster-index pair, so the dendrogram — and
every partition cut from it — is reproducible across runs and machines.
"""

from __future__ import annotations

from collections.abc import Sequence


def _labels_from_groups(groups: list[list[int]], n: int) -> tuple[int, ...]:
    """Assign each point a cluster id, ids ordered by smallest member index."""
    ordered = sorted(groups, key=min)
    labels = [-1] * n
    for cid, group in enumerate(ordered):
        for idx in group:
            labels[idx] = cid
    return tuple(labels)


def _average_linkage(dist: Sequence[Sequence[float]], a: Sequence[int], b: Sequence[int]) -> float:
    total = 0.0
    for i in a:
        for j in b:
            total += dist[i][j]
    return total / (len(a) * len(b))


def agglomerative(
    dist: Sequence[Sequence[float]],
    *,
    distance_threshold: float | None = 0.7,
    k: int | None = None,
) -> tuple[int, ...]:
    """Cluster points described by precomputed distance matrix ``dist``.

    Provide exactly one stopping rule: ``k`` (fixed cluster count) or
    ``distance_threshold`` (merge while the closest pair is within it).
    Returns a tuple of cluster ids aligned to the input order.
    """
    if (k is None) == (distance_threshold is None):
        raise ValueError("provide exactly one of 'k' or 'distance_threshold'")
    n = len(dist)
    if n == 0:
        return ()
    if n == 1:
        return (0,)

    groups: list[list[int]] = [[i] for i in range(n)]

    while len(groups) > 1:
        if k is not None and len(groups) <= k:
            break
        # Find the closest pair of groups; deterministic tie-break by (i, j).
        best: tuple[float, int, int] | None = None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                d = _average_linkage(dist, groups[i], groups[j])
                if best is None or d < best[0]:
                    best = (d, i, j)
        assert best is not None
        merge_d, gi, gj = best
        if k is None and distance_threshold is not None and merge_d > distance_threshold:
            break
        groups[gi] = groups[gi] + groups[gj]
        del groups[gj]

    return _labels_from_groups(groups, n)


__all__ = ["agglomerative"]
