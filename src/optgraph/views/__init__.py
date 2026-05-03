"""View derivations: schema, hybrid, and ground.

Each view is a pure function ``Formulation -> Graph``. The schema and
hybrid views require no extra arguments. The ground view additionally
requires ``cardinalities``: a mapping from index family name to a
positive integer.

Determinism: every derivation iterates over the canonical model in
declaration order. Two calls with identical inputs produce identical
graphs (compared as ordered node and edge sequences).
"""

from optgraph.views.ground import ground
from optgraph.views.hybrid import hybrid
from optgraph.views.schema import schema

__all__ = ["ground", "hybrid", "schema"]
