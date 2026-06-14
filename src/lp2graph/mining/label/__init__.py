"""M4 — two-stage labeling service with a versioned, self-growing store.

Public surface:

- :class:`ControlledVocabulary` / :func:`seed_vocabulary` — frozen label sets
  per (level, dimension), seeded from M3.
- :class:`RuleLayer` / :class:`SeedRule` — Stage-1 rules.
- :class:`LinearSVM` — Stage-2 calibrated linear SVM (one-vs-rest).
- :class:`LabelStore` / :class:`LabelRecord` / :class:`Decision` — the
  versioned label DB and replayable decision log.
- guardrails — :func:`score_gold`, :func:`drift`, :func:`cohen_kappa`,
  :func:`evaluate_guardrails`.
- :class:`LabelingService` / :class:`LoopConfig` / :class:`LoopReport` — the
  closed-loop orchestrator.

Deterministic given seed + versions.
"""

from __future__ import annotations

from lp2graph.mining.label.classifier import LinearSVM
from lp2graph.mining.label.features import entity_features
from lp2graph.mining.label.guardrails import (
    ClassScore,
    GoldScore,
    GuardrailReport,
    cohen_kappa,
    distribution,
    drift,
    evaluate_guardrails,
    score_gold,
)
from lp2graph.mining.label.loop import (
    HumanOracle,
    LabelingService,
    LoopConfig,
    LoopReport,
)
from lp2graph.mining.label.rules import RuleDecision, RuleLayer, SeedRule
from lp2graph.mining.label.store import (
    Decision,
    LabelRecord,
    LabelStore,
)
from lp2graph.mining.label.vocab import ControlledVocabulary, seed_vocabulary

__all__ = [
    "ClassScore",
    "ControlledVocabulary",
    "Decision",
    "GoldScore",
    "GuardrailReport",
    "HumanOracle",
    "LabelRecord",
    "LabelStore",
    "LabelingService",
    "LinearSVM",
    "LoopConfig",
    "LoopReport",
    "RuleDecision",
    "RuleLayer",
    "SeedRule",
    "cohen_kappa",
    "distribution",
    "drift",
    "entity_features",
    "evaluate_guardrails",
    "score_gold",
    "seed_vocabulary",
]
