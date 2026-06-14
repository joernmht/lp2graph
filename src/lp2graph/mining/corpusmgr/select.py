"""Reproducible representative selection per cluster (M5).

Given named clusters (cluster name -> member indices) and the aligned
provenance records, :func:`select_representatives` picks one member per
cluster to carry forward into validation. The rule is a pure, documented,
deterministic function:

1. Pick the member with the highest ``citation_count``
   (``reason="highest_citation"``).
2. If *every* member has ``citation_count == 0`` (no citation signal at all),
   fall back to the next-highest member that *does* have a non-zero count;
   only when none exists is the cluster considered to have no signal
   (``reason="next_highest_fallback"`` once a non-zero member is found).
3. If the cluster is empty or still has no usable member, fall back to the
   index supplied in ``benchmark_fallback[cluster]``
   (``reason="benchmark_fallback"``).

Ties at every step break by best quality tier, then lowest index, so the
ranking is total and reproducible.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from lp2graph.mining.corpusmgr.record import ProvenanceRecord

SelectionReason = Literal[
    "highest_citation",
    "next_highest_fallback",
    "benchmark_fallback",
]


@dataclass(frozen=True, slots=True)
class RepresentativeChoice:
    """The selection outcome for one cluster.

    ``chosen_index`` is the selected member (or the benchmark-fallback
    index); ``reason`` records which rule fired; ``ranked_candidates`` is the
    full member ranking (best first) under the documented tie-break, for
    auditing and reproducibility.
    """

    chosen_index: int | None
    reason: SelectionReason
    ranked_candidates: tuple[int, ...]


def _rank_key(record: ProvenanceRecord, index: int) -> tuple[int, int, int]:
    """Sort key: higher citation first, then best tier, then lowest index."""
    return (-record.citation_count, record.quality_rank, index)


def _rank_members(members: Sequence[int], records: Sequence[ProvenanceRecord]) -> tuple[int, ...]:
    return tuple(sorted(members, key=lambda i: _rank_key(records[i], i)))


def select_representatives(
    clusters: Mapping[str, Sequence[int]],
    records: Sequence[ProvenanceRecord],
    *,
    benchmark_fallback: Mapping[str, int] | None = None,
) -> dict[str, RepresentativeChoice]:
    """Pick a reproducible representative for each named cluster.

    See the module docstring for the exact, deterministic rule. Returns a
    mapping from cluster name to :class:`RepresentativeChoice`.
    """
    fallback = benchmark_fallback or {}
    out: dict[str, RepresentativeChoice] = {}

    for name in sorted(clusters):
        members = list(clusters[name])
        ranked = _rank_members(members, records)

        if not ranked:
            out[name] = RepresentativeChoice(
                chosen_index=fallback.get(name),
                reason="benchmark_fallback",
                ranked_candidates=(),
            )
            continue

        top = ranked[0]
        if records[top].citation_count > 0:
            out[name] = RepresentativeChoice(
                chosen_index=top,
                reason="highest_citation",
                ranked_candidates=ranked,
            )
            continue

        # All members have zero citation signal -> look for any non-zero
        # member (none exist here, but the search is explicit and ordered),
        # else fall back to a benchmark index if provided.
        non_zero = next((i for i in ranked if records[i].citation_count > 0), None)
        if non_zero is not None:
            out[name] = RepresentativeChoice(
                chosen_index=non_zero,
                reason="next_highest_fallback",
                ranked_candidates=ranked,
            )
        elif name in fallback:
            out[name] = RepresentativeChoice(
                chosen_index=fallback[name],
                reason="benchmark_fallback",
                ranked_candidates=ranked,
            )
        else:
            # No citation signal and no benchmark fallback: still pick the
            # documented top-of-ranking, but record it as a fallback.
            out[name] = RepresentativeChoice(
                chosen_index=top,
                reason="next_highest_fallback",
                ranked_candidates=ranked,
            )

    return out


__all__ = [
    "RepresentativeChoice",
    "SelectionReason",
    "select_representatives",
]
