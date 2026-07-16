"""Tests for the grounding solver back-end and the full text->solve pipeline."""

from __future__ import annotations

import json
import math

import pytest

from lp2graph import from_canonical_latex, load, to_canonical_latex

pulp = pytest.importorskip("pulp")
from lp2graph.solve import Instance, solve  # noqa: E402


def _spec(path):
    data = json.loads(path.read_text())
    f = load(path.parents[4] / data["formulation"])
    inst = Instance(cardinalities=data["cardinalities"], parameters=data["parameters"])
    return f, inst, data["expected_optimum"]


def test_matches_known_optimum(instance_files):
    for ip in instance_files:
        f, inst, expected = _spec(ip)
        obj = solve(f, inst).objective
        assert obj is not None and math.isclose(obj, expected, abs_tol=1e-4), ip.name


def test_pipeline_equals_direct(instance_files):
    """Solving the model reconstructed from LaTeX equals solving the JSON."""
    for ip in instance_files:
        f, inst, _ = _spec(ip)
        g = from_canonical_latex(to_canonical_latex(f))
        assert math.isclose(solve(f, inst).objective, solve(g, inst).objective, abs_tol=1e-6), (
            ip.name
        )


def test_cross_solver_agreement(instance_files):
    f, inst, expected = _spec(next(p for p in instance_files if p.stem == "assignment_4x4"))
    cbc = solve(f, inst, solver=pulp.PULP_CBC_CMD(msg=0, threads=1)).objective
    highs = solve(f, inst, solver=pulp.HiGHS(msg=False)).objective
    assert math.isclose(cbc, highs, abs_tol=1e-6)
    assert math.isclose(cbc, expected, abs_tol=1e-4)


def test_make_solver_and_solve_by_name(instance_files):
    """The library exposes the CBC/HiGHS/Gurobi back-end by name, and
    `solve()` accepts a solver name string — agreeing across installed
    back-ends."""
    from lp2graph.solve import available_solvers, make_solver

    assert "cbc" in available_solvers()  # CBC ships with pulp
    assert isinstance(make_solver("highs"), pulp.LpSolver)

    f, inst, expected = _spec(next(p for p in instance_files if p.stem == "assignment_4x4"))
    objs = [solve(f, inst, solver=name).objective for name in available_solvers()]
    assert all(math.isclose(o, expected, abs_tol=1e-4) for o in objs)
    assert all(math.isclose(o, objs[0], abs_tol=1e-6) for o in objs)


def test_make_solver_rejects_unknown():
    from lp2graph.solve import make_solver

    with pytest.raises(ValueError, match="unknown solver"):
        make_solver("clp")


def test_offset_constraints_skipped_at_boundary():
    """A `t_{i-1}` term at i=0 must drop the whole headway instance, not
    degrade it to `t_0 >= h`."""
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    inst = Instance(
        cardinalities={"I": 3}, parameters={"h": 2, "r": [1, 1, 1], "earliest": [0, 0, 0]}
    )
    res = solve(f, inst)
    assert math.isclose(res.objective, 6.0, abs_tol=1e-6)  # 0 + 2 + 4


def test_unsupported_operator_raises():
    from lp2graph.solve import UnsupportedModel

    f = load("formulations/objectives/objective_abs_deviation.json")
    with pytest.raises(UnsupportedModel):
        solve(f, Instance(cardinalities={"I": 2}, parameters={"target": [0, 0]}))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
