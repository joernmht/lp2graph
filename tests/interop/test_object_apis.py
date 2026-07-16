"""Live-object interfaces: gurobipy, PuLP, Pyomo — both directions.

Every path is verified by solving: import a natively-built model into
the graph and solve it with CBC; export the graph back to a live model
(or generated code, which is executed) and solve it with the target
API's own solver. All assertions are against hand-verified optima.
"""

from __future__ import annotations

import _models
import pytest

from lp2graph.interop import (
    InteropError,
    from_gurobipy,
    from_pulp,
    from_pyomo,
    to_gurobipy,
    to_gurobipy_code,
    to_pulp,
    to_pulp_code,
    to_pyomo,
    to_pyomo_code,
)


def _default_solver():
    from lp2graph.solve import default_solver

    return default_solver()


# ---------------------------------------------------------------------------
# gurobipy
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def genv():
    gp = pytest.importorskip("gurobipy")
    try:
        env = gp.Env(params={"OutputFlag": 0})
    except gp.GurobiError as exc:  # pragma: no cover - no license on this host
        pytest.skip(f"gurobi environment unavailable: {exc}")
    yield env
    env.dispose()


def _native_gurobi_freight(gp, genv):
    m = gp.Model("express_freight", env=genv)
    x1 = m.addVar(name="x1")
    x2 = m.addVar(name="x2")
    y = m.addVar(vtype=gp.GRB.BINARY, name="y")
    m.setObjective(4 * x1 + 10 * x2 - 12 * y, gp.GRB.MAXIMIZE)
    m.addConstr(2 * x1 + 3 * x2 <= 18, name="hours")
    m.addConstr(x2 <= 5 * y, name="link")
    return m


def test_gurobipy_to_graph_solves_with_cbc(genv):
    gp = pytest.importorskip("gurobipy")
    f = from_gurobipy(_native_gurobi_freight(gp, genv))
    assert f.family == "milp"
    assert [v.name for v in f.variables] == ["x1", "x2", "y"]
    assert _models.solve_cbc(f) == pytest.approx(44.0)


def test_graph_to_gurobipy_solves(known_model, genv):
    f, optimum = known_model
    m = to_gurobipy(f, env=genv)
    m.optimize()
    assert m.Status == 2  # GRB.OPTIMAL
    assert m.ObjVal == pytest.approx(optimum)


def test_graph_to_gurobipy_code_executes_and_solves(known_model, genv):
    f, optimum = known_model
    code = to_gurobipy_code(f)
    assert to_gurobipy_code(f) == code  # deterministic
    ns: dict = {}
    exec(compile(code, "<generated gurobipy>", "exec"), ns)
    m = ns["build_model"](env=genv)
    m.optimize()
    assert m.ObjVal == pytest.approx(optimum)


def test_gurobi_written_files_parse_back(genv, tmp_path):
    """Cross-check: Gurobi's own .lp/.mps writers -> our parsers -> CBC."""
    gp = pytest.importorskip("gurobipy")
    from lp2graph.interop import from_lp_string, from_mps_string

    m = _native_gurobi_freight(gp, genv)
    m.update()
    lp_path, mps_path = tmp_path / "m.lp", tmp_path / "m.mps"
    m.write(str(lp_path))
    m.write(str(mps_path))
    for parse, path in ((from_lp_string, lp_path), (from_mps_string, mps_path)):
        g = parse(path.read_text(encoding="utf-8"))
        assert _models.solve_cbc(g) == pytest.approx(44.0)


def test_our_mps_reads_back_into_gurobi(genv, tmp_path):
    """Cross-check the other way: our MPS writer -> Gurobi's reader."""
    gp = pytest.importorskip("gurobipy")
    from lp2graph.interop import to_mps_string

    f, optimum = _models.express_freight(), 44.0
    path = tmp_path / "ours.mps"
    path.write_text(to_mps_string(f), encoding="utf-8")
    m = gp.read(str(path), env=genv)
    m.optimize()
    assert m.ObjVal == pytest.approx(optimum)


def test_gurobipy_quadratic_objective_raises(genv):
    gp = pytest.importorskip("gurobipy")
    m = gp.Model("quad", env=genv)
    x = m.addVar(name="x")
    m.setObjective(x * x)
    m.update()
    with pytest.raises(InteropError, match="non-linear objective"):
        from_gurobipy(m)


# ---------------------------------------------------------------------------
# PuLP
# ---------------------------------------------------------------------------


def test_pulp_to_graph_and_back():
    pulp = pytest.importorskip("pulp")
    prob = pulp.LpProblem("express_freight", pulp.LpMaximize)
    x1 = pulp.LpVariable("x1", lowBound=0)
    x2 = pulp.LpVariable("x2", lowBound=0)
    y = pulp.LpVariable("y", cat="Binary")
    prob += 4 * x1 + 10 * x2 - 12 * y, "objective"
    prob += 2 * x1 + 3 * x2 <= 18, "hours"
    prob += x2 <= 5 * y, "link"

    f = from_pulp(prob)
    assert f.family == "milp"
    assert _models.solve_cbc(f) == pytest.approx(44.0)

    prob2 = to_pulp(f)
    prob2.solve(_default_solver())
    assert pulp.value(prob2.objective) == pytest.approx(44.0)


def test_graph_to_pulp_code_executes_and_solves(known_model):
    pulp = pytest.importorskip("pulp")
    f, optimum = known_model
    code = to_pulp_code(f)
    assert to_pulp_code(f) == code  # deterministic
    ns: dict = {}
    exec(compile(code, "<generated pulp>", "exec"), ns)
    prob = ns["build_problem"]()
    prob.solve(_default_solver())
    assert pulp.value(prob.objective) == pytest.approx(optimum)


# ---------------------------------------------------------------------------
# Pyomo
# ---------------------------------------------------------------------------


def _native_pyomo_freight(pyo):
    m = pyo.ConcreteModel(name="express_freight")
    m.x1 = pyo.Var(domain=pyo.NonNegativeReals)
    m.x2 = pyo.Var(domain=pyo.NonNegativeReals)
    m.y = pyo.Var(domain=pyo.Binary)
    m.obj = pyo.Objective(expr=4 * m.x1 + 10 * m.x2 - 12 * m.y, sense=pyo.maximize)
    m.hours = pyo.Constraint(expr=2 * m.x1 + 3 * m.x2 <= 18)
    m.link = pyo.Constraint(expr=m.x2 - 5 * m.y <= 0)
    return m


def test_pyomo_to_graph_is_coefficient_faithful():
    pyo = pytest.importorskip("pyomo.environ")
    f = from_pyomo(_native_pyomo_freight(pyo))
    assert f.family == "milp"
    hours = f.constraint_map()["hours"]
    coefs = {t.ref: float(t.coefficient) * t.sign for t in hours.lhs}
    assert coefs == {"x1": 2.0, "x2": 3.0}
    assert _models.solve_cbc(f) == pytest.approx(44.0)


def test_pyomo_ranged_constraint_splits():
    pyo = pytest.importorskip("pyomo.environ")
    m = pyo.ConcreteModel(name="ranged")
    m.x = pyo.Var(domain=pyo.NonNegativeReals)
    m.obj = pyo.Objective(expr=m.x, sense=pyo.minimize)
    m.window = pyo.Constraint(expr=(2, m.x, 8))
    f = from_pyomo(m)
    assert {c.name for c in f.constraints} == {"window_lo", "window_up"}
    assert _models.solve_cbc(f) == pytest.approx(2.0)


def test_pyomo_nonlinear_raises():
    pyo = pytest.importorskip("pyomo.environ")
    m = pyo.ConcreteModel(name="nl")
    m.x = pyo.Var(domain=pyo.NonNegativeReals)
    m.obj = pyo.Objective(expr=m.x * m.x)
    with pytest.raises(InteropError, match="nonlinear"):
        from_pyomo(m)


def _pyomo_solver(pyo):
    for name in ("appsi_highs", "highs", "cbc", "glpk"):
        solver = pyo.SolverFactory(name)
        try:
            if solver.available(exception_flag=False):
                return solver
        except Exception:
            continue
    return None


def test_graph_to_pyomo_solves(known_model):
    pyo = pytest.importorskip("pyomo.environ")
    solver = _pyomo_solver(pyo)
    if solver is None:
        pytest.skip("no LP/MILP solver available to Pyomo")
    f, optimum = known_model
    m = to_pyomo(f)
    solver.solve(m)
    assert pyo.value(m.obj) == pytest.approx(optimum)


def test_graph_to_pyomo_code_executes_and_solves(known_model):
    pyo = pytest.importorskip("pyomo.environ")
    solver = _pyomo_solver(pyo)
    if solver is None:
        pytest.skip("no LP/MILP solver available to Pyomo")
    f, optimum = known_model
    code = to_pyomo_code(f)
    assert to_pyomo_code(f) == code  # deterministic
    ns: dict = {}
    exec(compile(code, "<generated pyomo>", "exec"), ns)
    m = ns["build_model"]()
    solver.solve(m)
    assert pyo.value(m.obj) == pytest.approx(optimum)


# ---------------------------------------------------------------------------
# Cross-language chains (code -> graph -> code across APIs)
# ---------------------------------------------------------------------------


def test_pyomo_to_gurobi_chain(genv):
    pyo = pytest.importorskip("pyomo.environ")
    pytest.importorskip("gurobipy")
    f = from_pyomo(_native_pyomo_freight(pyo))
    m = to_gurobipy(f, env=genv)
    m.optimize()
    assert m.ObjVal == pytest.approx(44.0)


def test_gurobi_to_jump_text_chain(genv):
    gp = pytest.importorskip("gurobipy")
    from lp2graph.interop import from_jump, to_jump

    f = from_gurobipy(_native_gurobi_freight(gp, genv))
    julia = to_jump(f)
    g = from_jump(julia)
    assert _models.solve_cbc(g) == pytest.approx(44.0)
