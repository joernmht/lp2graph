"""Cosine distance over TF-IDF concept vectors (M3).

The clustering operator works in cosine-distance space. Because the M2
vectorizer already L2-normalizes its output, cosine similarity is just the
dot product and cosine distance is ``1 - dot``. Zero vectors (entities whose
text yielded no in-vocabulary concept) are at distance 1 from everything and
are routed to the explicit *unassigned* part upstream.

Pure Python, no numpy dependency, fully order-deterministic.
"""

from __future__ import annotations

from collections.abc import Sequence

Vector = Sequence[float]


def dot(a: Vector, b: Vector) -> float:
    """Dot product of two equal-length vectors."""
    if len(a) != len(b):
        raise ValueError(f"vector length mismatch: {len(a)} vs {len(b)}")
    return sum(x * y for x, y in zip(a, b, strict=True))


def cosine_similarity(a: Vector, b: Vector) -> float:
    """Cosine similarity assuming ``a``/``b`` are L2-normalized (or zero)."""
    return dot(a, b)


def cosine_distance(a: Vector, b: Vector) -> float:
    """Cosine distance ``1 - cosine_similarity`` clamped to ``[0, 2]``."""
    d = 1.0 - cosine_similarity(a, b)
    if d < 0.0:
        return 0.0
    if d > 2.0:
        return 2.0
    return d


def is_zero(v: Vector) -> bool:
    """True if every coordinate is exactly zero (no concept signal)."""
    return all(x == 0.0 for x in v)


def distance_matrix(vectors: Sequence[Vector]) -> list[list[float]]:
    """Symmetric pairwise cosine-distance matrix with a zero diagonal."""
    n = len(vectors)
    mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = cosine_distance(vectors[i], vectors[j])
            mat[i][j] = d
            mat[j][i] = d
    return mat


__all__ = [
    "Vector",
    "cosine_distance",
    "cosine_similarity",
    "distance_matrix",
    "dot",
    "is_zero",
]
