---
title: "A Verified, Categorized Corpus of Railway and Transport MILP Formulations for Graph-Based Model Mining"
author: "TU Dresden — railway optimization & knowledge-graph research"
date: 2026-05-31
---

## Abstract

We present a reproducible pipeline that mines mixed-integer linear programming
(MILP) and linear programming (LP) formulations from public, permissively
licensed source repositories and renders them as structured, schema-validated
data for graph-based analysis. From 17 repositories spanning railway
rescheduling, railway timetabling, and transport operations, we extract 28
distinct formulations into a single canonical JSON schema, preserving for every
constraint and objective an auditable link to the exact source lines from which
it was transcribed. We then apply a deterministic, two-axis *faceted*
categorization — a structural axis computed from the formulation and a
domain-function axis derived by rules informed by variable roles — achieving
96.7% / 100% / 88.1% labeling coverage for variables, constraints, and
parameters. Finally, we validate the corpus by solving the formulations that are
tractable in an open environment and by checking that a model expressed in one
modelling "language" yields the same optimum after translation to another and
submission to an independent solver. The corpus, categorizer, taxonomy, and
validation harness are released together as the data substrate of `lp2graph`, a
library that represents LP/MIP/MILP formulations as typed graphs.

## 1. Introduction

Graph neural networks and structural analysis over optimization formulations
("GNN-on-MILP") require a stable, machine-readable substrate: formulations as
*data*, not as solver output. Real research code, however, expresses the same
mathematical model in a wide variety of dialects — `gurobipy`, `docplex`,
`PuLP`, Pyomo, CPLEX/Concert in C++/C#/Java, FICO Xpress Mosel, or flat
LP/MPS files. The mathematics is shared; the syntax is not. Our goal is to
recover the shared mathematics into one representation that downstream tooling
can reason about, compare across formulations, and eventually translate back to
any dialect.

This work is the upstream data layer for `lp2graph`, a deterministic library
that turns a canonical formulation into three graph views (schema, hybrid,
ground), computes structural metrics, and exports to PyG/DGL/NetworkX. By design
`lp2graph` *consumes already-structured formulations*; producing those
structures faithfully is the problem addressed here. We contribute: (i) a
verified extraction corpus, (ii) a deterministic faceted categorization grounded
in the corpus, and (iii) a solve-and-translate validation layer.

## 2. Corpus construction

**Source selection.** Seventeen repositories were pre-selected for permissive
licensing (MIT, Apache-2.0, CC0-1.0) and topical relevance (railway
rescheduling, railway timetabling, transport operations). Each was verified
live against the GitHub/GitLab APIs for existence and unchanged license before
cloning; none required skipping. One anomaly was logged rather than skipped: the
IBM CPLEX-samples repository declares Apache-2.0 in its README but ships no
`LICENSE` file, so the declared statement was preserved with a note.

**Extraction.** Repositories were shallow-cloned (sparse-checkout for the two
that bury the relevant model inside a large monorepo) and **never built, run, or
modified** during extraction. Each formulation was transcribed into a JSON
document with explicit `sets_indices`, `parameters`, `decision_variables`,
`objective`, and `constraints`. For every constraint and the objective we record
both a human-readable plain-text description and a LaTeX expression, *and* a
`source_files` list of `path:line-start–line-end` references to the exact code
or model file from which it was read. Every code identifier is mapped to a
mathematical symbol, with the original identifier retained in `source_symbol` —
the anchor for later reverse translation. The full process, including the
dialect-specific construction hints used to locate models, is documented as an
activity diagram in `METHODOLOGY.md`.

**Discipline against fabrication.** The governing rule was: never invent a
constraint, parameter, symbol, or DOI; where a field cannot be determined from
code, README, or paper, set it to `null` and explain. This rule produced several
honest, load-bearing findings rather than fabricated content: one repository
nominally listed as having a "CPLEX baseline" in fact contains **no (MI)LP at
all** (it is a pure QUBO/HOBO formulation for quantum annealing); the IBM
`timtab1` model is an anonymous MPS instance whose per-row semantics are
genuinely unrecoverable and are left `null`; and column-generation repositories
whose pricing step is an algorithm (labeling / resource-constrained shortest
path) rather than an LP are documented as such, with no fabricated subproblem LP.

**Scale and verification.** The corpus comprises 17 repositories, 28
formulations, 224 constraint entries, and 123 decision-variable entries, with
verbatim LICENSE sidecars for each repository. As an automated integrity check,
every `source_files` reference was resolved against the cloned sources: **407
references, 0 missing files, 0 out-of-bounds line ranges**. This is strong
evidence that the transcription is anchored in real code rather than
hallucinated.

## 3. Faceted categorization

A single flat "MECE" label per element is attractive but does not survive
contact with real models: keyword classification of the 224 constraints is
heavily multi-label (a headway constraint is *also* a big-M linearization; an
assignment constraint is *also* a bounds statement). We therefore adopt a
**two-axis faceted** scheme.

- **Structural facet** — derived deterministically from the formulation
  (comparator → equality/inequality; aggregation operator; big-M presence;
  modulo/cyclic; indicator; definitional equality). No learning, no ambiguity.
- **Domain facet** — the semantic function (headway, capacity,
  flow-conservation, …), resolved by priority-ordered rules. Crucially, the
  rules are **variable-informed**: variables are categorized first into six
  roles (selection/assignment, ordering/precedence, routing/path-or-column,
  timing, flow/quantity, auxiliary/linearization), and a constraint whose name
  and text are inconclusive inherits a domain hint from the roles of the
  variables it links.

The categorizer is deterministic and dependency-free. On the corpus it labels
**96.7%** of variables, **100%** of constraints (primary domain), and **88.1%**
of parameters, leaving the remainder explicitly `unclassified` rather than
guessed. The structural facet maps directly onto fields `lp2graph` already
carries (`comparator`, term `operator`, parameter `kind`); the domain facet is
introduced as an additive optional attribute (`domain_role` on variables,
`domain_class` on constraints and parameters) so it does not disturb existing
schema views or metrics.

We deliberately defer machine learning. With 28 models the real corpus is the
gold seed; rules are transparent and reproducible. ML on a *synthetic* dataset
was considered and rejected as premature — the synthetic distribution may not
match real repositories, and the rule baseline must first demonstrate where it
plateaus, at which point any learned model would be trained on the real labeled
corpus (synthetic only as augmentation).

## 4. Validation: reference optima and cross-language fidelity

The extraction and categorization layers establish that the corpus is faithful
and well-organized. A third layer asks an operational question: do the
formulations *solve*, and does a model survive translation between modelling
languages? We run three experiments in an environment with Gurobi 13 (academic
WLS license), HiGHS, and CBC (via PuLP), all single-threaded with a 120 s limit.

- **Experiment A (cross-solver, portable interchange).** The `timtab1` model is
  shipped as a solver-neutral MPS file. We solve it with all three solvers; the
  reported optima must agree. MPS is precisely the dialect-neutral lingua franca
  the project ultimately targets, so agreement here is direct evidence that a
  formulation's meaning is solver-independent.
- **Experiment B (round-trip translation).** Gurobi reads the model and
  *re-emits* it to both `.mps` and `.lp` — its writer acting as a translator
  into two other textual dialects. The re-emitted files are solved again across
  solvers; agreement demonstrates that translation preserves the optimum.
- **Experiment C (from-repo Python model).** The `marcotallone/railway-scheduling`
  `gurobipy` model is built directly from repository code on its smallest shipped
  instance, solved for a reference optimum, then exported to portable `.lp`/`.mps`
  and cross-solved. This is the end-to-end check on actual repository code:
  modelling language → interchange format → independent open-source solver.

Not every repository can be solved in an open environment: the corpus
deliberately spans commercial solvers (CPLEX, Xpress) and compiled toolchains
(C#/.NET, C++, Java) whose builds are out of scope, plus one quantum-annealing
QUBO that is not an LP at all. The complete runnability matrix is given in
`validation/README.md`; the portable-format experiments are exactly the answer
for the cases where a native build is impractical.

## 5. Results

All runs used Gurobi 13.0.2, HiGHS 1.14.0, and CBC (PuLP 3.3.2), single-threaded.
Full machine-readable output is in `validation/results/validation_results.json`
and `summary.csv`.

**Experiment A — reference optima and cross-solver agreement (timtab1).**
Gurobi and HiGHS both **prove the same optimum, 764 772.0** (to within 1e-6;
Gurobi 127.5 s, HiGHS 169.7 s). CBC returns 784 722.0 at the 180 s limit — a
*time-limited incumbent* that PuLP reports with status "Optimal" (a known PuLP
quirk: CBC stopping on time with a solution is surfaced as optimal). So the
reference optimum is established and two independent solvers agree on it; the CBC
number is a caveat, not a disagreement, and also illustrates that an
open-source branch-and-bound solver does not close this MIP in the budget.

**Experiment B — round-trip translation fidelity (timtab1).** After Gurobi
re-emits the model to `.lp` and `.mps`, the re-emitted **`.lp` solves to
764 772.0 under both Gurobi and HiGHS**, and the re-emitted `.mps` likewise
(764 772.0 for Gurobi and HiGHS; CBC again time-limited at 784 722.0). The
optimum is invariant under translation across two textual dialects and two
solvers — the property the project relies on.

**Experiment C — from-repo Python model with a big-M caveat (marcotallone).**
The `gurobipy` model is built directly from repository code on the smallest
shipped instance (4 600 variables, 9 755 constraints, 3 250 integer). At
**tight tolerances** the native solve, the re-read exported `.mps`, and an
independent HiGHS solve **all agree on 3 913.47** (Gurobi native and re-read
3 913.4655/3 913.4656; HiGHS 3 913.4656). At **default tolerances** the same
model reports a spurious, better-looking 3 067.03. The objective constant
(−715 484.71) is preserved across the round-trip in both cases, so the
discrepancy is *not* a translation error: it is the classic **big-M effect** —
with M = 10^5 and a 10^-6 relative feasibility tolerance, a big-M term may be
violated by up to ~10^-1 in absolute terms, letting the solver certify a
slightly-infeasible solution with a lower objective. We confirmed this by fixing
the default-tolerance solution into the re-read model: under tight tolerances it
is rejected. This finding is precisely what `lp2graph`'s structural `has_big_m`
flag (set on 39 of the 224 constraints in the corpus) is intended to surface.

To remove the hazard by design, `lp2graph` now carries an optional `indicator`
gate on constraints and a deterministic, solver-free transform
(`lp2graph.transform.bigm`) that emits either a **native indicator constraint**
(Gurobi/CPLEX — exact, no `M`) or a **big-M linearization with the tightest
valid `M` computed from variable bounds** (HiGHS/CBC and older tools). A finite
tight `M` exists whenever the gated expression is bounded; otherwise the
transform refuses to guess and requires an explicit `M`. A demonstration
(`validation/results/indicator_demo.json`) confirms the native-indicator
encoding (Gurobi) and the tight big-M encoding (HiGHS *and* CBC, neither of
which supports native indicators) return the identical optimum — one logical
source of truth, served correctly to every solver class.

A second, tooling-level finding: PuLP's MPS reader fails (`KeyError: 'OBJ'`) on
the objective-row name Gurobi writes, so CBC could not read the exported
marcotallone model. Such interchange-reader incompatibilities are exactly the
kind of fragility a canonical, validated representation is meant to remove.

| Experiment | Model | Solvers in agreement | Optimum | Caveat |
|---|---|---|---|---|
| A reference | timtab1.mps | Gurobi, HiGHS | 764 772.0 | CBC time-limited (784 722, mislabeled "optimal") |
| B round-trip `.lp` | timtab1 re-emitted | Gurobi, HiGHS | 764 772.0 | — |
| B round-trip `.mps` | timtab1 re-emitted | Gurobi, HiGHS | 764 772.0 | CBC time-limited |
| C from-repo (tight) | marcotallone N10T10J10 | Gurobi native, Gurobi re-read, HiGHS | 3 913.47 | default-tol big-M artifact (3 067.03); PuLP can't read Gurobi MPS |



## 6. Discussion and limitations

The validation is intentionally narrow in breadth but rigorous in kind. It does
not re-solve all 28 formulations — most require commercial solvers or heavy
builds — but it demonstrates the property that matters for the project thesis:
the *meaning* of a formulation is preserved across solvers and across textual
dialects, which is the precondition for both faithful graph representation and
future dialect-to-dialect translation. The principal threats to validity are:
(i) extracted symbols in repositories that ship no written mathematics are the
extractor's mapping, not the authors' notation (flagged per formulation, and the
reason several entries carry `medium` confidence); (ii) the categorizer's
priority ordering can shadow a secondary domain meaning, mitigated by retaining
`domain_secondary` and `linked_variable_roles`; and (iii) the structural big-M
detector is regex-based on text and should, once formulations are parsed to
canonical terms, read the big-M *kind* directly.

## 7. Future work

The natural next step (Phase 3) is a deterministic, dialect-agnostic
**code→graph parser**: LP/MPS parse trivially and exactly; the algebraic
modelling APIs (`gurobipy`, Pyomo, PuLP, `docplex`, Concert) are parseable via
their abstract syntax with documented limits where models are built by arbitrary
imperative code. Because the canonical model retains templates, bindings, and
`source_symbol`, a back-end renderer can then translate a formulation into any
target dialect — making the round-trip of Experiment B a general capability
rather than a single demonstration, and enabling reversible dialect translation
and GNN-ready labeled graphs.

## 8. Conclusion

We have built and released a verified, categorized corpus of 28 railway and
transport optimization formulations, together with a deterministic faceted
categorizer and a solve-and-translate validation harness. Every transcribed
constraint is anchored to real source lines, no content was fabricated, and the
formulations that can be solved in an open environment agree across solvers and
across translated dialects. The corpus is the data substrate for `lp2graph` and
the foundation for a forthcoming deterministic parser and reversible dialect
translation.
