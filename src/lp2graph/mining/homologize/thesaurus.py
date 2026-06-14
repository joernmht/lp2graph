"""Frozen, versioned domain thesaurus (M2).

A small hand-curated synonym map for the railway-optimization domain. Each
entry collapses a family of surface phrases (already lowercased and
lemmatized) onto a single *concept* token. Multi-word phrases (e.g.
``rolling stock``) are supported and are matched greedily as bigrams before
unigrams in :mod:`lp2graph.mining.homologize.concept`.

The thesaurus is the deterministic, dependency-free backbone of concept
mapping; the optional WordNet backend only ever *adds* folding for tokens the
thesaurus does not cover. It is frozen and versioned
(:data:`~lp2graph.mining.versions.THESAURUS_VERSION`) so a change to the
synonym families is an explicit, diffable edit.
"""

from __future__ import annotations

from lp2graph.mining.versions import THESAURUS_VERSION

# concept -> list of synonym surface phrases (lowercased, lemmatized singular).
# Phrases may be one or two words. The concept itself need not appear in its
# own synonym list, but usually does for clarity.
_SYNONYM_FAMILIES: dict[str, tuple[str, ...]] = {
    "headway": ("headway", "spacing", "separation time", "time separation"),
    "rolling_stock": ("rolling stock", "rollingstock", "trainset", "train set", "fleet"),
    "precedence": ("precedence", "ordering", "order", "sequencing", "overtaking", "overtake"),
    "capacity": ("capacity", "throughput", "track capacity", "block capacity"),
    "timing": ("timing", "schedule", "timetable", "departure", "arrival", "dwell"),
    "delay": ("delay", "lateness", "tardiness", "deviation"),
    "routing": ("routing", "route", "path", "itinerary", "rerouting"),
    "assignment": ("assignment", "allocation", "matching", "covering"),
    "flow": ("flow", "flow conservation", "flow balance", "conservation"),
    "demand": ("demand", "passenger demand", "load", "requirement"),
    "cost": ("cost", "weight", "penalty", "price", "expense"),
    "robust": ("robust", "robustness", "recoverable", "uncertainty"),
    "periodic": ("periodic", "cyclic", "pesp", "period"),
    "platform": ("platform", "track", "siding"),
    "block": ("block", "block section", "section", "moving block"),
    "conflict": ("conflict", "incompatible", "incompatibility", "clash"),
    "rescheduling": ("rescheduling", "reschedule", "dispatching", "dispatch", "disruption"),
}


def _build_phrase_index() -> dict[str, str]:
    """Invert the synonym families to a phrase → concept lookup.

    Determinism: families are iterated in declaration order; on the rare
    collision (a phrase listed under two concepts) the first declaration
    wins, which is stable because dict insertion order is preserved.
    """
    index: dict[str, str] = {}
    for concept, phrases in _SYNONYM_FAMILIES.items():
        for phrase in phrases:
            index.setdefault(phrase, concept)
    return index


#: phrase (1-2 lemmatized words, space-joined) -> canonical concept token.
PHRASE_TO_CONCEPT: dict[str, str] = _build_phrase_index()

#: The longest phrase length (in words) present in the thesaurus; bounds the
#: n-gram window the concept mapper has to consider.
MAX_PHRASE_WORDS: int = max(len(p.split()) for p in PHRASE_TO_CONCEPT)


__all__ = [
    "MAX_PHRASE_WORDS",
    "PHRASE_TO_CONCEPT",
    "THESAURUS_VERSION",
]
