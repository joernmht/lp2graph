"""Clustering stability report: silhouette, bootstrap ARI, sensitivity (M3).

A partition is only trustworthy if it survives resampling and small changes
to the knobs. This module quantifies that:

- **silhouette** — cohesion/separation of the reported partition (re-exported
  from :mod:`lp2graph.mining.cluster.silhouette`).
- **bootstrap ARI** — resample the entities with replacement, re-cluster, and
  measure Adjusted Rand Index against the reference partition restricted to
  the shared points; report mean and spread.
- **sensitivity** — re-cluster under alternative configs (a different
  algorithm, a coarsened vocabulary ``|C|``) and report the ARI to the
  reference partition.

Determinism: bootstrap resampling uses a seeded :class:`random.Random`, so the
report is reproducible from ``(seed, versions)``.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from lp2graph.mining.cluster.operator import CN, ClusterConfig, NamedClustering
from lp2graph.mining.homologize.vectorize import Vocabulary, build_vocabulary


def adjusted_rand_index(a: Sequence[int], b: Sequence[int]) -> float:
    """Adjusted Rand Index between two labelings of the same points.

    Returns 1.0 for identical partitions (up to relabeling), ~0.0 for random
    agreement. Defined as 1.0 for the degenerate all-equal case.
    """
    if len(a) != len(b):
        raise ValueError("labelings must have equal length")
    n = len(a)
    if n == 0:
        return 1.0
    contingency: dict[tuple[int, int], int] = defaultdict(int)
    rows: dict[int, int] = defaultdict(int)
    cols: dict[int, int] = defaultdict(int)
    for x, y in zip(a, b, strict=True):
        contingency[(x, y)] += 1
        rows[x] += 1
        cols[y] += 1

    def comb2(x: int) -> int:
        return x * (x - 1) // 2

    sum_comb = sum(comb2(v) for v in contingency.values())
    sum_rows = sum(comb2(v) for v in rows.values())
    sum_cols = sum(comb2(v) for v in cols.values())
    total = comb2(n)
    expected = (sum_rows * sum_cols) / total if total else 0.0
    max_index = (sum_rows + sum_cols) / 2.0
    if max_index == expected:
        return 1.0
    return (sum_comb - expected) / (max_index - expected)


@dataclass(frozen=True, slots=True)
class StabilityReport:
    """Silhouette + bootstrap ARI + sensitivity for one clustering."""

    silhouette: float
    bootstrap_ari_mean: float
    bootstrap_ari_min: float
    bootstrap_ari_max: float
    n_bootstrap: int
    sensitivity: dict[str, float]
    config_version: str
    seed: int


def bootstrap_ari(
    vectors: Sequence[Sequence[float]],
    vocab: Vocabulary,
    reference: NamedClustering,
    config: ClusterConfig,
    *,
    n_bootstrap: int = 25,
) -> tuple[float, float, float]:
    """Mean/min/max ARI of bootstrap re-clusterings vs the reference partition.

    Each bootstrap draws ``n`` indices with replacement, re-clusters the
    unique drawn points, and compares to the reference labels on those same
    points. Deterministic via ``config.seed``.
    """
    n = len(vectors)
    if n < 3:
        return (1.0, 1.0, 1.0)
    rng = random.Random(config.seed)
    scores: list[float] = []
    for _ in range(n_bootstrap):
        drawn = sorted({rng.randrange(n) for _ in range(n)})
        if len(drawn) < 2:
            continue
        sub_vectors = [vectors[i] for i in drawn]
        sub = CN(drawn, sub_vectors, vocab, config)
        ref_labels = [reference.labels[i] for i in drawn]
        scores.append(adjusted_rand_index(ref_labels, list(sub.labels)))
    if not scores:
        return (1.0, 1.0, 1.0)
    return (sum(scores) / len(scores), min(scores), max(scores))


def _coarsen_vocabulary(vocab: Vocabulary, keep_every: int) -> Vocabulary:
    """Drop concepts to shrink ``|C|`` (deterministic stride over sorted axis)."""
    kept = tuple(c for i, c in enumerate(vocab.concepts) if i % keep_every == 0)
    return build_vocabulary([{c: 1 for c in kept}], version=vocab.version)


def sensitivity(
    vectors: Sequence[Sequence[float]],
    vocab: Vocabulary,
    reference: NamedClustering,
    config: ClusterConfig,
) -> dict[str, float]:
    """ARI of the reference partition against alternative configurations.

    Probes robustness to the clustering algorithm (``fixed_k``) and to a
    coarsened vocabulary ``|C|`` (every-other concept). Each entry is the ARI
    between the reference labels and the labels under that variation.
    """
    out: dict[str, float] = {}

    alt_algo = ClusterConfig(
        algorithm="fixed_k",
        k_range=config.k_range,
        seed=config.seed,
        version=config.version,
    )
    alt = CN(list(range(len(vectors))), vectors, vocab, alt_algo)
    out["algorithm=fixed_k"] = adjusted_rand_index(list(reference.labels), list(alt.labels))

    if len(vocab) >= 4:
        coarse_vocab = _coarsen_vocabulary(vocab, keep_every=2)
        pos = {c: i for i, c in enumerate(vocab.concepts)}
        # Re-project vectors onto the coarsened axis (keep matching coordinates).
        coarse_vectors = [tuple(v[pos[c]] for c in coarse_vocab.concepts) for v in vectors]
        coarse = CN(list(range(len(vectors))), coarse_vectors, coarse_vocab, config)
        out["vocabulary=halved"] = adjusted_rand_index(list(reference.labels), list(coarse.labels))

    return out


def stability_report(
    vectors: Sequence[Sequence[float]],
    vocab: Vocabulary,
    clustering: NamedClustering,
    config: ClusterConfig,
    *,
    n_bootstrap: int = 25,
) -> StabilityReport:
    """Assemble the full stability report for one clustering."""
    mean, lo, hi = bootstrap_ari(vectors, vocab, clustering, config, n_bootstrap=n_bootstrap)
    sens = sensitivity(vectors, vocab, clustering, config)
    return StabilityReport(
        silhouette=clustering.silhouette,
        bootstrap_ari_mean=mean,
        bootstrap_ari_min=lo,
        bootstrap_ari_max=hi,
        n_bootstrap=n_bootstrap,
        sensitivity=sens,
        config_version=config.version,
        seed=config.seed,
    )


__all__ = [
    "StabilityReport",
    "adjusted_rand_index",
    "bootstrap_ari",
    "sensitivity",
    "stability_report",
]
