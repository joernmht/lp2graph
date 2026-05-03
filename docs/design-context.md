# Design Context

> **Status:** seed document. This is the only document in the repository
> permitted to be subjective. Everything else is precise and verifiable.
> Authored 2026-05-03 during the v0.1 bootstrap.

This document is the **conceptual foundation** of `lp2graph`. It records the
purpose, scope, and design principles that the rest of the repository
operationalizes through schemas, code, and tests.

---

## Purpose

`lp2graph` is a focused, well-tested library for representing **LP, MIP, and
MILP formulations as typed graphs**. It provides:

1. A canonical, version-stable JSON data model for formulations.
2. Three derived **views** of every formulation: a *schema* view (templates and
   indices), a *hybrid* view (templates with offset-labeled term edges), and a
   *ground* view (a fully instantiated graph at given index cardinalities).
3. A library of **structural metrics** computed deterministically over the
   canonical model and the derived views.
4. **Renderers** that produce SVG/HTML and an interactive viewer for visual
   comparison across formulations and views.
5. **Export adapters** to PyG, DGL, NetworkX, LaTeX, and Pyomo skeletons,
   keeping the core library solver-free.

The audience is researchers and engineers who need a stable substrate for
GNN-on-MILP work, formulation comparison, teaching material, and tooling
that reasons about optimization problems as data — not as solver output.

## Scope

**In scope (v1):**

- Canonical data model and schema (constraints, objectives, indices,
  parameters, quantifiers).
- View derivations (schema, hybrid, ground).
- Structural metrics over the canonical model and derived graphs.
- Rendering and interactive viewer.
- Export adapters: PyG, DGL, NetworkX, LaTeX, Pyomo (stubs).
- A catalog of representative LP, MIP, and MILP formulations.

**Out of scope (v1):**

- Solving. `lp2graph` does not invoke Gurobi, CPLEX, HiGHS, etc. Solver
  output (LP relaxation gaps, basis information, primal/dual values) is
  *not* computed by this library; if needed, it is supplied by the caller
  and consumed as additional metadata.
- Full code generation for solvers. Pyomo and JuMP exports are stubs in v1.
- LLM-driven formulation extraction from text. The upstream research
  project does this; `lp2graph` consumes already-structured formulations.

## Core abstractions

### Formulation

A `Formulation` is the top-level container. It has:

- An `id`, a `name`, a `family` (`lp` | `mip` | `milp`), and a free-form
  `description`.
- A set of **index families** (e.g. `i ∈ I`, `t ∈ T`).
- A set of **parameters** (e.g. `M`, `δ_min`, `c_i`).
- A set of **variable templates** (e.g. `x[i]`, `y[i,j]`, `z[i,t] ∈ {0,1}`).
- A set of **constraint templates**.
- A set of **objective terms** (objectives are first-class).
- Optional metadata: provenance, tags, references.

### Templates vs instances

Every constraint and variable in a formulation is a **template**: a
quantified, parameterized object. A template has a *shape* (which indices
it depends on), a *body* (terms with coefficients, references to variables
and parameters, comparators, right-hand side), and *quantifiers* (which
index families it ranges over, with optional restrictions like `i ≠ j` or
`t < T`).

An **instance** is what you get when you ground a template at a specific
tuple of index values. Instances exist only in the *ground view*; the
canonical model stores templates.

### Indices as nodes

Indices are first-class graph nodes in the schema and hybrid views. This is
a deliberate choice: it makes the *binding pattern* of a constraint visible
without instantiating it. A constraint that ranges over `(i, j) ∈ I × I, i ≠ j`
shows two edges to the `I` index node, not one — and the `i ≠ j` restriction
is recorded as a quantifier annotation, not lost in the grounding.

### Term, refs, bindings, role, sign

Every constraint and objective body is a list of **terms**. Each term has:

- A **coefficient** — a parameter reference or a literal.
- A **ref** — what variable template (or parameter, in the RHS case) is
  being referenced.
- A **bindings** list — for each index slot of the referenced template,
  *which* index variable is bound, and *with what offset* (e.g.
  `t → t-1`, `j → j+k mod T`).
- A **role** — `lhs`, `rhs`, `objective`, `slack`, `aux`, etc. The role
  determines edge coloring in the rendered graph.
- A **sign** — `+1` or `-1` (multiplied into the coefficient at evaluation
  time, but kept separate so renderers can show it explicitly).

This is the pattern that makes the schema/hybrid/ground views derivable
from a single source of truth. The schema view collapses bindings to the
index; the hybrid view labels term edges with offsets; the ground view
substitutes concrete values.

### Three views

- **Schema view** — templates and indices only. Offsets are hidden. This is
  the "topology of the formulation" — which template touches which index,
  which parameters appear where.
- **Hybrid view** — schema view plus term-edge labels for offsets, signs,
  and roles. This is the most informative view at template scale and is
  the default for visual inspection.
- **Ground view** — fully instantiated. Requires a `cardinalities` map
  (e.g. `{"I": 5, "T": 8}`). Applies degeneracy filters: out-of-range
  offsets, `i ≠ j` exclusions, ordered-pair restrictions. The result is a
  concrete graph ready for ingestion by GNN frameworks.

### Metrics

Metrics are **derived**, not stored. They are pure functions
`Formulation → MetricResult` or `Graph → MetricResult` with deterministic
output. Examples: node counts by class, edge density, presence flags
(big-M, integer variables, modulo offsets, soft slack, aggregation
operators), symmetry diagnostics, and tightness proxies.

## Design decisions already made

1. **Indices are nodes.** Not edge attributes; not implicit in template
   names. This is what makes pattern matching across formulations
   tractable.
2. **Templates, not instances, are the source of truth.** The ground view
   is derived; it is never stored.
3. **Objectives are first-class.** The objective is not a special
   "constraint" — it has its own section in the schema and its own term
   structure, but the term semantics (refs, bindings, role, sign) are
   shared.
4. **Solver-agnostic.** Core has no solver dependency. Pyomo, JuMP, and
   friends live in optional extras.
5. **Library-agnostic internal graph.** PyG, DGL, and NetworkX are export
   targets, not internal representations. The internal `Graph` is a thin
   typed structure.
6. **Determinism everywhere.** Every derivation, render, and export is
   deterministic. Snapshot tests guard regressions.
7. **Apache 2.0 license.** Source repo is MIT (compatible). New repo is
   Apache for explicit patent grant.

## Open questions

These are intentionally unresolved and tracked as `open-question` issues.
They are *not* bugs; they are honest expressions of where the v1 model has
not yet committed.

1. **Hyperedges vs operator nodes for aggregation.** Time-indexed and PESP
   formulations use windowed sums and modulo aggregations. v0.1 uses
   operator nodes; hyperedges may be cleaner. Decision deferred.
2. **Objective representation depth.** Soft constraints introduce auxiliary
   variables whose meaning is bound to the objective. Should objective–
   constraint linkage be encoded explicitly?
3. **Solver-language export scope.** v1 ships stubs. Big-M tightening,
   indicator translation, and PESP modulo unrolling are non-trivial.
4. **Constraint generation patterns.** Separation cuts, lazy constraints,
   column generation — how does the model express formulations whose
   constraint set is not fully enumerated upfront?
5. **Schema versioning policy.** What is the migration path when the
   canonical schema needs a breaking change?

## Visual standards

The rendering and viewer are designed to be **distinctive**, not generic.
Specifically:

- Typography: **Fraunces** for display text, **JetBrains Mono** for
  identifiers and code-like content. Rendered as system-font fallbacks if
  the web fonts are not available, but the choice is intentional.
- Palette: deliberate, role-based. Variables, constraints, objectives,
  indices, parameters, and operators each have their own hue. Soft
  constraints and slacks share a desaturated band to mark their auxiliary
  nature.
- Borders: subtype-based. Integer variables get a thicker stroke than
  continuous; binary variables get a doubled stroke. Big-M constraints get
  a dashed border.
- Edge styles: role-based. `lhs` solid, `rhs` thicker, `objective` colored,
  `slack` dashed, `aux` dotted.

These choices are not negotiable in the rendered output of v1 — they are
part of the library's identity. If a downstream user wants different
styling, they consume the typed `Graph` and render it themselves.
