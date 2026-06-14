"""LP mining extensions for lp2graph.

This subpackage implements the modules the *LP Mining with LP2Graph*
method needs on top of the deterministic core library:

- :mod:`lp2graph.mining.ingest` (M1) — heterogeneous ingestion front-end
  turning solver code and non-canonical LaTeX into validated
  ``Formulation`` objects, with source-span provenance.
- :mod:`lp2graph.mining.homologize` (M2) — lexical homologizer and
  TF-IDF concept vectorizer.
- :mod:`lp2graph.mining.cluster` (M3) — the cluster-and-name operator
  ``CN`` and the bottom-up multi-level taxonomy induction.
- :mod:`lp2graph.mining.label` (M4) — the two-stage labeling service with
  a versioned, self-growing closed-loop store.
- :mod:`lp2graph.mining.corpusmgr` (M5) — corpus & provenance manager.
- :mod:`lp2graph.mining.isomorphism` (M6) — intra-cluster schema-graph
  isomorphism reporting.

Every module is deterministic: frozen resources are versioned in
:mod:`lp2graph.mining.versions` and stamped into emitted records.
"""

from __future__ import annotations

from lp2graph.mining.provenance import ProvenanceMap, Rewrite, SourceSpan
from lp2graph.mining.versions import (
    CLUSTERING_VERSION,
    LABEL_LEXICON_VERSION,
    LEXICON_VERSION,
    REWRITE_RULES_VERSION,
    THESAURUS_VERSION,
    VOCABULARY_VERSION,
    WORDNET_VERSION,
)

__all__ = [
    "CLUSTERING_VERSION",
    "LABEL_LEXICON_VERSION",
    "LEXICON_VERSION",
    "REWRITE_RULES_VERSION",
    "THESAURUS_VERSION",
    "VOCABULARY_VERSION",
    "WORDNET_VERSION",
    "ProvenanceMap",
    "Rewrite",
    "SourceSpan",
]
