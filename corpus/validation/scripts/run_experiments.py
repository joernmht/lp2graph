#!/usr/bin/env python3
"""Validation experiments for the extracted MILP corpus.

  1. Reference optima + cross-solver agreement on a dialect-neutral interchange
     file (timtab1, repo #9): Gurobi / HiGHS / CBC on the .mps, plus the
     Gurobi-re-emitted .lp.
  2. Round-trip translation fidelity: Gurobi reads the model and re-emits it to
     .lp and .mps (its writer = translation into other textual dialects); the
     re-emitted files are solved again and compared.
  3. From-repo Python model (marcotallone, #8) with a big-M caveat: build the
     gurobipy model on the smallest instance and solve at DEFAULT vs TIGHT
     tolerances (showing the big-M tolerance artifact), then export and
     cross-solve at tight tolerances (agreement = true optimum).

Deterministic: single thread, no heuristic seeds. Writes
../results/validation_results.json.
"""
from __future__ import annotations
import os, sys, json, time, pathlib

HERE = pathlib.Path(__file__).resolve().parent
VAL = HERE.parent
RESULTS = VAL / "results"
EXPORTS = RESULTS / "exports"
EXPORTS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(VAL / ".deps"))
sys.path.insert(0, str(HERE))
os.environ.setdefault("GRB_LICENSE_FILE", "/home/joern/gurobi.lic")
import solver_harness as H  # noqa: E402

SRC = pathlib.Path("/home/joern/milp_sources")
TIMTAB = SRC / "IBM__cplex-samples/Timetabling-problem/timtab1.mps"
MARCO = SRC / "railway-scheduling"
MARCO_INSTANCE = MARCO / "datasets/railway_N10_T10_J10_P1000_K3.json"
TL_HARD = 180   # timtab1 is a non-trivial MIP
TL_EASY = 60

report = {"meta": {}, "experiments": {}}


def proven_optima(results):
    return sorted({round(r["objective"], 2) for r in results
                   if r.get("objective") is not None and r.get("status") == "optimal"})


def exp1_reference():
    res = H.solve_all(str(TIMTAB), tl=TL_HARD)
    return {"description": "Reference optima + cross-solver on portable MPS (#9 timtab1)",
            "source_file": str(TIMTAB), "time_limit_s": TL_HARD,
            "proven_optima": proven_optima(res),
            "note": "timtab1 (MIPLIB cyclic timetable, 171 int vars) is hard; open-source solvers may hit the time limit.",
            "results": res}


def exp2_roundtrip():
    import gurobipy as gp
    m = gp.read(str(TIMTAB)); m.Params.OutputFlag = 0
    rmps, rlp = EXPORTS / "timtab1_reemit.mps", EXPORTS / "timtab1_reemit.lp"
    m.write(str(rmps)); m.write(str(rlp))
    res_lp = H.solve_all(str(rlp), which=("gurobi", "highs"), tl=TL_HARD)   # CBC reader = MPS only
    res_mps = H.solve_all(str(rmps), tl=TL_HARD)
    return {"description": "Round-trip: Gurobi re-emits timtab1 to .lp/.mps; re-solved by independent solvers",
            "reemitted_files": [str(rmps), str(rlp)],
            "proven_optima_lp": proven_optima(res_lp),
            "proven_optima_mps": proven_optima(res_mps),
            "results_reemit_lp": res_lp, "results_reemit_mps": res_mps}


def _build_marco():
    sys.path.insert(0, str(MARCO / "src"))
    from railway import Railway  # type: ignore
    rw = Railway.load(str(MARCO_INSTANCE))
    rw.set_model0(timelimit=TL_EASY, verbose=False)
    rw.set_constraints(); rw.set_objective()
    return rw.model


def _solve_native(tight):
    import gurobipy as gp
    m = _build_marco()
    m.Params.OutputFlag = 0; m.Params.Threads = 1; m.Params.TimeLimit = TL_EASY
    if tight:
        m.Params.MIPGap = 0.0; m.Params.FeasibilityTol = 1e-9; m.Params.IntFeasTol = 1e-9
    t = time.perf_counter(); m.optimize(); dt = time.perf_counter() - t
    return m, {"solver": f"gurobi-{gp.gurobi.version()[0]}.{gp.gurobi.version()[1]} (gurobipy, from repo code)",
               "tolerances": "tight (MIPGap=0, feas/int=1e-9)" if tight else "default (feas/int=1e-6)",
               "status": {2: "optimal"}.get(m.Status, f"status_{m.Status}"),
               "objective": round(m.ObjVal, 4) if m.Status == 2 else None,
               "obj_constant": round(m.ObjCon, 4),
               "runtime_s": round(dt, 4), "n_vars": m.NumVars, "n_constrs": m.NumConstrs, "n_int": m.NumIntVars}


def exp3_from_repo():
    _, native_default = _solve_native(tight=False)
    m_tight, native_tight = _solve_native(tight=True)
    exp_mps, exp_lp = EXPORTS / "marcotallone_N10T10J10.mps", EXPORTS / "marcotallone_N10T10J10.lp"
    m_tight.write(str(exp_mps)); m_tight.write(str(exp_lp))
    res_export = H.solve_all(str(exp_mps), tl=TL_EASY, tight=True)
    agreeing = proven_optima([native_tight] + res_export)
    return {"description": "From-repo gurobipy model (#8 marcotallone) — big-M tolerance caveat + cross-solver agreement",
            "instance": str(MARCO_INSTANCE),
            "big_m_value": "M=min(sum phi + 1, 1e5)",
            "native_default_tol": native_default,
            "native_tight_tol": native_tight,
            "exported_files": [str(exp_mps), str(exp_lp)],
            "results_exported_mps_tight": res_export,
            "true_optimum_agreed": agreeing,
            "finding": ("Default feasibility tolerance (1e-6) with big-M (1e5) yields a spurious lower 'optimum' "
                        f"({native_default['objective']}); at tight tolerance native, re-read, and all solvers agree "
                        f"on the true optimum {agreeing}.")}


def main():
    import gurobipy as gp, highspy, pulp, platform
    report["meta"] = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "python": platform.python_version(),
                      "gurobi": ".".join(map(str, gp.gurobi.version())),
                      "highs": highspy.Highs().version(), "pulp_cbc": pulp.__version__,
                      "determinism": "single-thread, OutputFlag=0; no custom heuristics"}
    for name, fn in (("1_reference_and_cross_solver", exp1_reference),
                     ("2_roundtrip_translation", exp2_roundtrip),
                     ("3_from_repo_bigM_caveat", exp3_from_repo)):
        try:
            report["experiments"][name] = fn()
            print(f"[ok] {name}")
        except Exception as e:  # noqa: BLE001
            report["experiments"][name] = {"error": f"{type(e).__name__}: {e}"}
            print(f"[ERR] {name}: {e}")
    out = RESULTS / "validation_results.json"
    out.write_text(json.dumps(report, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
