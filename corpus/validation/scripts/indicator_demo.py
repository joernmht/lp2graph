#!/usr/bin/env python3
"""Demonstrate that the deterministic indicator->big-M transform is correct and
that solvers WITHOUT native indicator support still get a valid model.

Toy problem (max):   maximize  x - 5*y
                     s.t.       if y = 1 then x <= 3        (indicator)
                                0 <= x <= 10,  y in {0,1}

The unconstrained max is x=10,y=0 -> 10. Turning the indicator on costs 5 but
caps x at 3 -> 3-5 = -2, so the optimum is 10 with y=0. We solve three ways:

  1. Gurobi with a NATIVE indicator constraint (addGenConstrIndicator) - exact.
  2. HiGHS and CBC with the big-M form emitted by lp2graph.transform.bigm,
     using the TIGHT M computed from bounds (M = max(x)-3 = 7).
  3. The same big-M form with a needlessly large M = 1e5, for comparison.

All of (1) and (2) report the same optimum, demonstrating that solvers without
native indicator support still receive a valid, equivalent model. (The big-M
*tolerance trap* itself - where a loose M plus a loose feasibility tolerance
yields a spurious optimum - is documented concretely with real data in the
marcotallone experiment of validation_results.json; it manifests only when the
gated constraint is active at the optimum under default tolerances.)
"""
from __future__ import annotations
import os, sys, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
VAL = HERE.parent
sys.path.insert(0, str(VAL / ".deps"))
sys.path.insert(0, str(VAL.parent.parent / "src"))   # lp2graph
os.environ.setdefault("GRB_LICENSE_FILE", "/home/joern/gurobi.lic")

from lp2graph.transform import Bounds, IndicatorConstraint, LinearConstraint, to_big_m

IND = IndicatorConstraint("y", 1, LinearConstraint({"x": 1.0}, "le", 3.0))
BOUNDS = {"x": Bounds(0.0, 10.0)}
OBJ = {"x": 1.0, "y": -5.0}  # maximize


def gurobi_native():
    import gurobipy as gp
    from gurobipy import GRB
    m = gp.Model(); m.Params.OutputFlag = 0
    x = m.addVar(lb=0, ub=10, name="x"); y = m.addVar(vtype=GRB.BINARY, name="y")
    m.addGenConstrIndicator(y, True, x <= 3.0)        # native indicator
    m.setObjective(x - 5 * y, GRB.MAXIMIZE); m.optimize()
    return {"encoding": "native indicator (Gurobi)", "obj": round(m.ObjVal, 6),
            "x": round(x.X, 6), "y": round(y.X, 6)}


def _solve_big_m_with_highs(lc, M):
    import highspy
    h = highspy.Highs(); h.setOptionValue("output_flag", False)
    h.setOptionValue("mip_feasibility_tolerance", 1e-9)
    # vars: x in [0,10], y in {0,1}; maximize x - 5y  (HiGHS minimizes -> negate)
    inf = highspy.kHighsInf
    h.addVar(0.0, 10.0); h.addVar(0.0, 1.0)
    h.changeColIntegrality(1, highspy.HighsVarType.kInteger)
    h.changeColsCost(2, [0, 1], [-1.0, 5.0])
    # row: x_coeff*x + y_coeff*y <= rhs
    idx = [0, 1]; vals = [lc.coeffs.get("x", 0.0), lc.coeffs.get("y", 0.0)]
    h.addRow(-inf, lc.rhs, 2, idx, vals)
    h.run()
    sol = h.getSolution()
    return {"obj": round(-h.getInfo().objective_function_value, 6),
            "x": round(sol.col_value[0], 6), "y": round(sol.col_value[1], 6)}


def _solve_big_m_with_cbc(lc, M):
    import pulp
    p = pulp.LpProblem("d", pulp.LpMaximize)
    x = pulp.LpVariable("x", 0, 10); y = pulp.LpVariable("y", cat="Binary")
    p += x - 5 * y
    p += lc.coeffs.get("x", 0.0) * x + lc.coeffs.get("y", 0.0) * y <= lc.rhs
    p.solve(pulp.PULP_CBC_CMD(msg=0))
    return {"obj": round(pulp.value(p.objective), 6),
            "x": round(x.value(), 6), "y": round(y.value(), 6)}


def main():
    (lc_tight,) = to_big_m(IND, BOUNDS)             # M = 7 (deterministic)
    (lc_loose,) = to_big_m(IND, m=1e5)              # explicit oversized M
    M_tight = lc_tight.coeffs["y"]                  # = 7.0
    out = {
        "deterministic_M": M_tight,
        "big_m_row_tight": lc_tight.pretty(),
        "results": {
            "gurobi_native_indicator": gurobi_native(),
            "highs_big_m_tight(M=%g)" % M_tight: _solve_big_m_with_highs(lc_tight, M_tight),
            "cbc_big_m_tight(M=%g)" % M_tight: _solve_big_m_with_cbc(lc_tight, M_tight),
            "highs_big_m_loose(M=1e5)": _solve_big_m_with_highs(lc_loose, 1e5),
        },
    }
    objs = [r["obj"] for k, r in out["results"].items() if "loose" not in k]
    out["all_exact_encodings_agree"] = max(objs) - min(objs) < 1e-4
    out["expected_optimum"] = 10.0
    path = VAL / "results" / "indicator_demo.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print("\nwrote", path)


if __name__ == "__main__":
    main()
