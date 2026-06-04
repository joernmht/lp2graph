# Two-Axis Faceted Taxonomy for MILP Elements

Status: **gold seed**, generated deterministically by [`categorize.py`](./categorize.py)
over the 17-repo / 28-model corpus on 2026-05-31. Intended for human review and
correction — where rules are uncertain, the label is `unclassified` (not guessed),
so coverage is measurable.

Confirmed design decisions (user, 2026-05-31):
1. **Two-axis faceted** classification (not flat single-label).
2. **Rules + variable-informed**, real corpus as gold; ML/LLM deferred until rules
   demonstrably plateau, and if used, trained on the *real* labeled corpus.
3. Built over the **existing structured corpus** first.

## Why faceted (empirical justification)

Keyword classification of the 224 constraints is heavily **multi-label**: a
headway constraint is typically *also* a big-M linearization; an assignment
constraint is *also* a bounds statement. A single flat label forces a lossy
choice. So every element gets two independent facets:

- **Structural facet** — derived deterministically from the formulation itself
  (comparator, aggregation operator, big-M presence, modulo). No learning, no
  ambiguity. This is the axis a parser can compute directly from the
  `lp2graph` graph.
- **Domain facet** — the semantic function (headway, capacity, …). Ambiguous;
  resolved by priority-ordered rules, **informed by the domain-roles of the
  variables the element links** (variable-first principle).

## Variables

| Facet | Values | How derived |
|---|---|---|
| `algebraic_type` | `binary` · `integer` · `continuous` | Deterministic from the variable's declared type. |
| `domain_role` | `selection_assignment` · `ordering_precedence` · `routing_path_column` · `timing` · `flow_quantity` · `auxiliary_linearization` · `unclassified` | Priority-ordered rules over name + meaning. |

Variables are categorized **first** because constraints inherit signal from them.

Corpus result: routing/path 49, timing 26, auxiliary 21, ordering 13,
selection 6, flow 4, unclassified 4 (**96.7%** classified).

## Constraints

**Structural facet** (deterministic):
- `relation` ∈ `equality` · `inequality` · `unknown`
- `flags` ⊆ `has_big_m` · `aggregation_sum` · `aggregation_max` · `aggregation_min` · `periodic_modulo` · `indicator` · `definitional`

Corpus: 134 inequality / 84 equality; flags — sum 109, big-M 39, definitional 23,
max 14, min 10, modulo 8, indicator 7.

**Domain facet** (`domain_primary` by priority + full `domain_secondary` list),
priority order:
`periodic_modulo_pesp` → `subtour_connectivity` → `headway_separation` →
`flow_conservation` → `capacity_resource` → `precedence_ordering` →
`timing_window` → `assignment_covering` → `coupling_linking_definition` →
`variable_bound_fix` → `objective_defining`.

When name/text rules are inconclusive, the **variable-informed fallback** maps
the roles of referenced variables to a domain hint (e.g. ordering vars ⇒
`precedence_ordering`, flow vars ⇒ `flow_conservation`). Each constraint also
records `linked_variable_roles` for transparency.

Corpus result (**100%** primary-classified): assignment_covering 66,
timing_window 28, variable_bound_fix 25, headway_separation 23,
flow_conservation 17, capacity_resource 16, precedence_ordering 15,
coupling_linking_definition 13, subtour_connectivity 13, periodic_modulo_pesp 8.

## Parameters

| Facet | Values |
|---|---|
| `structural_kind` | `lp2graph` kind: `scalar` · `vector` · `matrix` · `big_m` · `tolerance` (falls back to `scalar_or_indexed`). |
| `domain_class` | `cost_weight` · `time_duration` · `capacity` · `demand` · `network_structure` · `penalty_bigM` · `count_limit` · `unclassified` |

Corpus: time_duration 66, cost_weight 57, penalty_bigM 30, network_structure 20,
capacity 13, demand 9, count_limit 5, unclassified 27 (**88.1%** classified).

## Mapping onto the `lp2graph` canonical schema

The structural facet aligns with fields `lp2graph` already has, so it is a
*deterministic projection*, not new modelling:

| This taxonomy | `lp2graph` canonical field |
|---|---|
| variable `algebraic_type` | `variables[].domain` (`binary`/`integer`/`continuous`) |
| variable `domain_role` | `variables[].role` — extend the enum with the 6 domain roles |
| constraint `relation` | `constraints[].comparator` (`eq`/`le`/`ge`) |
| constraint `flags.has_big_m` | `constraints[].kind = "big_m"` + `parameters[].kind = "big_m"` |
| constraint `flags.aggregation_*` | term `operator` (`sum`/`max`/`min`) |
| constraint `flags.periodic_modulo` | index `cyclic=true` / binding `modulo` |
| parameter `structural_kind` | `parameters[].kind` |
| **domain facet (both)** | **NEW attribute** `domain_class` on variables/constraints/parameters — purely additive; does not disturb existing views/metrics. |

The **domain facet is additive metadata**: it can be attached to canonical
formulations without breaking schema/hybrid/ground views or metrics. Full
element-level mapping of the extraction JSON into canonical *terms with bindings*
requires parsing the `expression_latex`/code — that is the Phase-3 parser job,
not this categorizer.

## Reversibility hook

Each extracted element preserves `source_symbol` (the original code identifier).
Combined with the structural facet, this is the anchor for the Phase-3 goal of
**dialect translation**: canonical graph → target dialect, with domain/structural
facets carried as node attributes for GNN-on-MILP work and for cross-formulation
comparison.

## Known rough edges (for review)

- Priority ordering can shadow a secondary meaning (e.g. a "1 if route used"
  binary classifies as `routing_path_column` before `selection_assignment`).
  `domain_secondary` / `linked_variable_roles` retain the lost signal.
- 27 `unclassified` parameters are mostly bare scalars whose meaning text is too
  terse for a rule; these are the first candidates for manual gold labeling.
- The structural `has_big_m` detector is regex-based on LaTeX/plain text; once
  formulations are mapped to canonical terms it should read the big-M *kind*
  directly instead.
