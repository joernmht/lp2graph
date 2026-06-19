"""PyG export.

Converts an internal :class:`~lp2graph.core.graph.Graph` to a
``torch_geometric.data.HeteroData`` instance. Node classes become node
types; edge types become PyG edge types ``(src_cls, edge_type, dst_cls)``.

Node features are minimal in v0.1: a single one-hot of the node's
subtype. Callers who want richer features should consume the typed
graph and build their own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lp2graph.core.graph import Graph

if TYPE_CHECKING:
    from torch_geometric.data import HeteroData


def to_pyg(g: Graph) -> HeteroData:
    """Convert to a PyG HeteroData object.

    Raises:
        ImportError: if torch and torch_geometric are not installed.
    """
    try:
        import torch
        from torch_geometric.data import HeteroData
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "to_pyg requires torch and torch_geometric; install with 'pip install lp2graph[pyg]'"
        ) from exc

    data: Any = HeteroData()

    # Group nodes by class; assign per-class indices.
    nodes_by_class: dict[str, list[int]] = {}
    id_to_idx: dict[str, tuple[str, int]] = {}
    subtype_vocab: dict[str, list[str]] = {}

    for i, n in enumerate(g.nodes):
        bucket = nodes_by_class.setdefault(n.cls, [])
        idx = len(bucket)
        bucket.append(i)
        id_to_idx[n.id] = (n.cls, idx)
        subtype_vocab.setdefault(n.cls, [])
        if n.subtype and n.subtype not in subtype_vocab[n.cls]:
            subtype_vocab[n.cls].append(n.subtype)

    for cls, indices in nodes_by_class.items():
        n_subtypes = max(1, len(subtype_vocab[cls]))
        x = torch.zeros((len(indices), n_subtypes), dtype=torch.float32)
        for local_i, global_i in enumerate(indices):
            n = g.nodes[global_i]
            if n.subtype:
                col = subtype_vocab[cls].index(n.subtype)
                x[local_i, col] = 1.0
        data[cls].x = x

    # Edges: bucket by (src_cls, edge_type, dst_cls).
    edge_buckets: dict[tuple[str, str, str], tuple[list[int], list[int]]] = {}
    for edge in g.edges:
        sc, sidx = id_to_idx[edge.src]
        dc, didx = id_to_idx[edge.dst]
        key = (sc, edge.type, dc)
        if key not in edge_buckets:
            edge_buckets[key] = ([], [])
        edge_buckets[key][0].append(sidx)
        edge_buckets[key][1].append(didx)
    for (sc, etype, dc), (src, dst) in edge_buckets.items():
        edge_index = torch.tensor([src, dst], dtype=torch.long)
        data[(sc, etype, dc)].edge_index = edge_index

    return data


__all__ = ["to_pyg"]
