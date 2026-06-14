"""M3 — cluster-and-name operator and multi-level taxonomy induction.

Public surface:

- :func:`CN` / :class:`ClusterConfig` / :class:`NamedClustering` — the core
  cluster-and-name operator.
- :func:`induce` / :class:`Taxonomy` / :class:`LevelResult` — the bottom-up
  Level V → C → M passes plus the text-only domain / solution-approach
  clusterings.
- :func:`stability_report` / :class:`StabilityReport` — silhouette, bootstrap
  ARI, and sensitivity diagnostics.

Everything is deterministic given the versioned :class:`ClusterConfig`.
"""

from __future__ import annotations

from lp2graph.mining.cluster.distance import (
    cosine_distance,
    cosine_similarity,
    distance_matrix,
)
from lp2graph.mining.cluster.operator import (
    CN,
    UNASSIGNED,
    Algorithm,
    ClusterConfig,
    NamedClustering,
)
from lp2graph.mining.cluster.silhouette import silhouette_samples, silhouette_score
from lp2graph.mining.cluster.stability import (
    StabilityReport,
    adjusted_rand_index,
    bootstrap_ari,
    sensitivity,
    stability_report,
)
from lp2graph.mining.cluster.taxonomy import (
    LevelResult,
    Taxonomy,
    induce,
    model_feature_document,
)

__all__ = [
    "CN",
    "UNASSIGNED",
    "Algorithm",
    "ClusterConfig",
    "LevelResult",
    "NamedClustering",
    "StabilityReport",
    "Taxonomy",
    "adjusted_rand_index",
    "bootstrap_ari",
    "cosine_distance",
    "cosine_similarity",
    "distance_matrix",
    "induce",
    "model_feature_document",
    "sensitivity",
    "silhouette_samples",
    "silhouette_score",
    "stability_report",
]
