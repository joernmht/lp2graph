"""First-class, named solver selection for the grounding back-end.

The grounder (:mod:`lp2graph.solve.grounder`) builds a *solver-neutral* pulp
model; this module turns a solver **name** into a configured
``pulp.LpSolver``. It exists so the library itself — not just the validation
harness — offers a CBC / HiGHS / Gurobi grounding back-end: callers can
``solve(f, inst, solver="highs")`` without hand-constructing a pulp object or
knowing pulp's class names.

The three back-ends ride on pulp's solver interfaces: CBC via the bundled
``PULP_CBC_CMD``, HiGHS via ``pulp.HiGHS`` (highspy), and Gurobi via
``pulp.GUROBI`` (gurobipy). Each is an **optional** runtime dependency; HiGHS
and Gurobi are only imported by pulp when their back-end is actually
requested, so importing this module never requires them.

Defaults are deterministic — single-thread, no time limit, zero target gap —
matching the cross-solver agreement validation in ``corpus/validation``.
Determinism is a hard requirement of this package; do not change the
single-thread default.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # pulp has no stubs and is an optional dep — type-only import
    import pulp

SolverName = Literal["cbc", "highs", "gurobi"]

#: Solver names this library can build, in deterministic preference order.
SOLVER_NAMES: tuple[SolverName, ...] = ("cbc", "highs", "gurobi")

#: Map each solver name to the pulp class that implements it.
_PULP_CLASS: dict[SolverName, str] = {
    "cbc": "PULP_CBC_CMD",
    "highs": "HiGHS",
    "gurobi": "GUROBI",
}


def make_solver(
    name: str,
    *,
    msg: bool = False,
    threads: int = 1,
    time_limit: float | None = None,
    gap_rel: float | None = None,
) -> pulp.LpSolver:
    """Build a configured ``pulp.LpSolver`` for ``name``.

    ``name`` is one of :data:`SOLVER_NAMES` (case-insensitive). Defaults are
    deterministic: a single thread (where the back-end forwards it reliably —
    see the HiGHS note below), no time limit, and the solver's own default
    gap. Pass ``gap_rel=0.0`` for a proven optimum (the ``tight`` setting the
    validation harness uses for cross-solver agreement).

    Raises :class:`ValueError` for an unknown name. The chosen solver's
    optional dependency (highspy / gurobipy) is imported lazily by pulp only
    when that back-end is requested.
    """
    import pulp

    key = name.lower()
    if key == "cbc":
        opts: dict[str, object] = {"msg": msg, "threads": threads}
        if time_limit is not None:
            opts["timeLimit"] = time_limit
        if gap_rel is not None:
            opts["gapRel"] = gap_rel
        return pulp.PULP_CBC_CMD(**opts)
    if key == "highs":
        # NB: do not forward ``threads`` to pulp.HiGHS. With the pinned
        # pulp/highspy, setting the HiGHS ``threads`` option on the
        # incrementally-built model mis-solves some MILPs (returns a spurious
        # 0.0 incumbent), and HiGHS' parallel MILP path is itself nondeterm-
        # inistic across thread counts. Left at the default, HiGHS solves to
        # the correct, reproducible optimum — which is what determinism here
        # requires (the proven optimum is thread-count independent).
        return pulp.HiGHS(msg=msg, timeLimit=time_limit, gapRel=gap_rel)
    if key == "gurobi":
        # Gurobi takes per-engine parameters (e.g. Threads) as solverParams.
        return pulp.GUROBI(msg=msg, timeLimit=time_limit, gapRel=gap_rel, Threads=threads)
    raise ValueError(f"unknown solver {name!r}; choose one of {', '.join(SOLVER_NAMES)}")


def available_solvers() -> tuple[SolverName, ...]:
    """Return the subset of :data:`SOLVER_NAMES` actually installed here.

    CBC ships with pulp and is always present; HiGHS and Gurobi depend on
    their optional packages (and, for Gurobi, a valid license).
    """
    import pulp

    installed = set(pulp.listSolvers(onlyAvailable=True))
    return tuple(n for n in SOLVER_NAMES if _PULP_CLASS[n] in installed)


__all__ = ["SOLVER_NAMES", "SolverName", "available_solvers", "make_solver"]
