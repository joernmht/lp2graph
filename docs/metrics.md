# Metrics

Every metric is a pure function. Some take a `Formulation` directly
(presence flags); others take a derived `Graph` (structural metrics).
All return a `MetricResult(name, value, explanation, data)`.

## Presence flags

| Name | Source | Definition | Differentiating example |
|---|---|---|---|
| `has_big_m` | model | A parameter has `kind="big_m"` *or* a constraint has `kind="big_m"`. | `mip_2_1_big_m` is True; `mip_2_4_time_indexed` is False. |
| `has_integer_vars` | model | Any variable template has domain `integer` or `binary`. | True for every MIP/MILP; False for every LP. |
| `has_modulo_offset` | model | Any term binding declares `modulo`. | Triggers on PESP-style formulations with explicit modulo bindings. |
| `has_soft_slack` | model | Any variable has role `slack` *or* any term has role `slack`. | True for `lp_1_5_soft_regularity`. |
| `has_aggregation_operator` | model | Any term has `operator != "none"`. | True for `mip_2_4_time_indexed` (sum) and `objective_abs_deviation` (abs). |

Complexity: O(|terms|). All five computed in one pass via
`lp2graph.metrics.flags.presence_flags(f)`.

## Structural metrics

| Name | Source | Definition | Complexity |
|---|---|---|---|
| `node_counts_by_class` | graph | Count of nodes grouped by class (`variable`, `constraint`, …). | O(\|V\|) |
| `edge_density` | graph | `\|E\| / (\|V\| · (\|V\| − 1))` for the directed graph. | O(\|V\| + \|E\|) |
| `constraint_variable_ratio` | graph | Constraint-class node count divided by variable-class node count. | O(\|V\|) |
| `minimal_size` | graph | `\|constraints\| · \|variables\|` (a weak proxy for problem size). | O(\|V\|) |
| `model_coherence` | graph | 1 if the underlying undirected graph is connected, else 0. | O(\|V\| + \|E\|) |
| `graph_diameter` | graph | Longest shortest path in the largest connected component. Returns the path in `data["path"]`. | O(\|V\| · (\|V\| + \|E\|)) |

All six computed in one pass via
`lp2graph.metrics.structural.structural_summary(g)`.

## Constraint classification (heuristic)

`lp2graph.metrics.classify_constraints(f)` runs the source-repo's
keyword tables (preserved verbatim) over each constraint's `name` and
`description`, returning a per-constraint list of inferred type tags
plus a global histogram. Use this to audit catalog tags or to
cross-check author-supplied `kind` fields.

## Determinism

Metrics are deterministic. Two calls with the same input produce
identical output, byte-for-byte where applicable. Snapshot tests in
`tests/golden/` (planned for v0.2) will guard regressions; the
existing tests verify this property by calling each metric twice and
comparing.
