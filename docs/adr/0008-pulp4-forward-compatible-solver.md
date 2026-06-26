# ADR-0008: Forward-compatible PuLP API in the solver back-end

- **Status:** accepted
- **Date:** 2026-06-26

## Context

The grounding back-end (`solve/grounder.py`) builds and solves models with
PuLP. PuLP 4.0 deprecates three APIs the back-end relied on, each emitting a
`DeprecationWarning` and slated for removal:

1. **Direct `LpVariable(name, ...)` construction** — PuLP 4.0 wants variables
   created through `prob.add_variable(name, lowBound, upBound, cat=...)`, which
   attaches them to the model at creation.
2. **`PULP_CBC_CMD`** — the bundled CBC moves to the `pulp[cbc]` extra and the
   solver class is renamed `COIN_CMD`.
3. **`LpProblem.constraints` as a dict mapping** — `len(prob.constraints)`
   triggers a mapping-deprecation; PuLP 4.0 returns constraints as a list.

Left unmigrated, the entire `solve/` path breaks the day PuLP 4.0 is installed.
The back-end is the only executable boundary in an otherwise pure/deterministic
library, so a silent runtime break there is a real reliability risk. The
constraint was to migrate **without** breaking the currently-installed PuLP 3.x,
and **without** disturbing determinism or `SolveResult` values.

## Decision

**Use only PuLP APIs that exist in PuLP 3.x *and* are the sanctioned PuLP 4.0
form**, and centralise the CBC default behind one helper:

1. Build variables with `prob.add_variable(...)`. Verified: `prob.variables()`
   still returns only variables that appear in the objective/constraints, so
   `n_vars` and the emitted model are unchanged for models with unused
   variables.
2. Count constraints with `prob.numConstraints()` instead of
   `len(prob.constraints)`, avoiding the deprecated mapping access.
3. Add `solve.default_solver(msg=False)`, returning a `COIN_CMD` instance.
   `COIN_CMD` does not auto-discover PuLP's bundled CBC on 3.x, so when it
   reports `available()` falsy we fall back to the bundled binary path read from
   the **`PULP_CBC_CMD.pulp_cbc_path` class attribute** — accessed without
   instantiating the deprecated solver, so no warning is emitted. Under PuLP 4.0
   with `pulp[cbc]`, `COIN_CMD` finds CBC itself and the fallback is unused.
   `grounder.solve()` and the CLI `solve --solver cbc` path both route through
   this helper.

A regression test (`tests/test_solve.py::test_solve_path_is_pulp4_clean`) runs a
real solve with `DeprecationWarning` from `pulp.*` promoted to an error, so any
reintroduced deprecated call fails CI.

## Rationale

- One code path works on both PuLP 3.x (today's pin) and 4.0 (the next major),
  so the upgrade is a no-op rather than a breaking event.
- The default solver lives in exactly one place (`default_solver`), reused by
  the library and the CLI, instead of being duplicated as inline lambdas.
- Determinism preserved: single-threaded CBC, identical objective / `n_vars` /
  `n_constraints` / variable values verified across repeated solves and against
  the known-optimum and cross-solver (CBC vs HiGHS) tests.

## Consequences

- The default solver name reported in `SolveResult.solver` changes from
  `PULP_CBC_CMD` to `COIN_CMD`. No code or test asserts that string, but
  downstream consumers reading it should expect the new value.
- The bundled-CBC fallback depends on `PULP_CBC_CMD.pulp_cbc_path` existing on
  PuLP 3.x; if a future PuLP removes that class attribute *and* `pulp[cbc]` is
  not installed, `default_solver()` returns an unavailable solver and `solve()`
  raises a clear `PulpSolverError` — the documented "install CBC" failure, not a
  silent wrong answer.
- The PuLP floor stays `pulp>=2.8`; bumping past 3.x no longer requires code
  changes.

## Alternatives considered

- *Suppress the warnings with a `warnings.filter`:* rejected — hides the problem
  instead of fixing it; the code would still break under PuLP 4.0.
- *Pin `pulp<4`:* rejected — defers the break and freezes the solver stack; the
  forward-compatible APIs already exist in 3.x, so migration is strictly better.
- *Keep `PULP_CBC_CMD` and read its `.path` from an instance:* rejected —
  instantiating it emits the very deprecation we are removing; the class
  attribute gives the same path without construction.
