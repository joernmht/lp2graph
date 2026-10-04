"""Which loops an aggregated term runs over: one reading for every consumer.

A canonical :class:`~lp2graph.core.model.Term` with ``operator="sum"`` stores
the families its binder ranges over (``operator_over``) and, per slot of the
referenced template, a :class:`~lp2graph.core.model.Binding` whose ``expr``
names the dummy that feeds the slot. The binder's own dummy names are not
stored, so every consumer has to pair the summed families with the dummies the
bindings use. The LaTeX emitter, the ground view and the solver back-end used
to do that pairing three different ways, and they disagreed (issue #60):

- the grounder looped only over the dummies the referent uses, so
  ``\\sum_{i \\in I, r \\in R} dur_r`` grounded to ``\\sum_r dur_r``;
- the ground view keyed its loop scope by family but resolved bindings by
  dummy, so every summed term lost its edges;
- the emitter paired a family with the first binding of that family, so
  ``\\sum_{j \\in I} x_{i,j}`` under ``\\forall i \\in I`` was printed as
  ``\\sum_{i \\in I} x_{i,j}``, and ``\\sum_{t \\in T} x_{t-1}`` as the
  unparseable ``\\sum_{t-1 \\in T} x_{t-1}``.

This module is the single reading they now share. A family of
``operator_over`` takes the first *free* dummy (one the enclosing quantifiers
do not bind) whose slot family it is; a family no dummy matches is a loop the
referent does not vary with, which repeats the summand once per element
(``\\sum_{i \\in I} c = |I| c``).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from lp2graph.core.model import Term


class AggregationError(ValueError):
    """A summed family and a free dummy disagree, so the loops are ambiguous."""


@dataclass(frozen=True)
class Loop:
    """One loop of an aggregation.

    ``dummy`` is the identifier the referent's bindings use for the loop, or
    ``None`` when the referent does not vary with it.
    """

    family: str
    dummy: str | None


def binding_base(expr: str) -> str:
    """The leading identifier of a binding expression (``t-1`` -> ``t``)."""
    out: list[str] = []
    for ch in expr.strip():
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            break
    return "".join(out)


def free_dummies(term: Term, bound: Collection[str]) -> tuple[tuple[str, str], ...]:
    """``(dummy, slot family)`` of every binding the enclosing scope leaves
    free, deduplicated, in order of first use."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for b in term.bindings:
        base = binding_base(b.expr)
        if base and base not in bound and base not in seen:
            out.append((base, b.index))
            seen.add(base)
    return tuple(out)


def _pair(term: Term, bound: Collection[str]) -> tuple[list[Loop], list[tuple[str, str]]]:
    """Pair ``operator_over`` with the free dummies; return the loops in
    ``operator_over`` order and the free dummies no family took."""
    free = free_dummies(term, bound)
    taken: set[str] = set()
    loops: list[Loop] = []
    for fam in term.operator_over:
        pick = next((d for d, f in free if f == fam and d not in taken), None)
        if pick is not None:
            taken.add(pick)
        loops.append(Loop(family=fam, dummy=pick))
    return loops, [(d, f) for d, f in free if d not in taken]


def binder_loops(term: Term, bound: Collection[str]) -> tuple[Loop, ...]:
    """The loops the term's binder states, in ``operator_over`` order.

    This is the emitter's reading: it reproduces the binder as written. A
    family whose slot family disagrees with the dummy that fills it
    (``\\sum_{k \\in K} x_{k}`` with ``x`` declared over ``I``) is paired with
    the leftover dummies in order, so the text comes back as it went in.
    """
    loops, left = _pair(term, bound)
    rest = iter(left)
    out: list[Loop] = []
    for loop in loops:
        if loop.dummy is None:
            nxt = next(rest, None)
            if nxt is not None:
                loop = Loop(family=loop.family, dummy=nxt[0])
        out.append(loop)
    return tuple(out)


def aggregation_loops(term: Term, bound: Collection[str]) -> tuple[Loop, ...]:
    """The loops a ``sum`` or ``abs`` term runs over when it is evaluated.

    Dummy loops come first, in order of first use (the iteration order the
    grounder has always had), then the loops the referent does not vary with.
    A free dummy no summed family takes is aggregated over its slot family:
    that is how ``abs`` terms and models written before ``operator_over`` was
    populated have always been read (``|t_i|`` under a free ``i`` is
    ``sum_i |t_i|``).

    Raises:
        AggregationError: a summed family found no dummy while a free dummy
            found no family. The binder and the referent's declared shape
            disagree, and which elements the dummy then denotes is not in the
            model.
    """
    loops, left = _pair(term, bound)
    orphans = [loop.family for loop in loops if loop.dummy is None]
    if orphans and left:
        raise AggregationError(
            f"term {term.ref!r}: summed famil{'y' if len(orphans) == 1 else 'ies'} "
            f"{orphans!r} and free dumm{'y' if len(left) == 1 else 'ies'} "
            f"{[d for d, _ in left]!r} (slot families {[f for _, f in left]!r}) "
            "do not pair; the binder and the referenced template's shape disagree"
        )
    first_use = {d: k for k, (d, _) in enumerate(free_dummies(term, bound))}
    named = sorted(
        [loop for loop in loops if loop.dummy is not None]
        + [Loop(family=f, dummy=d) for d, f in left],
        key=lambda loop: first_use[loop.dummy or ""],
    )
    return (*named, *(loop for loop in loops if loop.dummy is None))


__all__ = [
    "AggregationError",
    "Loop",
    "aggregation_loops",
    "binder_loops",
    "binding_base",
    "free_dummies",
]
