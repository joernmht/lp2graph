# Extraction Report

> **Status:** complete. Bootstrap inspection performed 2026-05-03.
> Source: [`joernmht/raiLPminerExperimentation`][src] @ `main` (MIT license).
>
> **License compatibility:** source MIT → new repo Apache 2.0. Permissive
> attribution is sufficient. No GPL or unclear-license code is in scope.

[src]: https://github.com/joernmht/raiLPminerExperimentation

## Method

The source repository is a research codebase whose primary product is a
Jupyter notebook (`analysis.ipynb`, 97% of the line count) plus a Python
package (`railpminer/`, 3% of the line count). The graph-related machinery
lives entirely in `railpminer/analysis/` and `railpminer/visualization/`,
plus the structured-output schema in `railpminer/models/schema.py`.

A first-pass extraction was performed prior to this bootstrap: the
verbatim source files were copied into a flat `lp2graph/` package. That
extraction is preserved at `legacy/extracted_flat/` for traceability and
will be removed in a follow-up commit once the new canonical model is
fully established and the legacy code has no more diagnostic value.

## Files inspected

| Source path | Relevance | One-line summary |
|---|---|---|
| `railpminer/__init__.py` | low | Package marker. |
| `railpminer/config.py` | none | Experiment runtime configuration; not graph-related. |
| `railpminer/models/__init__.py` | low | Package marker. |
| `railpminer/models/schema.py` | **high** | Pydantic + dataclass models for `Variable`, `ObjectiveFunction`, `Constraint`. Flat representation; no templates or indices. Source for the v0 data model. |
| `railpminer/models/agents.py` | none | LLM agent glue for formulation generation. Out of scope. |
| `railpminer/experiments/*` | none | Experiment grid execution. Out of scope. |
| `railpminer/utils/*` | none | I/O helpers. Out of scope. |
| `railpminer/analysis/__init__.py` | low | Package marker (re-exports). |
| `railpminer/analysis/graph_parser.py` | **high** | `safe_eval_model`, `parse_lp_model`, `create_graph_columns`. Parses LLM-emitted Python strings into a flat graph. Source for v0 parser. |
| `railpminer/analysis/metrics.py` | **high** | `calculate_complexity_metrics`, `add_complexity_metrics`, `process_lp_dataframe`, `analyze_lp_models`. Computes minimal-size, graph-diameter, constraint/variable ratio, model-coherence, model-completeness on a NetworkX graph. |
| `railpminer/analysis/constraints.py` | **high** | `classify_constraint_types`, `add_constraint_classification`. Regex-based constraint typing (ordering, routing, timing, cancellation, headway, capacity, flow_balance, big_m, passenger_connection, rolling_stock_connection). |
| `railpminer/analysis/milp_detection.py` | medium | `detect_milp_artifacts`. Regex-based detector for `≤`, `≥`, `Σ`, `∀`, "subject to". Useful as a metric in the new repo. |
| `railpminer/analysis/regression.py` | none | OLS regression for the paper. Out of scope. |
| `railpminer/analysis/selection.py` | none | Diversity selection over the experiment dataset. Out of scope. |
| `railpminer/visualization/__init__.py` | low | Package marker. |
| `railpminer/visualization/circular.py` | medium | `visualize_circular_graph`. Matplotlib circular layout. |
| `railpminer/visualization/tree.py` | medium | `visualize_tree_graph`. Matplotlib hierarchical layout (objective at top, variables middle, constraints bottom). |
| `railpminer/visualization/diameter.py` | medium | `find_graph_diameter_and_path`, highlighting code. Useful as a metric and as a render annotation. |
| `railpminer/visualization/graphviz_utils.py` | low | `setup_graphviz` helper. Replaceable. |
| `railpminer/visualization/matrix.py` | low | Constraint–variable incidence matrix plot. Not migrated; can be a future export. |
| `railpminer/visualization/plotly_viz.py` | low | Plotly variants of the matplotlib plots. Not migrated. |
| `railpminer/visualization/runtime.py`, `single_paper.py`, `summary.py`, `scatter.py` | none | Paper-figure helpers. Out of scope. |

## Disposition

### Extracted and refactored

These provide useful functionality but the new repo's data model differs
substantially. The behavior is preserved; the surface is rebuilt.

- `analysis/metrics.py` → `src/lp2graph/metrics/structural.py`
  (graph diameter, model coherence, constraint/variable ratio, minimal
  size). Operates on the new internal `Graph` type rather than NetworkX
  directly. Determinism is now a tested property.
- `analysis/constraints.py` → `src/lp2graph/metrics/classification.py`
  (regex-based constraint typing). The keyword tables are preserved
  verbatim; the integration is rewritten to consume the canonical model.
- `analysis/milp_detection.py` → `src/lp2graph/metrics/operators.py`
  (operator presence detection, repurposed as structural metrics:
  `has_aggregation_operator`, `has_universal_quantifier`, etc.).
- `visualization/circular.py`, `tree.py` → `src/lp2graph/render/svg.py`
  (SVG-first rendering with the design-context palette and typography).
  The matplotlib originals are not preserved; SVG is the new default
  because it composes with the static viewer.
- `visualization/diameter.py` → `src/lp2graph/metrics/structural.py`
  (`graph_diameter` and `diameter_path` are returned together; rendering
  consumes them via the metric API).

### Reimplemented from scratch

These exist in spirit but the source's flat representation is
incompatible with the canonical model.

- The data model itself (`models/schema.py` →
  `src/lp2graph/core/model.py`). The source has flat `Variable`,
  `ObjectiveFunction`, `Constraint` with a `VariablesIncluded: List[int]`
  edge list. The new model has index families, parameters, variable
  templates, constraint templates with quantifiers, and term-level
  refs/bindings/role/sign. This is the central design change of the
  bootstrap and motivates the new repo's existence.
- Parser (`analysis/graph_parser.py` → no equivalent). The source uses
  `exec` on LLM-emitted Python strings; the new repo loads JSON files
  validated against `schema/canonical.schema.json`. This is a deliberate
  break: the `exec`-based loader is unsuitable for production.
- Visualization. The source uses matplotlib with circular and tree
  layouts; the new repo renders to SVG with a deliberate visual identity.
  The interactive viewer is a static HTML site, not Plotly.

### Dropped

- `models/agents.py` (LLM agents). Out of scope; belongs to upstream.
- `experiments/*` (experiment runners). Out of scope.
- `analysis/regression.py`, `analysis/selection.py` (paper analysis).
  Out of scope.
- `visualization/runtime.py`, `single_paper.py`, `summary.py`,
  `scatter.py`, `matrix.py`, `plotly_viz.py` (paper-figure helpers).
  Out of scope; could return as optional renderers in a future minor.
- `analysis.ipynb`, `experiment_results_metrics_corrected_selected.csv`.
  Research artifacts; out of scope.

## Dependency map

```
core/model.py
  └─ (no deps on other lp2graph modules)

core/loader.py
  └─ core/model.py
  └─ core/validate.py

core/validate.py
  └─ core/model.py
  └─ schema/canonical.schema.json

views/{schema,hybrid,ground}.py
  └─ core/model.py
  └─ core/graph.py        # internal typed graph

metrics/{structural,classification,operators}.py
  └─ core/model.py
  └─ core/graph.py

render/svg.py
  └─ core/graph.py

export/{pyg,dgl,networkx,latex,pyomo_stub}.py
  └─ core/model.py
  └─ core/graph.py
  └─ (export-specific deps as optional extras)
```

The core has no internal cycles. View derivations, metrics, render, and
export all depend on the core but not on each other.

## Load-bearing assumptions in the source code

The source code makes assumptions that were implicit in its research
context. Every one of these must be made explicit in the new design.

1. **Variables are identified by integer numbers, globally unique within
   a model.** The source's `Variable.Number` is the join key for
   `VariablesIncluded` lists. The new model uses string template names
   plus index bindings; integer IDs are an export concern.
2. **No index families.** The source treats `x_i` and `x_j` as separate
   variables identified by their LLM-generated names. The new model
   treats them as bindings of a template `x[I]`.
3. **No quantifier semantics.** A constraint that "applies for all `i`"
   is represented as a flat constraint string in the source. The new
   model has explicit quantifiers with restrictions (`i ≠ j`, `t < T`,
   etc.).
4. **Edges are undirected and untyped.** A `connection` is `[eq_num,
   var_num]`. The new model has typed, role-bearing edges.
5. **Coefficients and signs are embedded in equation strings, not
   structured.** The source carries `equation: str` and never parses it.
   The new model decomposes terms.
6. **Objective is a single function.** The source has one
   `ObjectiveFunction` per model. The new model allows multiple objective
   terms (for multi-objective formulations and for soft-constraint
   penalties), with a top-level combination rule.
7. **No notion of degeneracy filters in grounding.** The source never
   grounds; ground-view degeneracy filtering is new.
8. **Metrics operate on materialized NetworkX graphs.** The source builds
   a NetworkX graph inside every metric function. The new design
   computes metrics on the canonical model where possible (cheaper,
   exact) and on the internal `Graph` only where necessary
   (e.g., diameter).

## Attribution

Every file extracted or refactored from the source repo includes a
header comment crediting the origin, e.g.:

```python
# Adapted from joernmht/raiLPminerExperimentation
# (railpminer/analysis/metrics.py), MIT License.
```

The `legacy/extracted_flat/` directory preserves the verbatim first-pass
extraction with the same attribution.
