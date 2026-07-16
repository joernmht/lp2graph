"""View derivation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from lp2graph import load
from lp2graph.views import ground, hybrid, schema


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
    cinst = [
        n for n in g.nodes_by_class("instance_constraint") if n.data["template"] == "order_pair"
    ]
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


def _where_doc(parameter_shape: list[str]) -> dict:
    return {
        "schema_version": "0.1.0",
        "id": "where_demo",
        "name": "where demo",
        "family": "lp",
        "indices": [{"name": "T"}],
        "parameters": [{"name": "is_local", "shape": parameter_shape, "kind": "vector"}],
        "variables": [{"name": "x", "shape": ["T"], "domain": "non_negative"}],
        "constraints": [
            {
                "name": "c_local",
                "comparator": "le",
                "quantifiers": [
                    {
                        "index": "t",
                        "over": "T",
                        "where": {"parameter": "is_local", "equals": True},
                    }
                ],
                "lhs": [
                    {
                        "ref": "x",
                        "ref_kind": "variable",
                        "bindings": [{"index": "T", "expr": "t"}],
                        "role": "lhs",
                    }
                ],
                "rhs": [{"ref": "one", "ref_kind": "literal", "coefficient": 1, "role": "rhs"}],
            }
        ],
    }


def test_quantifier_where_filters_ground_view(tmp_path) -> None:
    import json

    p = tmp_path / "where.json"
    p.write_text(json.dumps(_where_doc(["T"])), encoding="utf-8")
    f = load(p)
    g = ground(f, {"T": 4}, parameter_values={"is_local": [True, False, True, False]})
    cinst = [n for n in g.nodes_by_class("instance_constraint") if n.data["template"] == "c_local"]
    assert len(cinst) == 2
    quant_t = sorted(n.data["quantifiers"]["t"] for n in cinst)
    assert quant_t == [0, 2]


def test_quantifier_where_requires_parameter_values(tmp_path) -> None:
    import json

    p = tmp_path / "where_missing.json"
    p.write_text(json.dumps(_where_doc(["T"])), encoding="utf-8")
    f = load(p)
    with pytest.raises(ValueError, match="requires parameter_values"):
        ground(f, {"T": 4})


def test_quantifier_where_appears_in_schema_view(tmp_path) -> None:
    import json

    p = tmp_path / "where_label.json"
    p.write_text(json.dumps(_where_doc(["T"])), encoding="utf-8")
    f = load(p)
    g = schema(f)
    c_node = next(n for n in g.nodes_by_class("constraint") if n.label == "c_local")
    where = c_node.data["quantifiers"][0]["where"]
    assert where == {"parameter": "is_local", "equals": True}


def test_validation_rejects_where_with_wrong_shape(tmp_path) -> None:
    import json

    bad = {
        "schema_version": "0.1.0",
        "id": "bad_where_shape",
        "name": "bad where shape",
        "family": "lp",
        "indices": [{"name": "T"}, {"name": "S"}],
        "parameters": [{"name": "p", "shape": ["S"], "kind": "vector"}],
        "variables": [{"name": "x", "shape": ["T"], "domain": "non_negative"}],
        "constraints": [
            {
                "name": "c1",
                "comparator": "le",
                "quantifiers": [
                    {
                        "index": "t",
                        "over": "T",
                        "where": {"parameter": "p", "equals": True},
                    }
                ],
                "lhs": [
                    {
                        "ref": "x",
                        "ref_kind": "variable",
                        "bindings": [{"index": "T", "expr": "t"}],
                        "role": "lhs",
                    }
                ],
                "rhs": [{"ref": "one", "ref_kind": "literal", "coefficient": 1, "role": "rhs"}],
            }
        ],
    }
    p = tmp_path / "bad_where.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    from lp2graph.core.validate import ValidationError

    with pytest.raises(ValidationError) as e:
        load(p)
    assert any("where-clause" in m and "shape" in m for m in e.value.errors)


def test_symbolic_coefficient_produces_uses_parameter_edge() -> None:
    f = load("formulations/constraints/mip_2_8_pesp.json")
    for view in (schema, hybrid):
        g = view(f)
        coef_edges = [(e.src, e.dst) for e in g.edges if e.type == "uses_parameter"]
        assert coef_edges == [
            ("constraint:pesp_lower", "param:T_period"),
            ("constraint:pesp_upper", "param:T_period"),
        ]


def test_pesp_schema_view_has_no_isolated_nodes() -> None:
    f = load("formulations/constraints/mip_2_8_pesp.json")
    g = schema(f)
    touched = {n for e in g.edges for n in (e.src, e.dst)}
    assert touched == {n.id for n in g.nodes}
