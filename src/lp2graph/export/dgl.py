"""DGL export (lazy import; stubbed for v0.1)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lp2graph.core.graph import Graph

if TYPE_CHECKING:
    pass


def to_dgl(g: Graph) -> Any:
    """Convert to a DGL heterograph.

    Raises:
        ImportError: if DGL is not installed.
    """
    try:
        import dgl
        import torch
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "to_dgl requires dgl and torch; install with 'pip install lp2graph[dgl]'"
        ) from exc

    nodes_by_class: dict[str, list[int]] = {}
    id_to_idx: dict[str, tuple[str, int]] = {}
    for i, n in enumerate(g.nodes):
        bucket = nodes_by_class.setdefault(n.cls, [])
        id_to_idx[n.id] = (n.cls, len(bucket))
        bucket.append(i)

    edge_buckets: dict[tuple[str, str, str], tuple[list[int], list[int]]] = {}
    for edge in g.edges:
        sc, sidx = id_to_idx[edge.src]
        dc, didx = id_to_idx[edge.dst]
        key = (sc, edge.type, dc)
        if key not in edge_buckets:
            edge_buckets[key] = ([], [])
        edge_buckets[key][0].append(sidx)
        edge_buckets[key][1].append(didx)

    data_dict: dict[tuple[str, str, str], tuple[Any, Any]] = {
        k: (torch.tensor(v[0]), torch.tensor(v[1])) for k, v in edge_buckets.items()
    }
    num_nodes_dict = {k: len(v) for k, v in nodes_by_class.items()}
    return dgl.heterograph(data_dict, num_nodes_dict=num_nodes_dict)


__all__ = ["to_dgl"]
