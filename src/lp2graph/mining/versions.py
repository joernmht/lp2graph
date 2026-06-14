"""Frozen version stamps for every determinism-bearing resource.

The *LP Mining with LP2Graph* method requires that two runs over the same
inputs produce byte-identical artifacts. The only way to keep that promise
while still allowing the resources to evolve is to version every frozen
resource explicitly and stamp it into the records the pipeline emits. When
a thesaurus entry, a stop-word, a vocabulary token, or a clustering knob
changes, its version string changes too, and the change is *diffable*:
a reader can see exactly which frozen input moved.

These are plain strings, deliberately not derived from package metadata or
timestamps (both of which would break reproducibility). Bumping a resource
is an explicit, reviewed edit to this module.
"""

from __future__ import annotations

from typing import Final

#: Stop-list + tokenizer normalization rules (M2).
LEXICON_VERSION: Final = "lex-2026.06.0"

#: Domain thesaurus / concept map (M2).
THESAURUS_VERSION: Final = "thes-2026.06.0"

#: Frozen TF-IDF concept vocabulary ``C`` (M2).
VOCABULARY_VERSION: Final = "vocab-2026.06.0"

#: WordNet database version, when the optional WordNet backend is used (M2).
#: ``None`` means the thesaurus-only backend was used (still deterministic).
WORDNET_VERSION: Final = "wn-3.1"

#: Clustering configuration / operator ``CN`` defaults (M3).
CLUSTERING_VERSION: Final = "cluster-2026.06.0"

#: Controlled label vocabularies + rule lexicon (M4).
LABEL_LEXICON_VERSION: Final = "label-2026.06.0"

#: LaTeX rewrite-rule table used by the non-canonical normalizer (M1).
REWRITE_RULES_VERSION: Final = "rewrite-2026.06.0"


__all__ = [
    "CLUSTERING_VERSION",
    "LABEL_LEXICON_VERSION",
    "LEXICON_VERSION",
    "REWRITE_RULES_VERSION",
    "THESAURUS_VERSION",
    "VOCABULARY_VERSION",
    "WORDNET_VERSION",
]
