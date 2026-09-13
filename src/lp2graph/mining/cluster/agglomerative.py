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
    # Every group carries an id; the average linkage of two groups is cached
    # by (earlier id, later id) and each row keeps its first-minimum later
    # column, so a merge costs O(g) plus the recomputation of the rows whose
    # minimum it touched. A merge recomputes the merged group's distances
    # with exactly the member order the from-scratch loop would use (earlier
    # group outer, later inner), so cached values, tie-breaking and the
    # dendrogram are bit-for-bit those of the naive O(n^4) recomputation
    # this replaces.
    ids: list[int] = list(range(n))
    next_id = n
    cache: dict[tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            cache[(i, j)] = _average_linkage(dist, groups[i], groups[j])
    rowmin: dict[int, tuple[float, int] | None] = {}

    def recompute_row(pos: int) -> None:
        gid = ids[pos]
        best: tuple[float, int] | None = None
        for j in range(pos + 1, len(ids)):
            d = cache[(gid, ids[j])]
            if best is None or d < best[0]:
                best = (d, ids[j])
        rowmin[gid] = best

    for i in range(n):
        recompute_row(i)

    while len(groups) > 1:
        if k is not None and len(groups) <= k:
            break
        # The closest pair, first in (row, column) order among ties: the
        # first row whose minimum equals the global minimum, at that row's
        # first-minimum column.
        pos_of = {gid: pos for pos, gid in enumerate(ids)}
        best_pair: tuple[float, int, int] | None = None
        for i, gid in enumerate(ids):
            rm = rowmin[gid]
            if rm is not None and (best_pair is None or rm[0] < best_pair[0]):
                best_pair = (rm[0], i, pos_of[rm[1]])
        assert best_pair is not None
        merge_d, gi, gj = best_pair
        if k is None and distance_threshold is not None and merge_d > distance_threshold:
            break
        old_i, old_j = ids[gi], ids[gj]
        merged = groups[gi] + groups[gj]
        # drop every cached distance that involves the two old groups
        for pos, gid in enumerate(ids):
            if pos < gi:
                del cache[(gid, old_i)]
                del cache[(gid, old_j)]
            elif gi < pos < gj:
                del cache[(old_i, gid)]
                del cache[(gid, old_j)]
            elif pos > gj:
                del cache[(old_i, gid)]
                del cache[(old_j, gid)]
        del cache[(old_i, old_j)]
        del rowmin[old_i]
        del rowmin[old_j]
        groups[gi] = merged
        ids[gi] = next_id
        del groups[gj]
        del ids[gj]
        for pos, other in enumerate(groups):
            if pos < gi:
                cache[(ids[pos], next_id)] = _average_linkage(dist, other, merged)
            elif pos > gi:
                cache[(next_id, ids[pos])] = _average_linkage(dist, merged, other)
        pos_of = {gid: pos for pos, gid in enumerate(ids)}
        recompute_row(gi)
        for pos in range(gi):
            gid = ids[pos]
            rm = rowmin[gid]
            if rm is None or rm[1] in (old_i, old_j):
                recompute_row(pos)
                continue
            d_new = cache[(gid, next_id)]
            if d_new < rm[0] or (d_new == rm[0] and gi < pos_of[rm[1]]):
                rowmin[gid] = (d_new, next_id)
        for pos in range(gi + 1, gj):
            gid = ids[pos]
            rm = rowmin[gid]
            if rm is None or rm[1] == old_j:
                recompute_row(pos)
        next_id += 1

    return _labels_from_groups(groups, n)


__all__ = ["agglomerative"]
