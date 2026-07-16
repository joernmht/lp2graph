"""Railway single-track sequencing (big-M MILP) -- CPLEX via DOcplex (Python).

    pip install docplex cplex
    python model_docplex.py

`docplex` is IBM's modelling layer; `cplex` provides the engine (the pip
Community Edition solves models up to 1000 vars/constraints -- plenty here).
"""
import itertools
from docplex.mp.model import Model

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
mdl = Model(name="railway_bigm")

t = mdl.continuous_var_dict(TRAINS, lb=0, name="t")
C = mdl.continuous_var_dict(TRAINS, lb=0, name="C")
y = mdl.binary_var_dict(PAIRS, name="y")

mdl.minimize(mdl.sum(w[i] * C[i] for i in TRAINS))

for i in TRAINS:
    mdl.add_constraint(t[i] >= r[i], ctname=f"release_{i}")
    mdl.add_constraint(C[i] == t[i] + p[i], ctname=f"completion_{i}")
for (i, j) in PAIRS:
    mdl.add_constraint(t[j] >= t[i] + p[i] + h - M * (1 - y[(i, j)]), ctname=f"seq_{i}_before_{j}")
    mdl.add_constraint(t[i] >= t[j] + p[j] + h - M * y[(i, j)],       ctname=f"seq_{j}_before_{i}")

# ----- solve ----------------------------------------------------------------
mdl.solve()

print("objective:", mdl.objective_value)
for i in sorted(TRAINS, key=lambda k: t[k].solution_value):
    print(f"  {i}: enter t={t[i].solution_value:.0f}  clear C={C[i].solution_value:.0f}")
