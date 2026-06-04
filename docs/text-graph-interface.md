# Deterministic text ⇄ graph interface

This document describes the bidirectional, **deterministic** (no LLM in the
loop) interface between a MILP's *text* and its *graph* (the lp2graph
canonical model), and the end-to-end validation that it preserves the
solvable problem.

Three new capabilities were added on top of the existing canonical model:

| Direction | Module | CLI | What it does |
|-----------|--------|-----|--------------|
| graph → text (LaTeX) | `lp2graph.codec.to_canonical_latex` | `lp2graph latex` | renders a paper-style LaTeX document (`\mathcal` sets, `\sum`, `\forall`, big-M, …) |
| text → graph (LaTeX) | `lp2graph.codec.from_canonical_latex` | `lp2graph parse` | parses that document back to the canonical model |
| graph → MILP → solve | `lp2graph.solve` | `lp2graph solve` | grounds the model with instance data and solves it |
| graph → text (prose) | `lp2graph.nl.describe` | `lp2graph describe` | generates a natural-language problem description + data tables |

Everything is deterministic: the same input always yields byte-identical
output. There is no model, no sampling, no temperature.

---

## 1. LaTeX ⇄ graph codec

### What the LaTeX looks like

`to_canonical_latex` emits a document in two parts. A `%@` **annotation
header** (LaTeX comments — invisible when typeset) carries the metadata
that has no algebraic surface form, and an `align` **body** carries genuine
paper math:

```latex
%@ meta id=mip_2_8_pesp family=milp schema=0.1.0
%@ index E ordered=0 cyclic=0 :: Events.
%@ var k shape=E,E domain=integer role=auxiliary ... :: Period wrap counter.
\begin{align}
  \min\quad & \sum_{i \in \mathcal{E}, j \in \mathcal{E}} k_{i,j} \tag{tension} \\
  & t_{j} - t_{i} + \mathit{T\_period} \cdot k_{i,j} \ge l_{i,j}
        \qquad \forall i \in \mathcal{E},\; \forall j \in \mathcal{E},\; j \neq i \tag{pesp\_lower} \\
  ...
\end{align}
```

The **algebra alone determines the solvable model.** The parser
reconstructs the structured model from the body using the *symbol table*
declared in the header: because every variable and parameter is declared
with its index shape, a natural subscripted symbol like `t_{j}` or
`x_{i,t}` resolves unambiguously to a referent of the right kind with the
right index-family bindings (`t` has shape `[E]`, so `t_{j}` binds family
`E` to the loop variable `j`; offsets like `t_{i-1}` are parsed too).

### The determinism guarantee

The codec is an inverse pair up to a documented normalization
(`canonical_normal_form`). Two properties are tested across **every**
formulation in the catalog:

- **Text-level idempotence** — the LaTeX serialization is a fixed point:

  ```
  to_canonical_latex(from_canonical_latex(to_canonical_latex(f))) == to_canonical_latex(f)
  ```

- **Normal-form round-trip** — `from_canonical_latex(to_canonical_latex(f))`
  has the same canonical normal form as `f`.

The *solvable content* (sets, parameters, variables, constraints,
objective) round-trips **exactly**. Only incidental labels are normalized:
a literal term's `ref` name, a redundant `offset` that disagrees with its
own `expr`, a negative numeric coefficient folded into the sign, and a
term's `role` (which only drives edge coloring). None affect grounding or
solving. See `lp2graph/codec/normalize.py`.

---

## 2. Grounding solver back-end

`lp2graph.solve` replaces the v0.1 Pyomo *stub* with a real grounding
back-end. Given a `Formulation` and an `Instance` (index cardinalities +
parameter values), it materializes every variable and constraint instance
with concrete numeric coefficients, builds a `pulp.LpProblem`, and solves
it (CBC by default; HiGHS and Gurobi also supported).

Supported — the linear core covering LP / MIP / MILP and big-M models:
index families with ordered/cyclic wrap; all four variable domains and
bounds; quantified constraints with `ne_other`/`<`/`<=`/`>`/`>=`/
`ordered_pair` restrictions and `where`-clause filters; terms with numeric
or parameter coefficients, signs, index offsets (`t-1`), and `\sum`
aggregation; parameter/literal constant terms; `sum`/`weighted_sum`
objectives. Big-M and PESP modulo are plain linear constraints and are
fully supported.

A key correctness point: a constraint instance where a **non-aggregated**
term references an out-of-range index (a boundary like `t_{i-1}` at `i=0`)
is **omitted**, not partially enforced — matching the ground view's
degeneracy semantics. Aggregated (`\sum`) terms silently drop out-of-range
summands (a windowed sum), which is normal.

---

## 3. End-to-end validation

The runner `corpus/validation/codec_pipeline/run.py` executes the full
loop for every instance in `instances/`:

```
formulation JSON --latex--> LaTeX --parse--> model --ground+solve--> objective
```

and checks: (1) codec round-trip, (2) **pipeline-solve == direct-solve**,
(3) **cross-solver agreement** (CBC/HiGHS/Gurobi), (4) the objective equals
an **independently established optimum**.

| Case | Model class | Optimum | Source of the reference |
|------|-------------|--------:|-------------------------|
| `assignment_4x4` | assignment / matching | 13 | brute-force min-cost matching over all 4! permutations |
| `bigm_ordering_4` | big-M disjunctive ordering | 30 | closed form (0+5+10+15) |
| `fixed_sequence_4` | sequential timetabling LP | 18 | closed form (0+3+6+9) |
| `pesp_2events` | PESP cyclic timetabling | 1 | closed form (exactly one arc must wrap) |
| `time_indexed_4x4` | time-indexed set packing | 4 | closed form (one slot per train) |

All five pass every check.

### Paper-anchored references

The request was to validate by reproducing a paper's objective value. The
canonical template grammar fits *template-structured* models (PESP,
assignment, time-indexed, big-M ordering, set packing/covering). For those
the pipeline reproduces independently-verified optima exactly. The sibling
harness `run_experiments.py` additionally proves published / benchmark
optima for corpus models of the same structural classes the pipeline
handles:

- **timtab1 = 764772** — the IBM/CPLEX `timtab1` MIPLIB cyclic-timetabling
  instance (a PESP — exactly the class of `pesp_solvable.json`),
  cross-solver proven.
- **marcotallone maintenance scheduling = 3913.47** — Gurobi/HiGHS/CBC
  agreement at tight tolerance (a big-M time-indexed model — the class of
  `mip_2_1_big_m` / `mip_2_4`).

Models that the canonical grammar does **not** yet cover are documented
honestly: e.g. Gurobi's `railway-dispatching-mip` (optimum 47) uses
per-train variable-length routes `R_i` and a derived "next resource",
which the regular-index-family template grammar cannot express. Extending
the grammar to such structures is future work.

---

## 4. Quick start

```bash
# graph -> paper LaTeX, and back
lp2graph latex   formulations/constraints/pesp_solvable.json --output pesp.tex
lp2graph parse   pesp.tex                                                  # -> JSON

# ground with data and solve
lp2graph solve   formulations/constraints/assignment.json \
                 --instance corpus/validation/codec_pipeline/instances/assignment_4x4.json

# graph -> natural-language problem description (+ data tables with --instance)
lp2graph describe formulations/constraints/pesp_solvable.json \
                 --instance corpus/validation/codec_pipeline/instances/pesp_2events.json
```

In Python:

```python
from lp2graph import load, to_canonical_latex, from_canonical_latex, describe
from lp2graph.solve import Instance, solve

f = load("formulations/constraints/assignment.json")
tex = to_canonical_latex(f)            # graph -> text
g   = from_canonical_latex(tex)        # text -> graph  (g ≅ f)
inst = Instance(cardinalities={"W": 4, "J": 4}, parameters={"c": [...]})
print(solve(g, inst).objective)        # graph -> MILP -> solve
print(describe(f, inst))               # graph -> prose + data tables
```
