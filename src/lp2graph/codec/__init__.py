"""Deterministic, reversible LaTeX <-> canonical-model codec.

This subpackage adds a *bidirectional, deterministic* text interface on
top of the canonical model:

- :func:`to_canonical_latex` renders a :class:`~lp2graph.core.model.Formulation`
  as a paper-style LaTeX document (``\\mathcal`` index sets, ``\\sum``,
  ``\\forall`` quantifiers, big-M, ...). The algebra is genuine LaTeX an
  author could paste into a paper; a compact ``%@`` annotation header
  carries the non-algebraic metadata (kinds, roles, descriptions, ...).

- :func:`from_canonical_latex` parses that document back into a
  ``Formulation``. The parse is *deterministic*: same text in, same model
  out, no model/LLM in the loop.

The two functions are inverses up to a documented normalization
(:func:`lp2graph.codec.normalize.canonical_normal_form`). The strongest
guarantee the codec offers — and the one the tests assert — is text-level
idempotence::

    to_canonical_latex(from_canonical_latex(to_canonical_latex(f))) == to_canonical_latex(f)

i.e. the LaTeX serialization is a fixed point. The *solvable* content
(sets, parameters, variables, constraints, objective) round-trips
exactly; only incidental labels (a literal term's ``ref`` name, a
redundant ``offset`` field that disagrees with its own ``expr``) are
normalized.

See :mod:`lp2graph.codec.latex` for the grammar.
"""

from __future__ import annotations

from lp2graph.codec.latex import from_canonical_latex, to_canonical_latex
from lp2graph.codec.normalize import canonical_normal_form

__all__ = [
    "canonical_normal_form",
    "from_canonical_latex",
    "to_canonical_latex",
]
