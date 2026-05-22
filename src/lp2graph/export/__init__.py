"""Export adapters: NetworkX, PyG, DGL, LaTeX, Pyomo stubs.

Heavy framework imports happen lazily inside each adapter to keep
``lp2graph`` importable without optional dependencies.
"""

from lp2graph.export.dgl import to_dgl
from lp2graph.export.latex import to_latex
from lp2graph.export.networkx_adapter import to_networkx
from lp2graph.export.pyg import to_pyg
from lp2graph.export.pyomo_stub import to_pyomo_stub

__all__ = ["to_dgl", "to_latex", "to_networkx", "to_pyg", "to_pyomo_stub"]
