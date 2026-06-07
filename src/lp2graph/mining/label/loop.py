"""The two-stage closed-loop labeling service (M4 orchestrator).

Ties the pieces together into the self-growing loop the method describes:

1. **Stage 1 (rules)** propose a label or abstain.
2. **Stage 2 (classifier)** proposes a calibrated label + confidence.
3. **Gating** combines rule-consistency with the confidence gates
   ``theta_low`` / ``theta_high`` into one of *auto-accept* / *human-adjudicate*
   / *defer*.
4. **Write-back** records every accepted label (stamped with versions) and
   logs every decision.
5. **Promotion** turns confirmed ``concept → label`` associations from human
   adjudications into new rules (re-versioning the lexicon).
6. **Retrain** the classifier on the confirmed labels.
7. **Guardrails** re-score a held-out gold set, measure drift, and raise the
   rollback flag if precision dropped.

Everything is deterministic given ``(seed, versions)``: same inputs and same
human oracle reproduce the store and every report bit-for-bit.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from lp2graph.mining.homologize.entity import Entity
from lp2graph.mining.label.classifier import LinearSVM
from lp2graph.mining.label.features import entity_features
from lp2graph.mining.label.guardrails import (
    GuardrailReport,
    drift,
    evaluate_guardrails,
    score_gold,
)
from lp2graph.mining.label.rules import RuleLayer, SeedRule
from lp2graph.mining.label.store import Decision, LabelRecord, LabelStore
from lp2graph.mining.label.vocab import ControlledVocabulary

#: A human (or gold) oracle: returns a label for an entity, or ``None`` to
#: signal "cannot decide" (which defers the entity).
HumanOracle = Callable[[Entity], str | None]


@dataclass(frozen=True, slots=True)
class LoopConfig:
    """Confidence gates and determinism knobs for the closed loop."""

    theta_low: float = 0.40
    theta_high: float = 0.70
    seed: int = 0
    corpus_version: str = "corpus-0"


@dataclass(frozen=True, slots=True)
class LoopReport:
    """Per-loop summary."""

    loop: int
    n_auto_accept: int
    n_adjudicate: int
    n_defer: int
    promoted_rules: tuple[SeedRule, ...]
    lexicon_version: str
    clf_version: str
    guardrail: GuardrailReport
    label_distribution: dict[str, float]


@dataclass
class LabelingService:
    """Stateful driver of the closed-loop labeling process."""

    vocabulary: ControlledVocabulary
    rule_layer: RuleLayer
    classifier: LinearSVM
    store: LabelStore
    gold_entities: tuple[Entity, ...]
    gold_labels: Mapping[str, str]
    config: LoopConfig
    _loop: int = 0
    _prev_precision: float | None = None
    _prev_gold_predictions: tuple[str, ...] = ()
    _train_labels: dict[str, str] = field(default_factory=dict)
    _entities_by_id: dict[str, Entity] = field(default_factory=dict)

    @classmethod
    def bootstrap(
        cls,
        vocabulary: ControlledVocabulary,
        seed_rules: Sequence[SeedRule],
        gold_entities: Sequence[Entity],
        gold_labels: Mapping[str, str],
        config: LoopConfig | None = None,
    ) -> LabelingService:
        """Create a fresh service with an empty store and an untrained model."""
        cfg = config or LoopConfig()
        rule_layer = RuleLayer(rules=tuple(seed_rules), version=vocabulary.version)
        empty_clf = LinearSVM(
            classes=(),
            features=(),
            weights={},
            biases={},
            calib_scale=1.5,
            version=vocabulary.version,
        )
        svc = cls(
            vocabulary=vocabulary,
            rule_layer=rule_layer,
            classifier=empty_clf,
            store=LabelStore.empty(),
            gold_entities=tuple(gold_entities),
            gold_labels=dict(gold_labels),
            config=cfg,
        )
        for e in gold_entities:
            svc._entities_by_id.setdefault(e.id, e)
        return svc

    # -- internals -------------------------------------------------------

    def _features(self, entity: Entity) -> dict[str, float]:
        return entity_features(entity)

    def _gate(
        self, rule_label: str | None, rule_conflict: bool, clf_label: str, clf_conf: float
    ) -> str:
        """Return the gate: ``auto_accept`` / ``adjudicate`` / ``defer``."""
        if not self.classifier.is_trained:
            # Bootstrap loop: trust unambiguous rules, adjudicate the rest.
            if rule_label is not None and not rule_conflict:
                return "auto_accept"
            return "adjudicate"
        if rule_conflict:
            return "adjudicate"
        agree = rule_label is not None and rule_label == clf_label
        if clf_conf >= self.config.theta_high and (rule_label is None or agree):
            return "auto_accept"
        if clf_conf < self.config.theta_low:
            return "defer"
        return "adjudicate"

    def _predict_label(self, entity: Entity) -> str:
        feats = self._features(entity)
        if self.classifier.is_trained:
            label, _conf = self.classifier.predict(feats)
            return label
        decision = self.rule_layer.apply(feats)
        return decision.label or "unassigned"

    def _promote_rules(self, loop: int) -> list[SeedRule]:
        """Promote unambiguous ``concept → human-label`` associations to rules.

        A concept feature is promoted when, across this loop's human
        adjudications, it co-occurs with exactly one label. Existing rule
        antecedents are not re-promoted.
        """
        concept_labels: dict[str, set[str]] = {}
        for d in self.store.decisions:
            if d.loop != loop or d.source != "human" or d.final_value is None:
                continue
            entity = self._entities_by_id.get(d.entity_id)
            if entity is None:
                continue
            for feat in self._features(entity):
                if feat.startswith("concept:"):
                    concept_labels.setdefault(feat, set()).add(d.final_value)
        existing = {(r.antecedent, r.label) for r in self.rule_layer.rules}
        promoted: list[SeedRule] = []
        for antecedent in sorted(concept_labels):
            labels = concept_labels[antecedent]
            if len(labels) != 1:
                continue
            label = next(iter(labels))
            if (antecedent, label) in existing:
                continue
            promoted.append(SeedRule(antecedent=antecedent, label=label, confidence=0.9))
        return promoted

    def _retrain(self, loop: int) -> LinearSVM:
        ids = sorted(self._train_labels)
        x = [self._features(self._entities_by_id[i]) for i in ids]
        y = [self._train_labels[i] for i in ids]
        if not y:
            return self.classifier
        return LinearSVM.train(
            x,
            y,
            seed=self.config.seed,
            version=f"{self.vocabulary.version}+loop{loop}",
        )

    # -- main loop -------------------------------------------------------

    def run_loop(self, entities: Sequence[Entity], oracle: HumanOracle) -> LoopReport:
        """Run one closed-loop pass over ``entities`` and return its report."""
        loop = self._loop
        n_auto = n_adj = n_defer = 0
        lexicon_version = self.rule_layer.version
        clf_version = self.classifier.version

        for entity in entities:
            self._entities_by_id.setdefault(entity.id, entity)
            feats = self._features(entity)
            rule = self.rule_layer.apply(feats)
            clf_label, clf_conf = self.classifier.predict(feats)
            gate = self._gate(rule.label, rule.conflict, clf_label, clf_conf)

            final_value: str | None = None
            source: str | None = None
            if gate == "auto_accept":
                if rule.label is not None:
                    final_value, source = rule.label, "rule"
                else:
                    final_value, source = clf_label, "clf"
                n_auto += 1
            elif gate == "adjudicate":
                human = oracle(entity)
                if human is None:
                    gate = "defer"
                    n_defer += 1
                else:
                    final_value, source = human, "human"
                    n_adj += 1
            else:  # defer
                n_defer += 1

            decision = Decision(
                entity_id=entity.id,
                level=self.vocabulary.level,
                dimension=self.vocabulary.dimension,
                rule_label=rule.label,
                rule_confidence=rule.confidence,
                clf_label=clf_label,
                clf_confidence=clf_conf,
                gate=gate,  # type: ignore[arg-type]
                final_value=final_value,
                source=source,  # type: ignore[arg-type]
                loop=loop,
                lexicon_version=lexicon_version,
                clf_version=clf_version,
                corpus_version=self.config.corpus_version,
            )
            self.store.log(decision)

            if final_value is not None and source is not None:
                if source == "rule":
                    record_conf = rule.confidence
                elif source == "human":
                    record_conf = 1.0
                else:
                    record_conf = clf_conf
                self.store.write(
                    LabelRecord(
                        entity_id=entity.id,
                        level=self.vocabulary.level,
                        dimension=self.vocabulary.dimension,
                        value=final_value,
                        source=source,  # type: ignore[arg-type]
                        confidence=record_conf,
                        lexicon_version=lexicon_version,
                        clf_version=clf_version,
                        corpus_version=self.config.corpus_version,
                        loop=loop,
                    )
                )
                # Confirmed labels (rule/human) feed retraining; clf
                # auto-accepts are not self-trained on.
                if source in ("rule", "human"):
                    self._train_labels[entity.id] = final_value

        # Promote rules, retrain, then re-score the gold set.
        promoted = self._promote_rules(loop)
        if promoted:
            self.rule_layer = self.rule_layer.with_rules(
                promoted, version=f"{self.vocabulary.version}+loop{loop}"
            )
        self.classifier = self._retrain(loop)

        gold_predictions = {e.id: self._predict_label(e) for e in self.gold_entities}
        gold_score = score_gold(gold_predictions, self.gold_labels)
        curr_pred_seq = tuple(gold_predictions[e.id] for e in self.gold_entities)
        label_drift = (
            drift(self._prev_gold_predictions, curr_pred_seq)
            if self._prev_gold_predictions
            else 0.0
        )
        guardrail = evaluate_guardrails(
            loop,
            gold_score,
            previous_precision=self._prev_precision,
            label_drift=label_drift,
        )

        self._prev_precision = gold_score.micro_precision
        self._prev_gold_predictions = curr_pred_seq
        self._loop += 1

        from lp2graph.mining.label.guardrails import distribution

        return LoopReport(
            loop=loop,
            n_auto_accept=n_auto,
            n_adjudicate=n_adj,
            n_defer=n_defer,
            promoted_rules=tuple(promoted),
            lexicon_version=self.rule_layer.version,
            clf_version=self.classifier.version,
            guardrail=guardrail,
            label_distribution=distribution(list(curr_pred_seq)),
        )


__all__ = ["HumanOracle", "LabelingService", "LoopConfig", "LoopReport"]
