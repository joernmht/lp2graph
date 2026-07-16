"""Railway single-track sequencing (big-M MILP) -- gurobipy.

    pip install gurobipy        # needs a Gurobi licence
    python model_gurobi.py
"""
import itertools
import gurobipy as gp
from gurobipy import GRB

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
m = gp.Model("railway_bigm")

t = m.addVars(TRAINS, lb=0.0, name="t")
C = m.addVars(TRAINS, lb=0.0, name="C")
y = m.addVars(PAIRS, vtype=GRB.BINARY, name="y")

m.setObjective(gp.quicksum(w[i] * C[i] for i in TRAINS), GRB.MINIMIZE)

m.addConstrs((t[i] >= r[i] for i in TRAINS), name="release")
m.addConstrs((C[i] == t[i] + p[i] for i in TRAINS), name="completion")
for (i, j) in PAIRS:
    m.addConstr(t[j] >= t[i] + p[i] + h - M * (1 - y[i, j]), name=f"seq_{i}_before_{j}")
    m.addConstr(t[i] >= t[j] + p[j] + h - M * y[i, j],       name=f"seq_{j}_before_{i}")

# ----- solve ----------------------------------------------------------------
m.optimize()

if m.status == GRB.OPTIMAL:
    print("objective:", m.objVal)
    for i in sorted(TRAINS, key=lambda k: t[k].X):
        print(f"  {i}: enter t={t[i].X:.0f}  clear C={C[i].X:.0f}")
