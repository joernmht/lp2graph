"""Tests for M4 — labeling service with closed-loop store."""

from __future__ import annotations

from pathlib import Path

from lp2graph import load
from lp2graph.mining.homologize import corpus_entities
from lp2graph.mining.label import (
    ControlledVocabulary,
    LabelingService,
    LabelStore,
    LinearSVM,
    LoopConfig,
    RuleLayer,
    SeedRule,
    cohen_kappa,
    evaluate_guardrails,
    score_gold,
    seed_vocabulary,
)

ROOT = Path(__file__).resolve().parents[2]
FORMULATIONS = ROOT / "formulations"

# Coarse constraint-family taxonomy: several structural kinds map onto one
# family, so the label is correlated with — but not equal to — the kind.
_FAMILY = {
    "headway": "separation",
    "block_occupation": "separation",
    "moving_block": "separation",
    "ordering": "sequencing",
    "capacity": "resource",
    "set_packing": "resource",
    "flow_balance": "flow",
    "big_m": "linking",
    "indicator": "linking",
    "dwell": "timing",
    "modulo": "timing",
    "robust": "robust",
}


def _family(kind: str) -> str:
    return _FAMILY.get(kind, "generic")


def _setup():
    forms = [load(p) for p in sorted(FORMULATIONS.rglob("*.json"))]
    ents = corpus_entities(forms, "C")
    truth = {e.id: _family(e.signature.kind) for e in ents}
    gold = ents[::3]
    pool = [e for e in ents if e not in gold]
    vocab = seed_vocabulary("C", "constraint_family", set(truth.values()))
    seed_rules = [SeedRule("concept:headway", "separation")]
    gold_labels = {e.id: truth[e.id] for e in gold}
    return pool, gold, gold_labels, truth, vocab, seed_rules


def _run_two_loops(seed: int = 0):
    pool, gold, gold_labels, truth, vocab, seed_rules = _setup()
    svc = LabelingService.bootstrap(vocab, seed_rules, gold, gold_labels, LoopConfig(seed=seed))

    def oracle(entity):
        return truth.get(entity.id)

    r1 = svc.run_loop(pool, oracle)
    r2 = svc.run_loop(pool, oracle)
    return svc, r1, r2


# --- unit: classifier ------------------------------------------------------


def test_classifier_learns_separable_data() -> None:
    x = [
        {"a": 1.0},
        {"a": 1.0, "b": 0.1},
        {"c": 1.0},
        {"c": 1.0, "d": 0.1},
    ]
    y = ["A", "A", "C", "C"]
    clf = LinearSVM.train(x, y, seed=0, epochs=80)
    assert clf.predict({"a": 1.0})[0] == "A"
    assert clf.predict({"c": 1.0})[0] == "C"
    # Calibrated confidence is a real probability in (0, 1].
    _label, conf = clf.predict({"a": 1.0})
    assert 0.0 < conf <= 1.0


def test_classifier_is_deterministic() -> None:
    x = [{"a": 1.0}, {"b": 1.0}, {"a": 1.0, "b": 1.0}]
    y = ["A", "B", "A"]
    a = LinearSVM.train(x, y, seed=3)
    b = LinearSVM.train(x, y, seed=3)
    assert a.weights == b.weights
    assert a.biases == b.biases


# --- unit: rules -----------------------------------------------------------


def test_rule_layer_fires_abstains_and_conflicts() -> None:
    layer = RuleLayer(
        rules=(
            SeedRule("domain:timing", "timing"),
            SeedRule("concept:headway", "separation"),
        )
    )
    assert layer.apply({"domain:timing": 1.0}).label == "timing"
    assert layer.apply({"other": 1.0}).abstained
    conflict = layer.apply({"domain:timing": 1.0, "concept:headway": 1.0})
    assert conflict.conflict and conflict.abstained


# --- unit: guardrails ------------------------------------------------------


def test_score_gold_and_kappa() -> None:
    preds = {"a": "x", "b": "y", "c": "x"}
    gold = {"a": "x", "b": "x", "c": "x"}
    score = score_gold(preds, gold)
    assert abs(score.micro_precision - 2 / 3) < 1e-9
    assert cohen_kappa(["x", "x", "y"], ["x", "x", "y"]) == 1.0


def test_guardrail_flags_precision_drop() -> None:
    g = score_gold({"a": "x"}, {"a": "y"})  # precision 0
    report = evaluate_guardrails(1, g, previous_precision=0.5, label_drift=0.0)
    assert report.rollback is True
    assert report.precision_delta is not None and report.precision_delta < 0


# --- closed loop -----------------------------------------------------------


def test_loop_writes_records_and_logs_decisions() -> None:
    svc, r1, r2 = _run_two_loops()
    assert svc.store.decisions, "decision log must be populated"
    assert svc.store.records, "label DB must be populated"
    # Loop 1 should adjudicate heavily (untrained), loop 2 should auto-accept more.
    assert r1.n_adjudicate > 0
    assert r2.n_auto_accept >= 1


def test_loop_replayable_from_decision_log() -> None:
    svc, _r1, _r2 = _run_two_loops()
    replayed = LabelStore.replay(svc.store.decisions)
    assert replayed == svc.store.records


def test_gold_precision_non_decreasing_or_flagged() -> None:
    _svc, _r1, r2 = _run_two_loops()
    # The acceptance criterion: precision is non-decreasing across loops, and
    # if it ever drops the rollback flag is raised.
    delta = r2.guardrail.precision_delta
    assert delta is None or delta >= 0.0 or r2.guardrail.rollback
    # The loop actually learns something: final precision is positive.
    assert r2.guardrail.gold.micro_precision > 0.0


def test_loop_is_deterministic_end_to_end() -> None:
    svc_a, _a1, a2 = _run_two_loops(seed=7)
    svc_b, _b1, b2 = _run_two_loops(seed=7)
    assert svc_a.store.to_dict() == svc_b.store.to_dict()
    assert a2.lexicon_version == b2.lexicon_version
    assert a2.clf_version == b2.clf_version
    assert a2.guardrail.gold.micro_precision == b2.guardrail.gold.micro_precision


def test_store_json_roundtrip() -> None:
    svc, _r1, _r2 = _run_two_loops()
    restored = LabelStore.from_json(svc.store.to_json())
    assert restored.to_dict() == svc.store.to_dict()


def test_records_stamp_versions() -> None:
    svc, _r1, _r2 = _run_two_loops()
    for rec in svc.store.records:
        assert rec.lexicon_version
        assert rec.clf_version
        assert rec.corpus_version
        assert rec.source in ("rule", "clf", "human")


def test_vocabulary_must_be_sorted_unique() -> None:
    import pytest

    with pytest.raises(ValueError):
        ControlledVocabulary("C", "d", ("b", "a"))
