# MILP Extraction — Methodology, Process & Design Decisions

This document records *how* the formulations in `extracted_milps/` were produced
and *why* the process is shaped the way it is. It is the companion to
[`INDEX.md`](./INDEX.md) (the per-model summary) and the per-repo
`{owner}__{repo}.json` files.

## Purpose

The extracted JSON files are **input data** for a downstream pipeline
(`lp2graph` graph representation + model mining / benchmarking / comparative
analysis). They are *not* solver artifacts. The optimization models in 17
permissively-licensed public repositories (railway rescheduling, railway
timetabling, transport operations) are transcribed into one machine-readable,
schema-consistent document per repository. Machine-readable consistency and
**faithfulness to source** matter more than narrative completeness.

This corpus is also the empirical basis for the next phase: deriving a
**MECE domain categorization** of constraints / variables / parameters and a
**deterministic, dialect-agnostic code→graph parser** for `lp2graph`. The
categorization cannot be designed honestly until the real distribution of
modelling constructs across these repos is visible — hence extraction first.

## Process (activity diagram)

```mermaid
flowchart TD
  subgraph GATE[1 · Verification gate]
    A0([Start: 17 repos]) --> A1{Repo exists?<br/>GitHub/GitLab API}
    A1 -- no --> AX[Log SKIP in INDEX.md]
    A1 -- yes --> A2{License still<br/>permissive?}
    A2 -- "no / changed to non-permissive" --> AX
    A2 -- yes --> A3[Record license + any anomaly]
  end

  A3 --> B1
  subgraph ACQ[2 · Acquisition]
    B1[Shallow clone --depth=1] --> B2{Subfolder-only<br/>mega-repo?}
    B2 -- yes --> B3[Sparse-checkout target folder]
    B2 -- no --> B4[Full shallow tree]
    B3 --> B5[Do NOT build / run / modify]
    B4 --> B5
  end

  B5 --> C1
  subgraph LOC[3 · Locate formulations]
    C1[Apply dialect construction hints] --> C2{Construction API found?}
    C2 -- "gurobipy / pyomo / pulp / docplex" --> C3[Python model]
    C2 -- "GRBModel / IloModel / Cplex" --> C4[C++ / C# / Java model]
    C2 -- "LP / MPS / AMPL file" --> C5[Flat-format model]
    C3 --> C6[One models[] entry per distinct formulation]
    C4 --> C6
    C5 --> C6
  end

  C6 --> D1
  subgraph XTRACT[4 · Transcribe]
    D1[Map code identifier -> math symbol<br/>reuse README/paper notation] --> D2[sets_indices]
    D2 --> D3[parameters]
    D3 --> D4[decision_variables]
    D4 --> D5[objective]
    D5 --> D6[constraints]
    D6 --> D7[instances by path+size, never inlined]
    D7 --> D8{Field determinable<br/>from code/README/paper?}
    D8 -- no --> D9[Set null + explain in extraction_notes]
    D8 -- yes --> D10[Fill value + source_files line refs]
  end

  D9 --> E1
  D10 --> E1
  subgraph OUT[5 · Emit & guard]
    E1[Write owner__repo.json] --> E2[Copy LICENSE verbatim -> sidecar]
    E2 --> E3[Validate JSON parses]
    E3 --> E4[Verify against source:<br/>every constraint/objective has real line refs]
    E4 --> E5{Fabrication or<br/>misread detected?}
    E5 -- yes --> D1
    E5 -- no --> E6[Accept]
  end

  E6 --> F1[Aggregate INDEX.md row per model_id]
  F1 --> F2([Corpus ready for categorization + parser design])
```

## Tooling / execution model

- The first repo (`marcotallone/railway-scheduling`) was extracted **by hand**
  as a reference exemplar to validate that the target schema fits real code and
  to fix the quality bar.
- The remaining repos are extracted by **per-repo subagents** running in
  parallel, each pointed at the exemplar and the hard rules below. Every
  subagent's output is then **verified against the cloned source** before being
  accepted — subagent summaries describe intent, not ground truth.
- Sources are cloned under `/home/joern/milp_sources/` (kept, not committed) so
  the later code→graph parser work has the real code to test against.

## Design decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **One JSON file per repo**, `{owner}__{repo}.json` | Stable, greppable, 1:1 with provenance and license sidecar. |
| D2 | **One `models[]` entry per distinct formulation** | A repo may hold several (e.g. OpenLinTim: line planning, PESP timetabling, delay mgmt, VSP; mtct: VSS/routing variants). Each is independently minable. |
| D3 | **`null`, never a guess** | The corpus feeds automated analysis; a fabricated symbol is worse than a recorded gap. Gaps are explained in `extraction_notes`. |
| D4 | **Every constraint/objective carries `source_files` line refs** | Makes each claim auditable against source and anchors the future parser. |
| D5 | **`source_symbol` records the code identifier** | Preserves the code↔math mapping needed for the *reversible* dialect translation goal. |
| D6 | **Instances referenced by path + size, never inlined** | Datasets can be large; the corpus stays lightweight and license-clean. |
| D7 | **LICENSE copied verbatim into a sidecar** | Keeps the extracted bundle redistributable and compliant. |
| D8 | **`extraction_confidence` = how directly the model came from code** | `high` = code + documented math agree; `low` = inferred from prose/paper. Lets downstream weight noisy entries. |
| D9 | **Skip only on confirmed non-permissive license change** | A missing/auto-undetected LICENSE (e.g. IBM samples) is an anomaly to log, not grounds to skip. |
| D10 | **Mega-repos use sparse-checkout for the named subfolder** | Avoids cloning unrelated examples (Gurobi modeling-examples, IBM CPLEX-samples). |
| D11 | **Extraction schema is intentionally richer than `lp2graph`'s canonical schema** | This is a faithful *source-level* transcript (latex + plain + source refs). A later deterministic mapping projects it onto the `lp2graph` template/term/quantifier model. |

## Hard constraints (enforced on every entry)

- Do **not** solve, run, build, or modify any model.
- Do **not** fabricate constraints, parameters, or symbols — `null` + explanation instead.
- Do **not** inline large datasets — reference by relative path.
- Preserve every upstream LICENSE.
- Skip (and log) any repo whose license changed to non-permissive.

## Relationship to `lp2graph` (next phases)

`lp2graph` already provides: a deterministic, pydantic-mirrored canonical JSON
schema; schema/hybrid/ground views; structural metrics; and PyG/DGL/NetworkX
exports. It explicitly *consumes already-structured formulations*. The work
beyond this corpus is therefore:

1. **MECE domain categorization** — derive mutually-exclusive, collectively-
   exhaustive domain classes for constraints (e.g. headway, capacity,
   flow-conservation, coupling/linking, assignment, time-window, big-M
   linearization, …), variables (e.g. assignment, ordering/precedence, timing,
   flow, indicator/auxiliary, …) and parameters, grounded in what this corpus
   actually contains.
2. **Deterministic dialect parser** — code (gurobipy/pyomo/pulp/docplex/CPLEX-
   C++/Concert/LP/MPS) → `lp2graph` canonical graph, flexible across dialects,
   with enough preserved structure (`source_symbol`, bindings, roles) to enable
   reverse translation between dialects.

The categorization *method* (keyword/heuristic vs. ML on a synthetic dataset)
is deliberately left open until the corpus distribution is visible — see the
open question carried into the next phase.
