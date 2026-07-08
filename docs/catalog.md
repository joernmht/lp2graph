# Catalog & where to start

!!! tip "Interactive demo"
    New here? Open the **[mobile demo hub](https://lp2graph.joernmaurischat.de/)**:
    [explore the representation](https://lp2graph.joernmaurischat.de/explore.html)
    (status quo — a clickable typed graph of a real catalog formulation) or try the
    [model configurator](https://lp2graph.joernmaurischat.de/configurator.html)
    (vision — compose a model and export it as text, PuLP/Gurobi or LaTeX).

## Catalog

| ID | Family | What it demonstrates |
|---|---|---|
| `lp_1_1_fixed_sequence` | LP | Fixed-sequence retiming with headway and earliest-departure constraints, makespan-style objective. |
| `lp_1_5_soft_regularity` | LP | Soft constraints with paired positive/negative slack variables and a weighted-sum objective. |
| `mip_2_1_big_m` | MILP | Pairwise ordering disjunction encoded with big-M; binary indicators with `ne_other` and `ordered_pair` quantifier restrictions. |
| `mip_2_4_time_indexed` | MILP | Time-indexed assignment with set-packing and capacity constraints; multi-index aggregation. |
| `mip_2_8_pesp` | MILP | PESP cyclic timetabling with integer wrap variables and modulo bindings. |
| `multi_obj_lateness_energy` | MILP | First-class objective with explicit weighted-sum combination. |
| `objective_lex_priority` | LP | Lexicographic objective combination. |
| `objective_abs_deviation` | LP | Absolute-value operator on objective terms. |

The catalog is in active expansion. Open a `new-formulation` issue to
propose additions; see [`add-a-formulation`](add-a-formulation.md).

## Where to start

1. [Data model](data-model.md) — the JSON schema and pydantic types.
2. [Views](views.md) — schema, hybrid, ground, and when to use each.
3. [Metrics](metrics.md) — what is computed and what it tells you.
4. [Add a formulation](add-a-formulation.md) — contributing checklist.
5. [Design context](design-context.md) — why the library exists and the
   choices that shape it.
6. [Extraction report](extraction-report.md) — provenance from the
   source repo.

## Architecture decisions

ADRs live in [`adr/`](adr/). Each significant choice gets one. See
[ADR-0001](adr/0001-build-tool.md) for the build-tool choice,
[ADR-0002](adr/0002-internal-graph.md) for the internal graph type,
[ADR-0003](adr/0003-license.md) for the license choice, and
[ADR-0004](adr/0004-schema-versioning.md) for the schema versioning
policy.
