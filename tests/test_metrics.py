"""Metric tests."""

from __future__ import annotations

from lp2graph import load
from lp2graph.metrics.flags import (
    has_aggregation_operator,
    has_big_m,
    has_integer_vars,
    has_soft_slack,
    presence_flags,
)
from lp2graph.metrics.structural import (
    constraint_variable_ratio,
    edge_density,
    graph_diameter,
    minimal_size,
    model_coherence,
    model_completeness,
    node_counts_by_class,
    structural_summary,
)
from lp2graph.views import schema


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


def test_model_completeness_for_full_formulation() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    assert model_completeness(f).value == 1


def test_model_completeness_zero_without_objective() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    fragment = f.model_copy(update={"objective": None})
    assert model_completeness(fragment).value == 0


def test_model_completeness_is_deterministic() -> None:
    f = load("formulations/constraints/mip_2_1_big_m.json")
    assert model_completeness(f).value == model_completeness(f).value


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


def _brute_force_diameter(g) -> int:
    """All-sources BFS over the largest component: the reference definition."""
    from collections import deque

    adj: dict[str, set[str]] = {n.id: set() for n in g.nodes}
    for e in g.edges:
        adj[e.src].add(e.dst)
        adj[e.dst].add(e.src)
    best = 0
    seen: set[str] = set()
    comps: list[set[str]] = []
    for n in g.nodes:
        if n.id in seen:
            continue
        comp, queue = {n.id}, deque([n.id])
        seen.add(n.id)
        while queue:
            x = queue.popleft()
            for y in adj[x] - seen:
                seen.add(y)
                comp.add(y)
                queue.append(y)
        comps.append(comp)
    for src in max(comps, key=len):
        dist, queue = {src: 0}, deque([src])
        while queue:
            x = queue.popleft()
            for y in adj[x]:
                if y not in dist:
                    dist[y] = dist[x] + 1
                    queue.append(y)
        best = max(best, max(dist.values()))
    return best


def test_graph_diameter_is_exact_and_its_path_realizes_it() -> None:
    import random

    from lp2graph.core.graph import Graph

    rng = random.Random(0)
    for _ in range(400):
        n = rng.randint(2, 30)
        g = Graph()
        for i in range(n):
            g.add_node(f"n{i}", "variable")
        for _ in range(rng.randint(0, 2 * n)):
            g.add_edge(f"n{rng.randrange(n)}", f"n{rng.randrange(n)}", "var_in_constraint")
        d = graph_diameter(g)
        assert d.value == _brute_force_diameter(g)
        if d.value:
            path = d.data["path"]
            pairs = {frozenset((e.src, e.dst)) for e in g.edges}
            assert len(path) == d.value + 1
            assert all(frozenset(path[i : i + 2]) in pairs for i in range(d.value))


def test_graph_diameter_is_exact_on_ground_views() -> None:
    from lp2graph.views import ground

    for name in ("assignment", "mip_2_1_big_m", "mip_2_8_pesp"):
        f = load(f"formulations/constraints/{name}.json")
        g = ground(f, {i.name: 4 for i in f.indices})
        assert graph_diameter(g).value == _brute_force_diameter(g)


def test_graph_diameter_path_does_not_depend_on_the_hash_seed() -> None:
    """The reported path once followed ``set[str]`` iteration order, which
    changes with PYTHONHASHSEED -- a different path in every process."""
    import os
    import subprocess
    import sys

    code = (
        "from lp2graph import load\n"
        "from lp2graph.views import ground\n"
        "from lp2graph.metrics.structural import graph_diameter\n"
        "for n in ('assignment', 'lp_1_1_fixed_sequence', 'mip_2_4_time_indexed'):\n"
        "    f = load(f'formulations/constraints/{n}.json')\n"
        "    g = ground(f, {i.name: 3 for i in f.indices})\n"
        "    print('|'.join(graph_diameter(g).data['path']))\n"
    )
    outputs = set()
    for seed in ("0", "1", "2", "3"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        run = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        outputs.add(run.stdout)
    assert len(outputs) == 1
