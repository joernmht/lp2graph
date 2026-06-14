"""Concept mapping ``g: token → concept`` (M2).

Surface tokens are folded to concepts in three deterministic stages:

1. **Morphology** — :func:`~lp2graph.mining.homologize.lemmatize.lemmatize`
   already collapsed inflections upstream.
2. **Domain synonymy** — the frozen thesaurus collapses curated synonym
   families (matched greedily as bigrams then unigrams, so ``rolling stock``
   wins over ``rolling`` + ``stock``).
3. **Optional WordNet** — when the ``nltk`` WordNet corpus is importable, an
   out-of-thesaurus token is folded onto the lemma name of its first synset;
   the pinned database version is recorded. When WordNet is absent the
   concept is the lemma itself (identity) — still fully deterministic.

The function ``g`` is :func:`concept_of`; :func:`concept_bag` applies it
across a piece of text and returns a multiset of concepts.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

from lp2graph.mining.homologize.lemmatize import lemmatize
from lp2graph.mining.homologize.thesaurus import PHRASE_TO_CONCEPT
from lp2graph.mining.homologize.tokenize import tokenize
from lp2graph.mining.versions import THESAURUS_VERSION, WORDNET_VERSION


def _lemmatize_phrase(phrase: str) -> str:
    return " ".join(lemmatize(w) for w in phrase.split())


# The thesaurus, re-keyed into the lemmatized space the tokenizer produces, so
# phrase lookups line up with lemmatized token n-grams.
_LEMMA_PHRASE_INDEX: dict[str, str] = {}
for _phrase, _concept in PHRASE_TO_CONCEPT.items():
    _LEMMA_PHRASE_INDEX.setdefault(_lemmatize_phrase(_phrase), _concept)

_MAX_PHRASE_WORDS: int = max((len(p.split()) for p in _LEMMA_PHRASE_INDEX), default=1)


@lru_cache(maxsize=4096)
def _wordnet_concept(lemma: str) -> str | None:
    """Fold ``lemma`` onto a WordNet synset lemma name, if WordNet is present.

    Deterministic: always the first synset's first lemma name. Returns
    ``None`` when WordNet is unavailable so callers fall back to identity.
    """
    try:
        from nltk.corpus import wordnet

        synsets = wordnet.synsets(lemma)
    except Exception:
        return None
    if not synsets:
        return None
    lemmas = synsets[0].lemmas()
    if not lemmas:
        return None
    name: str = lemmas[0].name().lower()
    return name


def concept_of(token: str, *, use_wordnet: bool = False) -> str:
    """Map a single surface ``token`` to its concept.

    Lemmatize, then prefer the thesaurus; optionally consult WordNet; else
    fall back to the lemma itself. Only unigram thesaurus entries are
    consulted here — phrase (bigram) folding lives in :func:`concept_bag`.
    """
    lemma = lemmatize(token.lower())
    if lemma in _LEMMA_PHRASE_INDEX:
        return _LEMMA_PHRASE_INDEX[lemma]
    if use_wordnet:
        wn = _wordnet_concept(lemma)
        if wn is not None:
            return wn
    return lemma


def concepts(text: str, *, use_wordnet: bool = False) -> list[str]:
    """Return the ordered list of concepts for ``text``.

    Tokenizes, lemmatizes, then performs a greedy longest-first n-gram scan
    against the thesaurus so multi-word concepts are recovered before their
    parts.
    """
    lemmas = [lemmatize(t) for t in tokenize(text)]
    out: list[str] = []
    i = 0
    n = len(lemmas)
    while i < n:
        matched = False
        upper = min(_MAX_PHRASE_WORDS, n - i)
        for width in range(upper, 1, -1):
            phrase = " ".join(lemmas[i : i + width])
            concept = _LEMMA_PHRASE_INDEX.get(phrase)
            if concept is not None:
                out.append(concept)
                i += width
                matched = True
                break
        if matched:
            continue
        out.append(concept_of(lemmas[i], use_wordnet=use_wordnet))
        i += 1
    return out


def concept_bag(text: str, *, use_wordnet: bool = False) -> Counter[str]:
    """Return the concept multiset (bag) for ``text``."""
    return Counter(concepts(text, use_wordnet=use_wordnet))


def concept_backend_versions(*, use_wordnet: bool = False) -> dict[str, str | None]:
    """Report the frozen resource versions behind concept mapping.

    Stamped into emitted records so a vectorization is reproducible. The
    WordNet version is only reported when the WordNet backend is actually
    engaged and importable.
    """
    wn_version: str | None = None
    if use_wordnet and _wordnet_concept("test") is not None:
        wn_version = WORDNET_VERSION
    return {"thesaurus": THESAURUS_VERSION, "wordnet": wn_version}


__all__ = [
    "concept_backend_versions",
    "concept_bag",
    "concept_of",
    "concepts",
]
