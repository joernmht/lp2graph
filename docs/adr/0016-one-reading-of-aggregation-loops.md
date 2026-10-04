# ADR-0016: One reading of an aggregation's loops, shared by emitter, views and grounder

- **Status:** accepted
- **Date:** 2026-10-04

## Context

A canonical `Term` with `operator="sum"` stores two things about its binder:
`operator_over`, the families it ranges over, and per slot of the referenced
template a `Binding` whose `expr` names the dummy feeding that slot. The
binder's own dummy names are not stored. Every consumer therefore has to pair
the summed families with the dummies the bindings use, and three consumers did
that pairing three different ways:

| consumer | reading | defect |
|---|---|---|
| `solve/grounder.py` | loop over the dummies the bindings use that the row leaves free; `operator_over` never read | `\sum_{i \in I, r \in R} dur_r` grounded to `\sum_r dur_r`, `\sum_{i \in I} 5` to `5` (issue #60) |
| `views/ground.py` | loop over `operator_over`, scope keyed by **family**, bindings resolved by **dummy** | no summed term ever produced an edge; bindings collected into a dict keyed by family, so `y_{i,j}` over `I x I` reached `y[j,j]` |
| `codec/latex.py` emitter | each family takes the first binding of that family | `\sum_{t \in T} x_{t-1}` printed as the unparseable `\sum_{t-1 \in T}`; `\sum_{j \in I} y_{i,j}` under `\forall i` printed as `\sum_{i \in I} y_{i,j}`; a summed constant printed without its binder |

None of these was caught: the codec's fixed-point tests ran over models whose
sums use every summed family with a fresh dummy, the ground-view tests counted
nodes and never edges, and no solved model had a summed family its referent
does not use. The defects surfaced while canonicalising the Gurobi
railway-dispatching MILP for the Paper-1 anatomy figure, whose objective
subtracts `\sum_{i \in I, r \in R} dur_r`.

The paper states that the ground view "is used for rendering at small sizes
and, exported to PyG/DGL, as input to downstream graph learning", and that the
grounder makes a mined model executable; both claims rest on these readings.

## Decision

1. **One module, `lp2graph.core.scope`, owns the reading.** A family of
   `operator_over` takes the first *free* dummy (one the row's quantifiers do
   not bind) whose slot family it is; a family no dummy matches is a loop the
   referent does not vary with, which repeats the summand once per element
   (`\sum_{i \in I} c = |I| c`). `aggregation_loops` is the evaluation reading
   (grounder, ground view); `binder_loops` is the emitter's, which reproduces
   the binder as written.
2. **Free dummies no summed family takes are aggregated**, as the grounder
   always did: that is how `abs` terms (which carry no `operator_over`) and
   models written before `operator_over` was populated are read (`|t_i|`
   under a free `i` is `\sum_i |t_i|`). The ground view now reads `abs` the
   same way.
3. **A binder whose family disagrees with the referent's declared shape is
   refused for evaluation** (`AggregationError`, surfaced by the grounder as
   `UnsupportedModel`): in `\sum_{k \in K} x_k` with `x` declared over `I`,
   which elements of `I` the elements of `K` denote is not in the model. The
   grounder used to loop `k` over `I`, silently. The emitter still prints the
   binder as written, so the text round-trips.
4. **Bindings resolve by slot position** in the ground view, as in the
   grounder. A recurring summand (a counting loop, a cyclic wrap onto the same
   instance) is one edge carrying `multiplicity`.
5. **The emitter names a counting loop with a fresh dummy** (the family's
   lower-case name, suffixed `p` until it is unused in the row), so it never
   re-binds a quantifier's dummy.

Issue #61 is decided alongside because it is the same kind of omission (a
model fact the graph did not carry): a quantifier's `where`-predicate is a
`uses_parameter` edge of role `where` in the schema and hybrid views.

## Consequences

Measured over the 10 catalog fixtures and the 25 canonical models of the lab
corpus (18 promotions, 7 repository conversions) before and after:

- Solved values change for every model with a summed family its referent does
  not use, and for summed constants: they are now the values the text states.
  In the lab corpus that is one model (the railway-dispatching anatomy
  example); its argmin is unchanged because the affected term is constant.
- Five lab models sum over a **subset family** (`\sum_{r \in \mathcal{R_k}}
  x_r` with `x` declared over `R`). The emitter used to print them with a
  dummy the summand does not use (`\sum_{r_k \in \mathcal{R_k}} x_r`, the
  model round trip was intact, the text was not); they now print as written.
  The grounder now refuses them (decision 3) where it used to sum over all of
  `R`. Grounding them needs the subset as data (a membership parameter and a
  `where`-predicate), which is a modelling step, not a reading.
- The 10 catalog fixtures emit byte-identical LaTeX.
- Ground views gain the edges of every aggregated term. Any ground graph
  exported before this change was missing them.
- Schema graphs gain one edge per `where`-predicate, so isomorphism and WL
  results change for models that select rows by attribute (one in the lab
  corpus). Every other schema graph is byte-identical.
- Hybrid graphs change for the five models with a same-family pair variable
  (`I.1`/`I.2` offset keys); every other hybrid graph is byte-identical.
- Tests: `tests/test_aggregation_scope.py` (each defect, confirmed to fail on
  the previous code).
