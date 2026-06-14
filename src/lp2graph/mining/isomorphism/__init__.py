"""M6 — intra-cluster schema-graph isomorphism reporting.

Computes, per taxonomy cluster, how structurally homogeneous its members are,
so a reader can judge how representative a validated anchor is. Built on the
existing NetworkX schema-graph export; deterministic.
"""

from __future__ import annotations

from lp2graph.mining.isomorphism.report import (
    ClusterIsomorphism,
    are_isomorphic,
    cluster_isomorphism,
    clusters_from_labels,
    isomorphism_report,
    schema_nx,
)

__all__ = [
    "ClusterIsomorphism",
    "are_isomorphic",
    "cluster_isomorphism",
    "clusters_from_labels",
    "isomorphism_report",
    "schema_nx",
]
