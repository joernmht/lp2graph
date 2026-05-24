"""Railway single-track sequencing (big-M MILP) -- Pyomo.

    pip install pyomo
    python model_pyomo.py            # uses any installed MILP solver (glpk/cbc/gurobi)
"""
import itertools
import pyomo.environ as pyo

# ----- data -----------------------------------------------------------------
TRAINS = ["A", "B", "C", "D"]
r = {"A": 0, "B": 2, "C": 1, "D": 4}
p = {"A": 5, "B": 3, "C": 4, "D": 2}
w = {"A": 1, "B": 2, "C": 1, "D": 3}
h = 1
n = len(TRAINS)
M = max(r.values()) + sum(p.values()) + (n - 1) * h   # = 21
PAIRS = list(itertools.combinations(TRAINS, 2))

# ----- model ----------------------------------------------------------------
m = pyo.ConcreteModel("railway_bigm")
m.I = pyo.Set(initialize=TRAINS)
m.P = pyo.Set(initialize=PAIRS, dimen=2)

m.t = pyo.Var(m.I, domain=pyo.NonNegativeReals)
m.C = pyo.Var(m.I, domain=pyo.NonNegativeReals)
m.y = pyo.Var(m.P, domain=pyo.Binary)

m.obj = pyo.Objective(expr=sum(w[i] * m.C[i] for i in m.I), sense=pyo.minimize)

m.release    = pyo.Constraint(m.I, rule=lambda m, i: m.t[i] >= r[i])
m.completion = pyo.Constraint(m.I, rule=lambda m, i: m.C[i] == m.t[i] + p[i])
m.seq_ij = pyo.Constraint(m.P, rule=lambda m, i, j:
                          m.t[j] >= m.t[i] + p[i] + h - M * (1 - m.y[i, j]))
m.seq_ji = pyo.Constraint(m.P, rule=lambda m, i, j:
                          m.t[i] >= m.t[j] + p[j] + h - M * m.y[i, j])

# ----- solve ----------------------------------------------------------------
solver = pyo.SolverFactory("glpk")     # or "cbc", "gurobi", ...
solver.solve(m)

print("objective:", pyo.value(m.obj))
for i in sorted(TRAINS, key=lambda k: pyo.value(m.t[k])):
    print(f"  {i}: enter t={pyo.value(m.t[i]):.0f}  clear C={pyo.value(m.C[i]):.0f}")
