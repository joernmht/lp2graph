"""Structural metrics over formulations and derived graphs.

Every metric is a pure function. Two categories:

- **Formulation metrics** consume the canonical model directly.
  Cheaper, exact, no grounding needed.
- **Graph metrics** consume an internal :class:`~lp2graph.core.graph.Graph`
  (typically the schema or hybrid view). Used when the metric is
  inherently topological (e.g. graph diameter).

All metrics return a :class:`MetricResult` — a name, a value, and a
short human-readable explanation. Determinism is required: snapshot
tests verify that identical inputs produce identical outputs.
"""

from lp2graph.metrics.classification import (
    CONSTRAINT_TYPE_KEYWORDS,
    classify_constraints,
)
from lp2graph.metrics.flags import (
    has_aggregation_operator,
    has_big_m,
    has_integer_vars,
    has_modulo_offset,
    has_soft_slack,
    presence_flags,
)
from lp2graph.metrics.result import MetricResult
from lp2graph.metrics.structural import (
    constraint_variable_ratio,
    edge_density,
    graph_diameter,
    minimal_size,
    model_coherence,
    node_counts_by_class,
    structural_summary,
)

__all__ = [
    "CONSTRAINT_TYPE_KEYWORDS",
    "MetricResult",
    "classify_constraints",
    "constraint_variable_ratio",
    "edge_density",
    "graph_diameter",
    "has_aggregation_operator",
    "has_big_m",
    "has_integer_vars",
    "has_modulo_offset",
    "has_soft_slack",
    "minimal_size",
    "model_coherence",
    "node_counts_by_class",
    "presence_flags",
    "structural_summary",
]
