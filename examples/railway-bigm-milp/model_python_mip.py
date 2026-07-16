"""Railway single-track sequencing (big-M MILP) -- Python-MIP.

    pip install mip
    python model_python_mip.py
"""
import itertools
from mip import Model, xsum, minimize, BINARY, CONTINUOUS, OptimizationStatus

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
m = Model("railway_bigm")

t = {i: m.add_var(name=f"t_{i}", lb=0.0, var_type=CONTINUOUS) for i in TRAINS}
C = {i: m.add_var(name=f"C_{i}", lb=0.0, var_type=CONTINUOUS) for i in TRAINS}
y = {(i, j): m.add_var(name=f"y_{i}_{j}", var_type=BINARY) for (i, j) in PAIRS}

m.objective = minimize(xsum(w[i] * C[i] for i in TRAINS))

for i in TRAINS:
    m += t[i] >= r[i]
    m += C[i] == t[i] + p[i]
for (i, j) in PAIRS:
    m += t[j] >= t[i] + p[i] + h - M * (1 - y[(i, j)])
    m += t[i] >= t[j] + p[j] + h - M * y[(i, j)]

# ----- solve ----------------------------------------------------------------
status = m.optimize()
if status in (OptimizationStatus.OPTIMAL, OptimizationStatus.FEASIBLE):
    print("objective:", m.objective_value)
    for i in sorted(TRAINS, key=lambda k: t[k].x):
        print(f"  {i}: enter t={t[i].x:.0f}  clear C={C[i].x:.0f}")
