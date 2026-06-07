"""Silhouette score and K selection (M3).

The silhouette coefficient measures how well each point sits in its assigned
cluster versus the nearest other cluster, in the same cosine-distance space
the clustering runs in. It serves two roles in the method: it is the
selection criterion for the fixed-K fallback, and it is reported (alongside
bootstrap ARI) in the stability report.

Pure Python and deterministic.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence


def silhouette_samples(dist: Sequence[Sequence[float]], labels: Sequence[int]) -> list[float]:
    """Per-point silhouette values given a distance matrix and labels.

    Points whose cluster has size 1, and all points when there is only one
    cluster, get a silhouette of 0 (the conventional definition).
    """
    n = len(labels)
    by_cluster: dict[int, list[int]] = defaultdict(list)
    for i, lab in enumerate(labels):
        by_cluster[lab].append(i)
    clusters = sorted(by_cluster)
    out = [0.0] * n
    if len(clusters) < 2:
        return out

    for i in range(n):
        own = labels[i]
        own_members = by_cluster[own]
        if len(own_members) <= 1:
            out[i] = 0.0
            continue
        a = sum(dist[i][j] for j in own_members if j != i) / (len(own_members) - 1)
        b = float("inf")
        for lab in clusters:
            if lab == own:
                continue
            members = by_cluster[lab]
            mean_d = sum(dist[i][j] for j in members) / len(members)
            if mean_d < b:
                b = mean_d
        denom = max(a, b)
        out[i] = 0.0 if denom == 0.0 else (b - a) / denom
    return out


def silhouette_score(dist: Sequence[Sequence[float]], labels: Sequence[int]) -> float:
    """Mean silhouette over all points (0.0 for a degenerate partition)."""
    samples = silhouette_samples(dist, labels)
    if not samples:
        return 0.0
    return sum(samples) / len(samples)


def select_k(
    dist: Sequence[Sequence[float]],
    cluster_fn: Callable[[int], Sequence[int]],
    *,
    k_min: int,
    k_max: int,
) -> tuple[int, float]:
    """Pick the K in ``[k_min, k_max]`` with the highest mean silhouette.

    ``cluster_fn(k)`` must return labels for ``k`` clusters. Ties are broken
    toward the smaller K (simpler partition). Returns ``(best_k, best_score)``.
    """
    n = len(dist)
    hi = min(k_max, n - 1)
    lo = max(2, k_min)
    if hi < lo:
        return (1, 0.0)
    best_k = lo
    best_score = float("-inf")
    for k in range(lo, hi + 1):
        score = silhouette_score(dist, cluster_fn(k))
        if score > best_score:
            best_score = score
            best_k = k
    return (best_k, best_score)


__all__ = ["select_k", "silhouette_samples", "silhouette_score"]
