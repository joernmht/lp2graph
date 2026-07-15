# Code ⇄ graph interop

`lp2graph.interop` converts between solver/modeling languages and the
canonical `Formulation` — the typed graph's single source of truth.
Because every importer and every exporter meets in the same canonical
model, **any importer composes with any exporter**: `code → graph →
code`, with no LaTeX step in between.

| Language | code → graph | graph → code | Verified by |
|---|---|---|---|
| Gurobi (`gurobipy`) | `from_gurobipy(model)` | `to_gurobipy(f)` (live model), `to_gurobipy_code(f)` (script) | solved with Gurobi |
| PuLP | `from_pulp(problem)` | `to_pulp(f)` (live problem), `to_pulp_code(f)` (script) | solved with CBC |
| Pyomo | `from_pyomo(model)` | `to_pyomo(f)` (live model), `to_pyomo_code(f)` (script) | solved with HiGHS |
| CPLEX/Gurobi LP file | `from_lp_string(text)` | `to_lp_string(f)` | cross-read with Gurobi |
| MPS file | `from_mps_string(text)` | `to_mps_string(f)` | cross-read with Gurobi |
| GAMS (scalar) | `from_gams(text)` | `to_gams(f)` | round-trip + external sources |
| AMPL (scalar, `.mod`) | `from_ampl(text)` | `to_ampl(f)` | round-trip + external sources |
| JuMP (scalar, `.jl`) | `from_jump(text)` | `to_jump(f)` | round-trip + external sources |

All conversions are **coefficient-faithful**: the test matrix
(`tests/interop/`) round-trips models with hand-verified optima through
every format and requires the re-imported model to solve to the same
objective (CBC, HiGHS, and Gurobi cross-checks). Unsupported constructs
(quadratic/SOS/indicator content, indexed GAMS/AMPL/JuMP, MPS `RANGES`)
raise `InteropError` — nothing is dropped silently. Every emitter is
deterministic and a fixpoint under its own parser.

## Quick start

```python
from lp2graph.interop import from_gurobipy, to_gams, to_pulp

f = from_gurobipy(model)         # gurobipy.Model -> canonical Formulation
print(to_gams(f))                # -> runnable scalar GAMS program
prob = to_pulp(f)                # -> pulp.LpProblem
prob.solve()                     # solve it with CBC
```

Or from the command line, routed by file extension:

```bash
lp2graph convert model.lp model.gms          # LP file -> GAMS
lp2graph convert model.gms model.py          # GAMS -> PuLP script (default)
lp2graph convert model.mps model.py --python-api gurobipy
lp2graph convert model.json model.jl --instance data.json   # template -> JuMP
```

## Two levels of model, one hub

Importers return **flat** formulations: scalar variables, unquantified
constraints, numeric coefficients — exactly what a built solver model
contains. Flat formulations ground directly (no dependencies) and solve
via `lp2graph.solve`.

Exporters accept flat formulations as-is and **template-level**
formulations (index families, quantifiers, `sum` terms, parameter
coefficients) together with an `Instance`; the PuLP grounder
materializes the template before emission.

Internally both directions meet in `GroundedModel`, the flat numeric
interchange struct: importers produce it, `to_formulation` promotes it
to a validated canonical model, and `ground` lowers any formulation
back onto it.

## Boundaries

- The three Python APIs (`gurobipy` / `pulp` / `pyomo`) are optional
  dependencies, imported lazily inside the functions that need them.
  The five text formats are dependency-free for flat models.
- Importing from `.py` *source* is out of scope by design (it would
  mean executing arbitrary code); build the model object and pass it to
  `from_gurobipy` / `from_pulp` / `from_pyomo`. The
  `mining.ingest.ingest()` dispatcher reports `.py` as unsupported and
  routes `.gms/.mod/.jl/.lp/.mps` to these parsers.
- GAMS/AMPL/JuMP parsing covers the *scalar linear* subset (the shape
  the emitters write, plus common hand-written variants). Set-indexed
  source models are honestly rejected, not partially parsed.
- `lp2graph.interop.from_pyomo` is the coefficient-faithful, solvable
  importer; the structural M1a importer
  `lp2graph.mining.ingest.from_pyomo` (template shell, no coefficients)
  still exists for mining statistics.
