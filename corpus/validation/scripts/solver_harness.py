#!/usr/bin/env python3
"""Solve a portable model file (.mps / .lp) with three independent solvers and
report the optimal objective from each. Used for two validations:

  (A) cross-solver agreement on a dialect-neutral interchange file (MPS/LP);
  (B) round-trip translation fidelity (a model emitted from one tool, re-solved
      by others).

Solvers: Gurobi (commercial, WLS license), HiGHS (open source), CBC (open
source, via PuLP). Deterministic single-thread settings where available.
Requires: PYTHONPATH including the bundled .deps, and GRB_LICENSE_FILE set.
"""
from __future__ import annotations
import time, math, sys


TIME_LIMIT = 120  # seconds per solver; keeps the suite "not too intensive"


def solve_gurobi(path, tl=TIME_LIMIT, tight=False):
    import gurobipy as gp
    t = time.perf_counter()
    m = gp.read(path)
    m.Params.OutputFlag = 0
    m.Params.Threads = 1
    m.Params.TimeLimit = tl
    if tight:
        m.Params.MIPGap = 0.0
        m.Params.FeasibilityTol = 1e-9
        m.Params.IntFeasTol = 1e-9
    m.optimize()
    dt = time.perf_counter() - t
    st = {2: "optimal", 3: "infeasible", 5: "unbounded", 9: "time_limit"}.get(m.Status, f"status_{m.Status}")
    obj = m.ObjVal if m.SolCount > 0 else None
    bound = m.ObjBound if m.SolCount >= 0 else None
    return {"solver": f"gurobi-{gp.gurobi.version()[0]}.{gp.gurobi.version()[1]}",
            "status": st, "objective": obj, "best_bound": round(bound, 4) if bound is not None else None,
            "mip_gap": round(m.MIPGap, 6) if m.SolCount > 0 else None,
            "runtime_s": round(dt, 4),
            "n_vars": m.NumVars, "n_constrs": m.NumConstrs, "n_int": m.NumIntVars}


def solve_highs(path, tl=TIME_LIMIT, tight=False):
    import highspy
    t = time.perf_counter()
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("threads", 1)
    h.setOptionValue("time_limit", float(tl))
    if tight:
        h.setOptionValue("mip_rel_gap", 0.0)
        h.setOptionValue("mip_feasibility_tolerance", 1e-9)
        h.setOptionValue("primal_feasibility_tolerance", 1e-9)
    h.readModel(path)
    h.run()
    dt = time.perf_counter() - t
    status = h.modelStatusToString(h.getModelStatus()).lower()
    info = h.getInfo()
    obj = info.objective_function_value if status in ("optimal", "time limit") else None
    return {"solver": f"highs-{highspy.Highs().version()}", "status": status,
            "objective": obj, "runtime_s": round(dt, 4),
            "n_vars": h.getNumCol(), "n_constrs": h.getNumRow()}


def solve_cbc(path, tl=TIME_LIMIT, tight=False):
    import pulp
    t = time.perf_counter()
    if path.lower().endswith(".mps"):
        _, prob = pulp.LpProblem.fromMPS(path)
    else:  # .lp
        raise NotImplementedError("CBC path-reader only supports MPS here")
    opts = ["ratio", "0"] if tight else []  # CBC: target 0% optimality gap
    prob.solve(pulp.PULP_CBC_CMD(msg=0, threads=1, timeLimit=tl, options=opts))
    dt = time.perf_counter() - t
    status = pulp.LpStatus[prob.status].lower()
    obj = pulp.value(prob.objective)
    return {"solver": f"cbc-pulp-{pulp.__version__}", "status": status,
            "objective": obj, "runtime_s": round(dt, 4),
            "n_vars": len(prob.variables()), "n_constrs": len(prob.constraints)}


SOLVERS = {"gurobi": solve_gurobi, "highs": solve_highs, "cbc": solve_cbc}


def solve_all(path, which=("gurobi", "highs", "cbc"), tl=TIME_LIMIT, tight=False):
    out = []
    for name in which:
        try:
            out.append(SOLVERS[name](path, tl=tl, tight=tight))
        except Exception as e:  # noqa: BLE001 - record, do not crash the batch
            out.append({"solver": name, "status": "error", "objective": None,
                        "error": f"{type(e).__name__}: {e}"})
    return out


def agree(results, rtol=1e-6, atol=1e-4):
    vals = [r["objective"] for r in results if r.get("objective") is not None]
    if len(vals) < 2:
        return None
    return all(math.isclose(v, vals[0], rel_tol=rtol, abs_tol=atol) for v in vals)


if __name__ == "__main__":
    import json
    for p in sys.argv[1:]:
        res = solve_all(p)
        print(json.dumps({"file": p, "agree": agree(res), "results": res}, indent=2))
