"""Example 4: export a ground view to a PyG HeteroData object.

Requires the ``pyg`` extra: ``pip install lp2graph[pyg]``.
"""

from __future__ import annotations

import sys

from lp2graph import load
from lp2graph.views import ground


def main() -> None:
    try:
        from lp2graph.export.pyg import to_pyg
    except ImportError as exc:
        print(f"PyG export unavailable: {exc}")
        sys.exit(1)

    f = load("formulations/constraints/mip_2_4_time_indexed.json")
    g = ground(f, {"I": 4, "T": 6})
    data = to_pyg(g)

    print("HeteroData:")
    print(f"  node types: {list(data.node_types)}")
    print(f"  edge types: {list(data.edge_types)}")
    for nt in data.node_types:
        x = data[nt].x
        print(f"  {nt:25s} x.shape = {tuple(x.shape)}")
    for et in data.edge_types:
        ei = data[et].edge_index
        print(f"  {str(et):60s} edge_index.shape = {tuple(ei.shape)}")


if __name__ == "__main__":
    main()
