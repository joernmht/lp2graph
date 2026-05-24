"""Railway single-track sequencing (big-M MILP) -- CVXPY.

    pip install cvxpy
    python model_cvxpy.py            # needs a MILP-capable backend (GLPK_MI/CBC/SCIP/...)

CVXPY is matrix/vector oriented, so trains are indexed 0..n-1.
"""
import itertools
import numpy as np
import cvxpy as cp

# ----- data (index order A,B,C,D) -------------------------------------------
TRAINS = ["A", "B", "C", "D"]
r = np.array([0, 2, 1, 4])
p = np.array([5, 3, 4, 2])
w = np.array([1, 2, 1, 3])
h = 1
n = len(TRAINS)
M = int(r.max() + p.sum() + (n - 1) * h)   # = 21
PAIRS = list(itertools.combinations(range(n), 2))

# ----- model ----------------------------------------------------------------
t = cp.Variable(n, nonneg=True, name="t")
C = cp.Variable(n, nonneg=True, name="C")
y = cp.Variable(len(PAIRS), boolean=True, name="y")

constraints = [t >= r, C == t + p]
for k, (i, j) in enumerate(PAIRS):
    constraints += [
        t[j] >= t[i] + p[i] + h - M * (1 - y[k]),
        t[i] >= t[j] + p[j] + h - M * y[k],
    ]

prob = cp.Problem(cp.Minimize(w @ C), constraints)

# ----- solve ----------------------------------------------------------------
prob.solve(solver=cp.GLPK_MI)          # or cp.CBC, cp.SCIP, ...

print("objective:", prob.value)
order = sorted(range(n), key=lambda i: t.value[i])
for i in order:
    print(f"  {TRAINS[i]}: enter t={t.value[i]:.0f}  clear C={C.value[i]:.0f}")
