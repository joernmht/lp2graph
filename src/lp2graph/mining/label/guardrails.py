"""Closed-loop guardrails: gold-set scoring, drift, kappa, rollback (M4).

The self-growing loop is only safe if it is watched. Each loop re-scores a
held-out gold set and compares against the previous loop:

- **per-class precision / recall** and overall (micro) precision;
- **drift** — how much the predicted label distribution shifted between loops;
- **rollback flag** — set when gold-set precision *decreased*, the signal the
  acceptance criterion turns on ("gold-set precision non-decreasing across
  loops, else flagged");
- **inter-annotator agreement** — Cohen's κ, for auditing human adjudications.

All metrics are deterministic functions of their inputs.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ClassScore:
    """Precision / recall / support for one class."""

    label: str
    precision: float
    recall: float
    support: int


@dataclass(frozen=True, slots=True)
class GoldScore:
    """Gold-set scoring result for one loop."""

    micro_precision: float
    per_class: tuple[ClassScore, ...]
    n_scored: int
    per_class_map: dict[str, ClassScore] = field(default_factory=dict)


def score_gold(predictions: Mapping[str, str], gold: Mapping[str, str]) -> GoldScore:
    """Score ``predictions`` against ``gold`` (both entity_id → label).

    Only entities present in ``gold`` are scored. Micro precision is the
    fraction of scored entities labeled correctly.
    """
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)
    support: dict[str, int] = defaultdict(int)
    correct = 0
    scored = 0
    for entity_id, true_label in gold.items():
        support[true_label] += 1
        scored += 1
        pred = predictions.get(entity_id)
        if pred is None:
            fn[true_label] += 1
            continue
        if pred == true_label:
            tp[true_label] += 1
            correct += 1
        else:
            fp[pred] += 1
            fn[true_label] += 1

    labels = sorted(set(support) | set(tp) | set(fp) | set(fn))
    per_class: list[ClassScore] = []
    for lab in labels:
        denom_p = tp[lab] + fp[lab]
        denom_r = tp[lab] + fn[lab]
        precision = tp[lab] / denom_p if denom_p else 0.0
        recall = tp[lab] / denom_r if denom_r else 0.0
        per_class.append(
            ClassScore(label=lab, precision=precision, recall=recall, support=support[lab])
        )
    micro = correct / scored if scored else 0.0
    return GoldScore(
        micro_precision=micro,
        per_class=tuple(per_class),
        n_scored=scored,
        per_class_map={cs.label: cs for cs in per_class},
    )


def distribution(labels: Sequence[str]) -> dict[str, float]:
    """Normalized label frequency distribution."""
    if not labels:
        return {}
    counts: dict[str, int] = defaultdict(int)
    for lab in labels:
        counts[lab] += 1
    n = len(labels)
    return {lab: counts[lab] / n for lab in sorted(counts)}


def drift(prev: Sequence[str], curr: Sequence[str]) -> float:
    """Total-variation distance between two label distributions in ``[0, 1]``."""
    p = distribution(prev)
    q = distribution(curr)
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's κ between two annotators' label sequences (same order).

    Returns 1.0 for perfect agreement; 0.0 for chance-level. Defined as 1.0
    when both annotators are constant and agree.
    """
    if len(a) != len(b):
        raise ValueError("annotator sequences must have equal length")
    n = len(a)
    if n == 0:
        return 1.0
    agree = sum(1 for x, y in zip(a, b, strict=True) if x == y)
    po = agree / n
    dist_a = distribution(a)
    dist_b = distribution(b)
    pe = sum(dist_a.get(k, 0.0) * dist_b.get(k, 0.0) for k in set(dist_a) | set(dist_b))
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


@dataclass(frozen=True, slots=True)
class GuardrailReport:
    """Guardrail outcome for one loop, including the rollback signal."""

    loop: int
    gold: GoldScore
    previous_precision: float | None
    precision_delta: float | None
    rollback: bool
    drift: float


def evaluate_guardrails(
    loop: int,
    gold_score: GoldScore,
    *,
    previous_precision: float | None,
    label_drift: float,
) -> GuardrailReport:
    """Assemble the guardrail report and set the rollback flag.

    ``rollback`` is True iff precision strictly decreased versus the previous
    loop — the "else flagged" branch of the acceptance criterion.
    """
    delta: float | None = None
    rollback = False
    if previous_precision is not None:
        delta = gold_score.micro_precision - previous_precision
        rollback = delta < 0.0
    return GuardrailReport(
        loop=loop,
        gold=gold_score,
        previous_precision=previous_precision,
        precision_delta=delta,
        rollback=rollback,
        drift=label_drift,
    )


__all__ = [
    "ClassScore",
    "GoldScore",
    "GuardrailReport",
    "cohen_kappa",
    "distribution",
    "drift",
    "evaluate_guardrails",
    "score_gold",
]
