"""M2 — lexical homologizer and concept vectorizer.

Reduces entity names and descriptions to comparable *concepts*, emits frozen
TF-IDF concept vectors, and exposes the structural type signature ``τ(s)``
read from the canonical model. Everything here is deterministic and pinned by
the versions in :mod:`lp2graph.mining.versions`.

Typical use::

    from lp2graph.mining.homologize import corpus_entities, concept_bag, ConceptVectorizer
    ents = corpus_entities(formulations, "C")
    docs = [concept_bag(e.text) for e in ents]
    vec, vectors = ConceptVectorizer.fit_transform(docs)
"""

from __future__ import annotations

from lp2graph.mining.homologize.concept import (
    concept_backend_versions,
    concept_bag,
    concept_of,
    concepts,
)
from lp2graph.mining.homologize.entity import (
    Entity,
    EntityLevel,
    corpus_entities,
    entities,
    level_c_entities,
    level_m_entity,
    level_v_entities,
    signature_documents,
    text_dimension,
)
from lp2graph.mining.homologize.lemmatize import lemmatize
from lp2graph.mining.homologize.signature import (
    TypeSignature,
    constraint_signature,
    model_signature,
    objective_signature,
    parameter_signature,
    variable_signature,
)
from lp2graph.mining.homologize.thesaurus import PHRASE_TO_CONCEPT
from lp2graph.mining.homologize.tokenize import STOPLIST, split_compounds, tokenize
from lp2graph.mining.homologize.vectorize import (
    ConceptCounts,
    ConceptVectorizer,
    Vocabulary,
    build_vocabulary,
)

__all__ = [
    "PHRASE_TO_CONCEPT",
    "STOPLIST",
    "ConceptCounts",
    "ConceptVectorizer",
    "Entity",
    "EntityLevel",
    "TypeSignature",
    "Vocabulary",
    "build_vocabulary",
    "concept_backend_versions",
    "concept_bag",
    "concept_of",
    "concepts",
    "constraint_signature",
    "corpus_entities",
    "entities",
    "lemmatize",
    "level_c_entities",
    "level_m_entity",
    "level_v_entities",
    "model_signature",
    "objective_signature",
    "parameter_signature",
    "signature_documents",
    "split_compounds",
    "text_dimension",
    "tokenize",
    "variable_signature",
]
