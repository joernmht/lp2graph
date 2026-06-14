"""Tokenizer and versioned stop-list (M2, lexical front-end).

Names in the canonical model are identifier-shaped (``headway_separation``,
``rolling_stock``, ``x_{i,t}``) and descriptions are free prose. Both have
to be reduced to a comparable bag of surface tokens before concept mapping.
The tokenizer is deterministic and does only structural work — splitting,
case-folding, and stop-word removal — leaving morphological folding to
:mod:`lp2graph.mining.homologize.lemmatize` and synonymy to
:mod:`lp2graph.mining.homologize.concept`.

The stop-list is *versioned* (:data:`~lp2graph.mining.versions.LEXICON_VERSION`):
it combines English function words with a small domain stop-list of
optimization boilerplate (``constraint``, ``variable``, ``model``, ...)
that is too common across formulations to discriminate between them.
"""

from __future__ import annotations

import re

from lp2graph.mining.versions import LEXICON_VERSION

# English function words — closed-class tokens that carry no concept.
_FUNCTION_WORDS: frozenset[str] = frozenset(
    [
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "from",
        "by",
        "with",
        "without",
        "within",
        "and",
        "or",
        "not",
        "nor",
        "but",
        "so",
        "as",
        "is",
        "are",
        "be",
        "been",
        "being",
        "am",
        "was",
        "were",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "can",
        "could",
        "may",
        "might",
        "must",
        "if",
        "then",
        "else",
        "when",
        "while",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "what",
        "how",
        "than",
        "into",
        "over",
        "under",
        "between",
        "among",
        "per",
        "each",
        "every",
        "all",
        "any",
        "some",
        "no",
        "none",
        "both",
        "either",
        "neither",
        "such",
        "same",
        "other",
        "another",
        "its",
        "it",
        "their",
        "our",
        "your",
        "his",
        "her",
        "my",
        "we",
        "you",
        "they",
        "he",
        "she",
        "them",
        "us",
        "him",
        "me",
        "i",
        "here",
        "there",
        "about",
        "above",
        "below",
        "up",
        "down",
        "out",
        "off",
        "only",
        "also",
        "more",
        "most",
        "less",
        "least",
        "very",
        "much",
        "many",
        "few",
        "several",
        "whether",
        "due",
        "via",
        "given",
        "using",
        "used",
        "use",
        "uses",
    ]
)

# Domain stop-list: optimization/modeling boilerplate that appears in almost
# every formulation and therefore cannot separate one from another. Frozen
# and versioned together with the function words.
_DOMAIN_STOP_WORDS: frozenset[str] = frozenset(
    [
        "constraint",
        "constraints",
        "variable",
        "variables",
        "parameter",
        "parameters",
        "model",
        "models",
        "problem",
        "problems",
        "formulation",
        "formulations",
        "objective",
        "set",
        "sets",
        "index",
        "indices",
        "value",
        "values",
        "number",
        "numbers",
        "term",
        "terms",
        "equation",
        "equations",
        "expression",
        "decision",
        "define",
        "defines",
        "defined",
        "definition",
        "denote",
        "denotes",
        "let",
        "given",
        "total",
    ]
)

#: The frozen, versioned stop-list applied by :func:`tokenize`.
STOPLIST: frozenset[str] = _FUNCTION_WORDS | _DOMAIN_STOP_WORDS

#: Minimum surviving token length (single characters are dropped — bare index
#: letters such as ``i``/``t`` carry no lexical concept).
MIN_TOKEN_LENGTH = 2

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z])(?=[A-Z])")
_LETTER_DIGIT_BOUNDARY = re.compile(r"(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])")
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")
_PURE_DIGITS = re.compile(r"^[0-9]+$")
# LaTeX control sequences (\sum, \forall, ...) are stripped wholesale: they are
# structure, not concepts.
_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+")


def split_compounds(text: str) -> list[str]:
    """Split ``text`` into lowercase surface tokens.

    Splits ``camelCase`` boundaries, letter/digit boundaries (``x1`` →
    ``x``, ``1``), and any run of non-alphanumeric characters (so
    ``rolling_stock``, ``x_{i,t}``, and ``big-M`` all break apart).
    """
    text = _LATEX_COMMAND.sub(" ", text)
    text = _CAMEL_BOUNDARY.sub(" ", text)
    text = _LETTER_DIGIT_BOUNDARY.sub(" ", text)
    text = _NON_ALNUM.sub(" ", text)
    return text.lower().split()


def tokenize(text: str) -> list[str]:
    """Tokenize ``text`` into kept surface tokens.

    Pipeline: split compounds → case-fold → drop pure-digit tokens,
    sub-:data:`MIN_TOKEN_LENGTH` tokens, and stop-words. Order is
    preserved (it is meaningful for bigram concept lookup downstream).
    """
    out: list[str] = []
    for tok in split_compounds(text):
        if len(tok) < MIN_TOKEN_LENGTH:
            continue
        if _PURE_DIGITS.match(tok):
            continue
        if tok in STOPLIST:
            continue
        out.append(tok)
    return out


__all__ = [
    "LEXICON_VERSION",
    "MIN_TOKEN_LENGTH",
    "STOPLIST",
    "split_compounds",
    "tokenize",
]
