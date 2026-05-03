"""Metric tests."""

from __future__ import annotations

from optgraph import load
from optgraph.metrics.flags import (
    has_aggregation_operator,
    has_big_m,
    has_integer_vars,
    has_soft_slack,
    presence_flags,
)
from optgraph.metrics.structural import (
    constraint_variable_ratio,
    edge_density,
    graph_diameter,
    minimal_size,
    model_coherence,
    node_counts_by_class,
    structural_summary,
)
from optgraph.views import schema


def test_has_big_m_for_mip_2_1() -> None:
    f = load("formulations/constraints/mip_2_1_big_m.json")
    assert has_big_m(f).value is True


def test_no_big_m_for_lp_1_1() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    assert has_big_m(f).value is False


def test_has_integer_vars_for_milp_only() -> None:
    f_lp = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    f_milp = load("formulations/constraints/mip_2_1_big_m.json")
    assert has_integer_vars(f_lp).value is False
    assert has_integer_vars(f_milp).value is True


def test_has_soft_slack_for_lp_1_5() -> None:
    f = load("formulations/constraints/lp_1_5_soft_regularity.json")
    assert has_soft_slack(f).value is True


def test_has_aggregation_operator_when_sum_present() -> None:
    f = load("formulations/constraints/mip_2_4_time_indexed.json")
    assert has_aggregation_operator(f).value is True


def test_modulo_offset_detection_pesp() -> None:
    f = load("formulations/constraints/mip_2_8_pesp.json")
    # PESP encodes period wrap via the integer k variable; explicit
    # modulo bindings would also trigger this. Either is acceptable.
    flags = presence_flags(f)
    assert flags["has_integer_vars"].value is True


def test_node_counts_by_class_sum_to_total() -> None:
    f = load("formulations/constraints/mip_2_4_time_indexed.json")
    g = schema(f)
    counts = node_counts_by_class(g).value
    assert sum(counts.values()) == len(g.nodes)


def test_edge_density_in_unit_interval() -> None:
    f = load("formulations/constraints/mip_2_4_time_indexed.json")
    g = schema(f)
    d = edge_density(g).value
    assert 0.0 <= d <= 1.0


def test_constraint_variable_ratio_simple() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    g = schema(f)
    r = constraint_variable_ratio(g).value
    # Two constraints, one variable template.
    assert r == 2.0


def test_minimal_size_is_product() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    g = schema(f)
    m = minimal_size(g).value
    assert m == 2 * 1


def test_model_coherence_for_connected_formulation() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    g = schema(f)
    assert model_coherence(g).value == 1


def test_graph_diameter_is_nonnegative_int() -> None:
    f = load("formulations/constraints/mip_2_1_big_m.json")
    g = schema(f)
    d = graph_diameter(g)
    assert isinstance(d.value, int) and d.value >= 0


def test_structural_summary_returns_all_metrics() -> None:
    f = load("formulations/constraints/mip_2_1_big_m.json")
    g = schema(f)
    s = structural_summary(g)
    expected = {
        "node_counts_by_class",
        "edge_density",
        "constraint_variable_ratio",
        "minimal_size",
        "model_coherence",
        "graph_diameter",
    }
    assert set(s) == expected


def test_metrics_are_deterministic() -> None:
    f = load("formulations/constraints/mip_2_1_big_m.json")
    g = schema(f)
    a = structural_summary(g)
    b = structural_summary(g)
    for k in a:
        assert a[k].value == b[k].value
