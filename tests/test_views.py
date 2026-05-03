"""View derivation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from optgraph import load
from optgraph.views import ground, hybrid, schema


def test_schema_view_basic_structure(formulation_files: list[Path]) -> None:
    for p in formulation_files:
        f = load(p)
        g = schema(f)
        # Every variable has a node.
        var_nodes = g.nodes_by_class("variable")
        assert {n.label for n in var_nodes} == {v.name for v in f.variables}
        # Every index has a node.
        idx_nodes = g.nodes_by_class("index")
        assert {n.label for n in idx_nodes} == {i.name for i in f.indices}
        # Every constraint has a node.
        c_nodes = g.nodes_by_class("constraint")
        assert {n.label for n in c_nodes} == {c.name for c in f.constraints}
        # If objective is present, exactly one objective node.
        if f.objective is not None:
            assert len(g.nodes_by_class("objective")) == 1


def test_hybrid_view_offset_labels_present() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    g = hybrid(f)
    edges = [e for e in g.edges if e.src == "constraint:headway"]
    # The headway constraint has two terms; the second has offset -1.
    has_offset_label = any("i-1" in str(e.data.get("offsets", {})) for e in edges)
    assert has_offset_label


def test_schema_view_omits_offsets() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    g = schema(f)
    for e in g.edges:
        assert "offsets" not in e.data


def test_schema_view_is_deterministic() -> None:
    f = load("formulations/constraints/mip_2_4_time_indexed.json")
    g1 = schema(f)
    g2 = schema(f)
    assert [n.id for n in g1.nodes] == [n.id for n in g2.nodes]
    assert [(e.src, e.dst, e.type, e.role) for e in g1.edges] == [
        (e.src, e.dst, e.type, e.role) for e in g2.edges
    ]


def test_ground_view_requires_all_cardinalities() -> None:
    f = load("formulations/constraints/mip_2_4_time_indexed.json")
    with pytest.raises(ValueError):
        ground(f, {"I": 3})  # missing T


def test_ground_view_materializes_instances() -> None:
    f = load("formulations/constraints/mip_2_4_time_indexed.json")
    g = ground(f, {"I": 2, "T": 3})
    var_inst = g.nodes_by_class("instance_variable")
    # 2 trains x 3 slots = 6 binary x instances.
    assert len(var_inst) == 6


def test_ground_view_applies_ne_other_restriction() -> None:
    f = load("formulations/constraints/mip_2_1_big_m.json")
    g = ground(f, {"I": 3})
    # order_a quantifies (i, j) with j != i. For |I|=3, that is 6 instances.
    cinst = [n for n in g.nodes_by_class("instance_constraint") if n.data["template"] == "order_a"]
    assert len(cinst) == 6


def test_ground_view_applies_ordered_pair_restriction() -> None:
    f = load("formulations/constraints/mip_2_1_big_m.json")
    g = ground(f, {"I": 4})
    # order_pair quantifies (i, j) with i < j. For |I|=4, that is 6 instances.
    cinst = [n for n in g.nodes_by_class("instance_constraint") if n.data["template"] == "order_pair"]
    assert len(cinst) == 6


def test_ground_view_drops_out_of_range_offsets_for_non_cyclic() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    g = ground(f, {"I": 3})
    # headway has bindings t and t-1. At i=0, t-1 is out of range, so the
    # instance constraint is flagged degenerate but still emitted.
    headway_insts = [
        n for n in g.nodes_by_class("instance_constraint") if n.data["template"] == "headway"
    ]
    assert any(n.data.get("degenerate") for n in headway_insts)
