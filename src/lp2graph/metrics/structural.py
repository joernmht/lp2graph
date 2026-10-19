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
    reached = len(_bfs(_undirected_adjacency(g), g.nodes[0].id)[0])
    coherent = 1 if reached == len(g) else 0
    return MetricResult(
        name="model_coherence",
        value=coherent,
        explanation="1 if undirected graph is connected, else 0.",
        data={"reached": reached, "total": len(g)},
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

    The diameter is exact. It is found by eccentricity bounding (Takes &
    Kosters, "Determining the diameter of small world networks", CIKM
    2011) rather than a BFS from every node: each BFS tightens lower and
    upper eccentricity bounds on all nodes, and the search stops once the
    bounds pin the diameter. On ground-view graphs this needs a handful of
    BFS runs where the all-sources search needed one per node -- the
    difference between milliseconds and seconds at a few thousand nodes.
    """
    if len(g) < 2:
        return MetricResult(name="graph_diameter", value=0, explanation="Too small.")
    adj = _undirected_adjacency(g)

    # Largest connected component; ties go to the one met first in node order.
    seen: set[str] = set()
    largest: list[str] = []
    for n in g.nodes:
        if n.id not in seen:
            comp = list(_bfs(adj, n.id)[0])
            seen.update(comp)
            if len(comp) > len(largest):
                largest = comp
    if len(largest) < 2:
        return MetricResult(name="graph_diameter", value=0, explanation="LCC has < 2 nodes.")

    best, best_path = _exact_diameter(adj, sorted(largest))
    return MetricResult(
        name="graph_diameter",
        value=best,
        explanation="Longest shortest path in the largest connected component.",
        data={"path": best_path},
    )


def _undirected_adjacency(g: Graph) -> dict[str, list[str]]:
    """Undirected neighbour lists in edge-insertion order, duplicates removed.

    Lists, not sets: BFS visits neighbours in this order, so it decides
    which shortest path a search reports. ``set[str]`` iteration follows
    the per-process string hash seed, which made the reported diameter
    path differ between runs.
    """
    nbrs: dict[str, dict[str, None]] = {n.id: {} for n in g.nodes}
    for e in g.edges:
        nbrs[e.src][e.dst] = None
        nbrs[e.dst][e.src] = None
    return {k: list(v) for k, v in nbrs.items()}


def _bfs(adj: dict[str, list[str]], src: str) -> tuple[dict[str, int], dict[str, str | None]]:
    """Hop distances and BFS-tree parents from ``src`` over its component."""
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
    return dist, prev


def _exact_diameter(adj: dict[str, list[str]], nodes: list[str]) -> tuple[int, list[str]]:
    """Exact diameter of one connected component and a path realizing it.

    ``nodes`` is the component, sorted, so every tie below breaks on node
    id and the result is deterministic. Bounds kept per node ``w``:
    ``lo[w] <= ecc(w) <= hi[w]``. A BFS from ``v`` with ``ecc(v) = e``
    gives, by the triangle inequality, ``max(d, e - d) <= ecc(w) <= e + d``
    for ``d = dist(v, w)``. The diameter is ``max ecc``, so it lies
    between ``max lo`` and ``max hi``; the loop ends when those meet.
    """
    lo = dict.fromkeys(nodes, 0)
    hi = dict.fromkeys(nodes, len(nodes))
    open_ = list(nodes)  # eccentricity not yet known exactly
    searched: dict[str, tuple[int, dict[str, int], dict[str, str | None]]] = {}
    pick_high = True
    while open_ and max(lo.values()) < max(hi.values()):
        # Alternate: the node that could have the largest eccentricity
        # (raises the lower bound), then the one that could have the smallest
        # (a central node: lowers every upper bound).
        if pick_high:
            v = min(open_, key=lambda w: (-hi[w], w))
        else:
            v = min(open_, key=lambda w: (lo[w], w))
        pick_high = not pick_high
        dist, prev = _bfs(adj, v)
        e = max(dist.values())
        searched[v] = (e, dist, prev)
        for w in open_:
            d = dist[w]
            lo[w] = max(lo[w], d, e - d)
            hi[w] = min(hi[w], e + d)
        open_ = [w for w in open_ if lo[w] < hi[w]]
    best = max(lo.values())

    # A path: from the first searched node that realizes the diameter, or,
    # if the bounds alone proved it, from the first node whose lower bound
    # reaches it (its eccentricity is then exactly ``best``).
    src = next((v for v, (e, _, _) in searched.items() if e == best), None)
    if src is None:
        src = next(w for w in nodes if lo[w] == best)
        dist, prev = _bfs(adj, src)
    else:
        _, dist, prev = searched[src]
    target = max(dist, key=lambda k: (dist[k], k))
    path: list[str] = []
    cur: str | None = target
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    return best, list(reversed(path))


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
