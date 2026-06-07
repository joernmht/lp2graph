"""TF-IDF concept vectors over a frozen vocabulary ``C`` (M2).

Homologization and clustering compare entities by the concepts their names
and descriptions evoke. This module turns a concept multiset into a fixed,
ordered, deterministic numeric vector:

- :class:`Vocabulary` is the frozen, sorted concept axis ``C``. It is built
  from a corpus with :func:`build_vocabulary`, which sorts concepts so the
  axis — and therefore every vector's coordinate meaning — is stable and any
  vocabulary change is a readable diff.
- :class:`ConceptVectorizer` computes smoothed IDF weights over ``C`` from a
  set of documents and emits L2-normalized TF-IDF vectors.

Everything is pure Python (no numpy dependency) and order-deterministic, so
two runs over identical inputs yield byte-identical vectors.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from lp2graph.mining.versions import VOCABULARY_VERSION

#: A concept-count document: concept token → count.
ConceptCounts = Mapping[str, int]


@dataclass(frozen=True, slots=True)
class Vocabulary:
    """The frozen concept axis ``C``.

    ``concepts`` is a sorted, de-duplicated tuple; its order defines vector
    coordinates. ``version`` stamps which frozen vocabulary produced a
    vector.
    """

    concepts: tuple[str, ...]
    version: str = VOCABULARY_VERSION

    def __post_init__(self) -> None:
        if list(self.concepts) != sorted(set(self.concepts)):
            raise ValueError("Vocabulary.concepts must be sorted and unique")

    def __len__(self) -> int:
        return len(self.concepts)

    def index(self, concept: str) -> int | None:
        """Return the coordinate of ``concept`` or ``None`` if out-of-vocabulary."""
        position = self._position_map.get(concept)
        return position

    @property
    def _position_map(self) -> dict[str, int]:
        return {c: i for i, c in enumerate(self.concepts)}


def build_vocabulary(
    documents: Iterable[ConceptCounts], *, version: str = VOCABULARY_VERSION
) -> Vocabulary:
    """Build a sorted vocabulary from the concepts present in ``documents``."""
    seen: set[str] = set()
    for doc in documents:
        seen.update(doc.keys())
    return Vocabulary(concepts=tuple(sorted(seen)), version=version)


@dataclass(frozen=True, slots=True)
class ConceptVectorizer:
    """A fitted TF-IDF vectorizer over a fixed :class:`Vocabulary`.

    Use :meth:`fit` to learn IDF weights from a document set, then
    :meth:`transform` to map any concept-count document to an L2-normalized
    vector aligned to ``vocabulary.concepts``. Out-of-vocabulary concepts are
    ignored (the vocabulary is the contract).
    """

    vocabulary: Vocabulary
    idf: tuple[float, ...]

    @classmethod
    def fit(
        cls,
        documents: Sequence[ConceptCounts],
        *,
        vocabulary: Vocabulary | None = None,
    ) -> ConceptVectorizer:
        """Fit IDF over ``documents`` (smoothed, sklearn-style).

        ``idf(c) = ln((1 + N) / (1 + df(c))) + 1`` where ``N`` is the number
        of documents and ``df(c)`` the number containing concept ``c``. When
        ``vocabulary`` is omitted it is built from the documents.
        """
        vocab = vocabulary if vocabulary is not None else build_vocabulary(documents)
        n_docs = len(documents)
        df = [0] * len(vocab)
        pos = vocab._position_map
        for doc in documents:
            for concept in doc:
                idx = pos.get(concept)
                if idx is not None and doc[concept] > 0:
                    df[idx] += 1
        idf = tuple(math.log((1 + n_docs) / (1 + df_c)) + 1.0 for df_c in df)
        return cls(vocabulary=vocab, idf=idf)

    def transform(self, document: ConceptCounts) -> tuple[float, ...]:
        """Map one concept-count document to an L2-normalized TF-IDF vector."""
        pos = self.vocabulary._position_map
        raw = [0.0] * len(self.vocabulary)
        for concept, count in document.items():
            idx = pos.get(concept)
            if idx is not None and count > 0:
                raw[idx] = float(count) * self.idf[idx]
        norm = math.sqrt(sum(v * v for v in raw))
        if norm == 0.0:
            return tuple(raw)
        return tuple(v / norm for v in raw)

    @classmethod
    def fit_transform(
        cls,
        documents: Sequence[ConceptCounts],
        *,
        vocabulary: Vocabulary | None = None,
    ) -> tuple[ConceptVectorizer, tuple[tuple[float, ...], ...]]:
        """Convenience: :meth:`fit` then :meth:`transform` every document.

        Returns the fitted vectorizer alongside the document vectors so the
        IDF weights and vocabulary version remain available for stamping.
        """
        fitted = cls.fit(documents, vocabulary=vocabulary)
        return fitted, tuple(fitted.transform(doc) for doc in documents)


__all__ = [
    "ConceptCounts",
    "ConceptVectorizer",
    "Vocabulary",
    "build_vocabulary",
]
