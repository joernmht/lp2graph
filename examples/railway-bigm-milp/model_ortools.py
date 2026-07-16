"""Railway single-track sequencing (big-M MILP) -- Google OR-Tools (MPSolver).

    pip install ortools
    python model_ortools.py

Uses the linear MILP wrapper (CBC backend) so the big-M formulation is kept
verbatim. (OR-Tools' CP-SAT could model the disjunction natively without a
big-M, but the point here is to show the classic big-M MILP.)
"""
import itertools
from ortools.linear_solver import pywraplp

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
solver = pywraplp.Solver.CreateSolver("CBC")
INF = solver.infinity()

t = {i: solver.NumVar(0.0, INF, f"t_{i}") for i in TRAINS}
C = {i: solver.NumVar(0.0, INF, f"C_{i}") for i in TRAINS}
y = {(i, j): solver.BoolVar(f"y_{i}_{j}") for (i, j) in PAIRS}

for i in TRAINS:
    solver.Add(t[i] >= r[i])
    solver.Add(C[i] == t[i] + p[i])
for (i, j) in PAIRS:
    solver.Add(t[j] >= t[i] + p[i] + h - M * (1 - y[(i, j)]))
    solver.Add(t[i] >= t[j] + p[j] + h - M * y[(i, j)])

solver.Minimize(solver.Sum(w[i] * C[i] for i in TRAINS))

# ----- solve ----------------------------------------------------------------
status = solver.Solve()
if status == pywraplp.Solver.OPTIMAL:
    print("objective:", solver.Objective().Value())
    for i in sorted(TRAINS, key=lambda k: t[k].solution_value()):
        print(f"  {i}: enter t={t[i].solution_value():.0f}  clear C={C[i].solution_value():.0f}")
