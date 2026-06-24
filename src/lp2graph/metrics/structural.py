"""Structural metrics over typed graphs.

Adapted from joernmht/raiLPminerExperimentation
(railpminer/analysis/metrics.py and railpminer/visualization/diameter.py),
MIT License. The algorithms are the same; the surface targets the new
internal :class:`~lp2graph.core.graph.Graph` rather than NetworkX
directly.
"""

from __future__ import annotations

from collections import defaultdict, deque

from lp2graph.core.graph import Graph
from lp2graph.core.model import Formulation
from lp2graph.metrics.result import MetricResult


def node_counts_by_class(g: Graph) -> MetricResult:
    """Count nodes by their high-level class.

    Returns a dict like ``{"variable": 4, "constraint": 6, ...}``.
    """
    counts: dict[str, int] = defaultdict(int)
    for n in g.nodes:
        counts[n.cls] += 1
    return MetricResult(
        name="node_counts_by_class",
        value=dict(counts),
        explanation="Count of nodes grouped by class.",
    )


def edge_density(g: Graph) -> MetricResult:
    """Edge density: |E| / max(1, |V| * (|V| - 1))."""
    n = len(g)
    e = len(g.edges)
    density = 0.0 if n <= 1 else e / (n * (n - 1))
    return MetricResult(
        name="edge_density",
        value=density,
        explanation="Directed-graph edge density.",
        data={"nodes": n, "edges": e},
    )


def constraint_variable_ratio(g: Graph) -> MetricResult:
    """Number of constraint nodes divided by number of variable nodes.

    Operates on the schema or hybrid view. For ground views, instance
    nodes are counted instead.
    """
    constraints = len([n for n in g.nodes if n.cls in ("constraint", "instance_constraint")])
    variables = len([n for n in g.nodes if n.cls in ("variable", "instance_variable")])
    if variables == 0:
        ratio = float("inf") if constraints > 0 else 0.0
    else:
        ratio = constraints / variables
    return MetricResult(
        name="constraint_variable_ratio",
        value=ratio,
        explanation="Constraint-to-variable count ratio.",
        data={"constraints": constraints, "variables": variables},
    )


def minimal_size(g: Graph) -> MetricResult:
    """The product |constraints| · |variables| (the dense incidence-matrix size).

    A weak proxy for problem size; useful for relative comparison across
    formulations.
    """
    constraints = len([n for n in g.nodes if n.cls in ("constraint", "instance_constraint")])
    variables = len([n for n in g.nodes if n.cls in ("variable", "instance_variable")])
    cv = max(constraints, 1) * max(variables, 1)
    return MetricResult(
        name="minimal_size",
        value=cv,
        explanation="Product of constraint count and variable count.",
        data={"constraints": constraints, "variables": variables},
    )


def model_coherence(g: Graph) -> MetricResult:
    """1 if the underlying undirected graph is connected, else 0.

    A coherent model has every variable reached by some path through
    constraints. Disconnected components usually signal a missing
    coupling.
    """
    if len(g) <= 1:
        return MetricResult(name="model_coherence", value=1, explanation="Trivially connected.")
    seen: set[str] = set()
    start = g.nodes[0].id
    queue = deque([start])
    seen.add(start)
    adj: dict[str, set[str]] = defaultdict(set)
    for e in g.edges:
        adj[e.src].add(e.dst)
        adj[e.dst].add(e.src)
    while queue:
        n = queue.popleft()
        for m in adj[n]:
            if m not in seen:
                seen.add(m)
                queue.append(m)
    coherent = 1 if len(seen) == len(g) else 0
    return MetricResult(
        name="model_coherence",
        value=coherent,
        explanation="1 if undirected graph is connected, else 0.",
        data={"reached": len(seen), "total": len(g)},
    )


def model_completeness(f: Formulation) -> MetricResult:
    """1 if the formulation is a recoverable model, else 0.

    A *complete* model declares an objective together with at least one
    variable and at least one constraint -- the minimal evidence that a
    whole model, rather than a fragment, was extracted. This is the
    companion well-formedness indicator to :func:`model_coherence`; unlike
    coherence (a graph property) it reads the canonical
    :class:`~lp2graph.core.model.Formulation` directly.
    """
    complete = (
        1 if f.objective is not None and len(f.variables) >= 1 and len(f.constraints) >= 1 else 0
    )
    return MetricResult(
        name="model_completeness",
        value=complete,
        explanation="1 if the model declares an objective, >=1 variable and >=1 constraint, else 0.",
        data={
            "has_objective": f.objective is not None,
            "n_variables": len(f.variables),
            "n_constraints": len(f.constraints),
        },
    )


def graph_diameter(g: Graph) -> MetricResult:
    """Diameter of the largest connected component (undirected, unweighted).

    Returns the diameter and one diameter-realizing path. If the graph
    has fewer than two nodes, returns 0.
    """
    if len(g) < 2:
        return MetricResult(name="graph_diameter", value=0, explanation="Too small.")
    adj: dict[str, set[str]] = defaultdict(set)
    for e in g.edges:
        adj[e.src].add(e.dst)
        adj[e.dst].add(e.src)

    # Find the largest connected component.
    seen_global: set[str] = set()
    components: list[set[str]] = []
    for n in g.nodes:
        if n.id in seen_global:
            continue
        comp: set[str] = set()
        queue = deque([n.id])
        seen_global.add(n.id)
        comp.add(n.id)
        while queue:
            x = queue.popleft()
            for y in adj[x]:
                if y not in seen_global:
                    seen_global.add(y)
                    comp.add(y)
                    queue.append(y)
        components.append(comp)
    largest = max(components, key=len)
    if len(largest) < 2:
        return MetricResult(name="graph_diameter", value=0, explanation="LCC has < 2 nodes.")

    # Two-pass BFS approximation gives the exact diameter for trees and
    # an exact answer for arbitrary graphs only when followed by full
    # BFS from every node. Here we do the full BFS for correctness; the
    # graphs we care about are small (template-scale).
    best = 0
    best_path: list[str] = []
    nodes = sorted(largest)  # deterministic
    for src in nodes:
        dist = {src: 0}
        prev: dict[str, str | None] = {src: None}
        queue = deque([src])
        while queue:
            x = queue.popleft()
            for y in adj[x]:
                if y not in dist:
                    dist[y] = dist[x] + 1
                    prev[y] = x
                    queue.append(y)
        target = max(dist, key=lambda k: (dist[k], k))
        if dist[target] > best:
            best = dist[target]
            # Reconstruct path.
            path: list[str] = []
            cur: str | None = target
            while cur is not None:
                path.append(cur)
                cur = prev[cur]
            best_path = list(reversed(path))
    return MetricResult(
        name="graph_diameter",
        value=best,
        explanation="Longest shortest path in the largest connected component.",
        data={"path": best_path},
    )


def structural_summary(g: Graph) -> dict[str, MetricResult]:
    """Convenience: compute every structural metric at once."""
    return {
        m.name: m
        for m in (
            node_counts_by_class(g),
            edge_density(g),
            constraint_variable_ratio(g),
            minimal_size(g),
            model_coherence(g),
            graph_diameter(g),
        )
    }


__all__ = [
    "constraint_variable_ratio",
    "edge_density",
    "graph_diameter",
    "minimal_size",
    "model_coherence",
    "model_completeness",
    "node_counts_by_class",
    "structural_summary",
]
