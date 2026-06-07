"""Tests for M6 — intra-cluster schema-graph isomorphism report."""

from __future__ import annotations

from pathlib import Path

import pytest

from lp2graph import load

pytest.importorskip("networkx")

from lp2graph.mining.isomorphism import (
    are_isomorphic,
    cluster_isomorphism,
    clusters_from_labels,
    isomorphism_report,
)

ROOT = Path(__file__).resolve().parents[2]
FORMULATIONS = ROOT / "formulations"


def _all_formulations() -> list:
    return [load(p) for p in sorted(FORMULATIONS.rglob("*.json"))]


def _by_id(form_id: str):
    for p in sorted(FORMULATIONS.rglob("*.json")):
        f = load(p)
        if f.id == form_id:
            return f
    raise AssertionError(f"no formulation with id {form_id!r}")


def test_formulation_is_isomorphic_to_itself() -> None:
    forms = _all_formulations()
    for f in forms:
        assert are_isomorphic(f, f)


def test_renamed_copy_is_isomorphic() -> None:
    f = _all_formulations()[0]
    # A copy with a different id/name but identical structure must be
    # schema-graph isomorphic.
    renamed = f.model_copy(update={"id": f.id + "-copy", "name": "Renamed"})
    assert are_isomorphic(f, renamed)


def test_structurally_different_not_isomorphic() -> None:
    forms = _all_formulations()
    # Find two formulations with different node counts → cannot be isomorphic.
    from lp2graph.mining.isomorphism import schema_nx

    sizes = {f.id: schema_nx(f).number_of_nodes() for f in forms}
    ids = sorted(sizes)
    a = _by_id(ids[0])
    # pick one with a different size
    b = next((_by_id(i) for i in ids if sizes[i] != sizes[ids[0]]), None)
    if b is None:
        pytest.skip("no pair with differing schema-graph size in the catalog")
    assert not are_isomorphic(a, b)


def test_single_cluster_report_fields() -> None:
    f = _all_formulations()[0]
    renamed = f.model_copy(update={"id": f.id + "-copy", "name": "Renamed"})
    rep = cluster_isomorphism("c0", [f, renamed])
    assert rep.size == 2
    assert rep.n_pairs == 1
    assert rep.n_isomorphic_pairs == 1
    assert rep.pairwise_rate == 1.0
    assert rep.whole_cluster_rate == 1.0
    assert rep.largest_class_size == 2
    assert rep.representative == 0


def test_mixed_cluster_rate() -> None:
    forms = _all_formulations()
    from lp2graph.mining.isomorphism import schema_nx

    sizes = {f.id: schema_nx(f).number_of_nodes() for f in forms}
    base = forms[0]
    other = next((f for f in forms if sizes[f.id] != sizes[base.id]), None)
    if other is None:
        pytest.skip("need two differently-shaped formulations")
    copy = base.model_copy(update={"id": base.id + "-copy"})
    rep = cluster_isomorphism("mixed", [base, copy, other])
    # base & copy form one class of size 2; other is its own class.
    assert rep.largest_class_size == 2
    assert rep.size == 3
    assert rep.n_pairs == 3
    assert rep.n_isomorphic_pairs == 1
    assert abs(rep.pairwise_rate - 1 / 3) < 1e-9


def test_report_is_deterministic() -> None:
    forms = _all_formulations()
    labels = [i % 2 for i in range(len(forms))]
    names = {0: "even", 1: "odd"}
    clusters = clusters_from_labels(forms, labels, names)
    r1 = isomorphism_report(clusters)
    r2 = isomorphism_report(clusters)
    assert {k: v.equivalence_classes for k, v in r1.items()} == {
        k: v.equivalence_classes for k, v in r2.items()
    }
    assert {k: v.pairwise_rate for k, v in r1.items()} == {
        k: v.pairwise_rate for k, v in r2.items()
    }
