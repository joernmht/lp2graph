"""Tests for M2 — lexical homologizer & concept vectorizer."""

from __future__ import annotations

from pathlib import Path

import pytest

from lp2graph import load
from lp2graph.mining.homologize import (
    ConceptVectorizer,
    Vocabulary,
    build_vocabulary,
    concept_bag,
    concept_of,
    concepts,
    corpus_entities,
    lemmatize,
    signature_documents,
    split_compounds,
    tokenize,
)

ROOT = Path(__file__).resolve().parents[2]
FORMULATIONS = ROOT / "formulations"


def _all_formulations() -> list:
    return [load(p) for p in sorted(FORMULATIONS.rglob("*.json"))]


# --- tokenizer -------------------------------------------------------------


def test_split_compounds_handles_identifier_shapes() -> None:
    assert split_compounds("headway_separation") == ["headway", "separation"]
    assert split_compounds("rollingStock") == ["rolling", "stock"]
    assert split_compounds("x_{i,t}") == ["x", "i", "t"]
    assert split_compounds("big-M") == ["big", "m"]


def test_tokenize_drops_stopwords_and_short_tokens() -> None:
    toks = tokenize("the number of trains in the set of constraints")
    # "the", "of", "in", "number", "set", "constraints" are all stopped.
    assert "train" not in toks  # lemmatization happens later, not in tokenize
    assert "trains" in toks
    assert "the" not in toks
    assert "constraints" not in toks  # domain stop word


def test_tokenize_is_deterministic() -> None:
    text = "Headway separation between consecutive trains on a block section"
    assert tokenize(text) == tokenize(text)


# --- lemmatizer ------------------------------------------------------------


@pytest.mark.parametrize(
    ("surface", "base"),
    [
        ("constraints", "constraint"),
        ("capacities", "capacity"),
        ("indices", "index"),
        ("orderings", "ordering"),
        ("trains", "train"),
        ("delays", "delay"),
        ("loss", "loss"),  # -ss not stripped
        ("bus", "bus"),  # too short to strip
    ],
)
def test_lemmatize(surface: str, base: str) -> None:
    assert lemmatize(surface) == base


# --- concept mapping (the acceptance fixture) ------------------------------


def test_synonyms_collapse_to_one_concept() -> None:
    # Each group should map to a single shared concept token.
    groups = [
        ["headway", "spacing"],
        ["ordering", "precedence", "sequencing", "overtaking"],
        ["timetable", "schedule", "departure"],
        ["delay", "lateness", "tardiness"],
        ["allocation", "assignment", "matching"],
    ]
    for group in groups:
        mapped = {concept_of(word) for word in group}
        assert len(mapped) == 1, f"{group} did not collapse: {mapped}"


def test_multiword_concept_beats_its_parts() -> None:
    bag = concept_bag("rolling stock circulation")
    assert bag["rolling_stock"] == 1
    assert "rolling" not in bag and "stock" not in bag


def test_concept_bag_is_deterministic() -> None:
    text = "minimum headway separation between consecutive train departures"
    assert concepts(text) == concepts(text)


# --- vocabulary + vectorizer ----------------------------------------------


def test_vocabulary_must_be_sorted_and_unique() -> None:
    with pytest.raises(ValueError):
        Vocabulary(concepts=("b", "a"))
    with pytest.raises(ValueError):
        Vocabulary(concepts=("a", "a"))


def test_build_vocabulary_is_sorted_diffable() -> None:
    docs = [concept_bag("headway conflict"), concept_bag("capacity demand")]
    vocab = build_vocabulary(docs)
    assert list(vocab.concepts) == sorted(vocab.concepts)
    # Adding a doc only extends the axis; existing coordinates keep meaning.
    docs2 = [*docs, concept_bag("robust delay")]
    vocab2 = build_vocabulary(docs2)
    for c in vocab.concepts:
        assert c in vocab2.concepts


def test_tfidf_vectors_are_stable_across_runs() -> None:
    docs = [
        concept_bag("headway separation between trains"),
        concept_bag("rolling stock assignment to services"),
        concept_bag("track capacity at a block section"),
    ]
    vec1, vectors1 = ConceptVectorizer.fit_transform(docs)
    vec2, vectors2 = ConceptVectorizer.fit_transform(docs)
    assert vectors1 == vectors2
    assert vec1.idf == vec2.idf
    # L2-normalized: every non-empty vector has unit norm.
    for v in vectors1:
        norm_sq = sum(x * x for x in v)
        assert abs(norm_sq - 1.0) < 1e-9


def test_vectorizer_ignores_out_of_vocabulary() -> None:
    vocab = build_vocabulary([concept_bag("headway capacity")])
    fitted = ConceptVectorizer.fit([concept_bag("headway capacity")], vocabulary=vocab)
    v = fitted.transform(concept_bag("headway robustness delay"))
    # "robust"/"delay" are out of vocabulary; only "headway" survives.
    nonzero = [i for i, x in enumerate(v) if x != 0.0]
    assert len(nonzero) == 1


# --- type signatures over the real catalog ---------------------------------


def test_entities_carry_signatures_for_every_formulation() -> None:
    forms = _all_formulations()
    assert forms, "expected formulation fixtures"
    for f in forms:
        for level in ("V", "C", "M"):
            ents = corpus_entities([f], level)  # type: ignore[arg-type]
            for e in ents:
                assert e.signature.canonical()
                assert e.text
        # Level M is exactly one entity.
        assert len(corpus_entities([f], "M")) == 1  # type: ignore[arg-type]


def test_signature_documents_are_categorical() -> None:
    forms = _all_formulations()
    ents = corpus_entities(forms, "C")  # type: ignore[arg-type]
    docs = signature_documents(ents)
    assert len(docs) == len(ents)
    # Every constraint entity emits a role token.
    for doc in docs:
        assert any(k.startswith("role:") for k in doc)
