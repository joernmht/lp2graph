"""NetworkX export.

Converts an internal :class:`~optgraph.core.graph.Graph` to a
``networkx.MultiDiGraph``. Node attributes preserve ``cls``, ``subtype``,
``label``, ``shape``, and ``data``. Edge attributes preserve ``type``,
``role``, ``label``, ``data``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from optgraph.core.graph import Graph

if TYPE_CHECKING:
    import networkx as nx


def to_networkx(g: Graph) -> nx.MultiDiGraph:
    """Convert to a NetworkX MultiDiGraph."""
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "to_networkx requires networkx; install with 'pip install lp2graph[networkx]'"
        ) from exc

    nxg: Any = nx.MultiDiGraph()
    for n in g.nodes:
        nxg.add_node(
            n.id,
            cls=n.cls,
            subtype=n.subtype,
            label=n.label,
            shape=list(n.shape),
            data=dict(n.data),
        )
    for edge in g.edges:
        nxg.add_edge(
            edge.src,
            edge.dst,
            type=edge.type,
            role=edge.role,
            label=edge.label,
            data=dict(edge.data),
        )
    return nxg


__all__ = ["to_networkx"]
