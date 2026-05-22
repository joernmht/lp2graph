"""Constraint-type classification by keyword matching.

Adapted from joernmht/raiLPminerExperimentation
(railpminer/analysis/constraints.py), MIT License. The keyword tables
are preserved; the integration consumes the canonical model rather than
the source repo's flat node lists.

Classification is heuristic and intentionally so. It complements the
declarative ``constraint.kind`` field (which the formulation author
sets explicitly): ``classify_constraints`` infers the same kinds from
free-form text in name and description, useful for catalog audits and
for cross-checking author-supplied kinds.
"""

from __future__ import annotations

import re

from lp2graph.core.model import Formulation
from lp2graph.metrics.result import MetricResult

CONSTRAINT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "ordering": [
        r"\bprecedence\b", r"\border\b", r"\bordering\b",
        r"\bovertaking\b", r"\bovertake\b", r"\bre-?ordering\b",
    ],
    "routing": [
        r"\broute\s+selection\b", r"\brouting\b", r"\brerouting\b",
        r"\bre-?routing\b",
    ],
    "timing": [
        r"\bdepart(ure)?\b", r"\bdwell\b", r"\bdelay\b",
        r"\bscheduled\b", r"\brunning\s+time\b",
        r"\bminimum\s+duration\b", r"\bre-?timing\b",
    ],
    "cancellation": [
        r"\bcancel(l?ation|l?ed|l?ing)?\b",
        r"\btrain\s+service\s+balance\b",
        r"\bunbalanced\s+timetable\b",
    ],
    "headway": [
        r"\bheadway\b", r"\bconflict-free\b",
        r"\bincompatible\s+arc\b", r"\btrain\s+incompatibility\b",
    ],
    "capacity": [
        r"\binfrastructure\s+capacity\b", r"\btrack\s+capacity\b",
        r"\bstation\s+capacity\b", r"\bblock\s+section\b",
        r"\bsingle-?track\b", r"\bno-?store\b",
    ],
    "flow_balance": [
        r"\bflow\s+balance\b", r"\bflow\s+conservation\b",
    ],
    "big_m": [
        r"\blarge\s+constant\b", r"\bbig-?M\s+constraint\b",
        r"\bbig-?M\b",
    ],
    "passenger_connection": [
        r"\bminimum\s+transfer\s+time\b",
        r"\bpassenger\s+connection\b",
    ],
    "rolling_stock_connection": [
        r"\brolling\s+stock\s+connection\b",
    ],
}


def classify_constraints(f: Formulation) -> MetricResult:
    """Heuristic classification of every constraint by keyword matches.

    Returns a dict mapping constraint name to a list of matched type
    tags. Empty list means no keyword matched. The overall ``value`` is
    the per-tag count summary.
    """
    matrix: dict[str, list[str]] = {}
    type_counts: dict[str, int] = {tag: 0 for tag in CONSTRAINT_TYPE_KEYWORDS}

    for c in f.constraints:
        haystack = f"{c.name} {c.description}"
        matched: list[str] = []
        for tag, patterns in CONSTRAINT_TYPE_KEYWORDS.items():
            joined = "|".join(patterns)
            if re.search(joined, haystack, re.IGNORECASE):
                matched.append(tag)
                type_counts[tag] += 1
        matrix[c.name] = matched

    classified = sum(1 for tags in matrix.values() if tags)
    return MetricResult(
        name="classify_constraints",
        value=type_counts,
        explanation=(
            f"Classified {classified}/{len(matrix)} constraint(s) by keyword."
        ),
        data={"matrix": matrix, "total": len(matrix), "classified": classified},
    )


__all__ = ["CONSTRAINT_TYPE_KEYWORDS", "classify_constraints"]
