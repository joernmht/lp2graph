"""Deterministic rule-based lemmatizer (M2).

Reduces inflected surface tokens to a base form so that ``constraints`` and
``constraint`` or ``orderings`` and ``ordering`` map to the same concept.
This is a small, conservative, fully deterministic stemmer-with-exceptions —
*not* a WordNet morphology engine. The point is reproducibility: the same
token always lemmatizes to the same base, with no model, corpus, or pinned
external resource in the loop. Genuine synonymy (not morphology) is handled
separately in :mod:`lp2graph.mining.homologize.concept`.
"""

from __future__ import annotations

# Irregular forms that the suffix rules below would get wrong. Kept small and
# biased toward tokens that actually occur in optimization/railway text.
_EXCEPTIONS: dict[str, str] = {
    "indices": "index",
    "matrices": "matrix",
    "vertices": "vertex",
    "buses": "bus",
    "data": "datum",
    "feet": "foot",
    "men": "man",
    "women": "woman",
    "analyses": "analysis",
    "bases": "basis",
    "axes": "axis",
    "is": "be",
    "are": "be",
    "was": "be",
    "were": "be",
    "has": "have",
    "running": "run",
}

# Suffixes that take "es" (drop the whole "es"), keyed by the preceding stem
# ending. Applied before the bare "-s" rule.
_ES_STEM_ENDINGS = ("s", "x", "z", "ch", "sh")


def lemmatize(token: str) -> str:
    """Return the base form of a single lowercase ``token``.

    Handles regular plural (``-s``/``-es``/``-ies``) and a couple of verb
    inflections (``-ing``/``-ed``) plus a small exception table. Tokens are
    only shortened when a reasonable stem (length ≥ 3) remains, so short
    domain abbreviations are left untouched.
    """
    if token in _EXCEPTIONS:
        return _EXCEPTIONS[token]

    # Plural: -ies -> -y  (capacities -> capacity)
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"

    # Plural: -es after a sibilant stem (boxes -> box, classes -> class)
    if token.endswith("es") and len(token) > 3:
        stem = token[:-2]
        if stem.endswith(_ES_STEM_ENDINGS):
            return stem

    # Plural: bare -s (but not -ss: "loss" stays "loss")
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]

    # Gerund: -ing -> stem (scheduling -> schedul... too aggressive; only when
    # the stem is a real-looking length and we restore a trailing 'e' when the
    # stem would otherwise end in a consonant cluster we cannot judge — keep it
    # simple and conservative: just drop -ing when stem length >= 4).
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]

    # Past tense: -ed -> stem
    if token.endswith("ed") and len(token) > 4:
        return token[:-2]

    return token


__all__ = ["lemmatize"]
