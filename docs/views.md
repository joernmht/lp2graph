# Views

Three derivations turn a formulation into a typed graph. Each is a
pure function: same input, same output, every time.

## Schema view

`optgraph.views.schema(f) -> Graph`

The topology of the formulation. Nodes:

- one per **index family**,
- one per **parameter**,
- one per **variable template**,
- one per **constraint template**,
- one **objective** (if present),
- one per **aggregation operator** (`sum_{t in T}`, `abs`, etc.),
  inserted between the container and its referenced variable.

Edges:

- `var_in_constraint` — constraint to variable per term.
- `var_in_objective` — objective to variable per term.
- `uses_index` — variable / parameter to its shape index family.
- `uses_parameter` — to be added in v0.2; currently parameters appear
  only as term references.
- `operator_input`, `operator_output` — connect operator nodes.

Offsets are *not* shown in the schema view. Use this view for
topological metrics (graph diameter, model coherence, edge density)
and for cross-formulation comparison: every formulation with the same
template skeleton produces the same schema graph.

## Hybrid view

`optgraph.views.hybrid(f) -> Graph`

Schema view enriched with per-binding offset, sign, and modulo labels.
Each constraint-to-variable edge carries an `offsets` data field:

```json
{ "T": { "expr": "t-1", "offset": -1, "modulo": null } }
```

Edge labels show the same information compactly: `[T=t-1]` or
`[T=t+k mod T]`. Use this view for visual inspection — it is the most
informative at template scale.

## Ground view

`optgraph.views.ground(f, cardinalities) -> Graph`

Materializes every variable instance and constraint instance for the
supplied cardinalities (one positive integer per declared index).
Applies degeneracy filters:

- **Out-of-range offsets.** A binding `t-1` for a non-cyclic index is
  dropped at `t = 0`; the constraint instance loses that term and is
  flagged `degenerate=True` for the renderer.
- **i != j (and friends).** Pair quantifiers with `ne_other`,
  `lt_other`, etc. exclude tuples that fail the restriction.
- **Ordered pairs.** `ordered_pair` keeps only `(i, j)` with `i < j`.
- **Cyclic wrap.** Bindings with `modulo` set, or against a cyclic
  index family, wrap modulo the cardinality.

Ground views are *expensive* at large cardinalities. Use sparingly and
at small sizes (typically 3 ≤ cardinality ≤ 8) for visual purposes;
for GNN training, ground at the cardinalities your downstream pipeline
needs and feed into PyG via `optgraph.export.to_pyg`.

## When to use which

| Question | View |
|---|---|
| Are these two formulations structurally the same? | schema |
| What does this constraint actually couple? | hybrid |
| Render this at a specific instance size for a paper figure. | ground |
| Train a GNN on this. | ground (export to PyG) |
| Compute a topological metric. | schema |
| Compute presence flags. | (no view; use the canonical model directly) |
