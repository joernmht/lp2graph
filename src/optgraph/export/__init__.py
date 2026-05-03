"""Export adapters: NetworkX, PyG, DGL, LaTeX, Pyomo stubs.

Heavy framework imports happen lazily inside each adapter to keep
``optgraph`` importable without optional dependencies.
"""

from optgraph.export.dgl import to_dgl
from optgraph.export.latex import to_latex
from optgraph.export.networkx_adapter import to_networkx
from optgraph.export.pyg import to_pyg
from optgraph.export.pyomo_stub import to_pyomo_stub

__all__ = ["to_dgl", "to_latex", "to_networkx", "to_pyg", "to_pyomo_stub"]
