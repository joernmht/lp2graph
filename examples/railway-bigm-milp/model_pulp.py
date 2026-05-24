"""Railway single-track sequencing (big-M MILP) -- PuLP.

    pip install pulp
    python model_pulp.py

Also exports model.lp (CPLEX LP) and model.mps so the portable-format files
in this folder are guaranteed to be the exact same model.
"""
import itertools
import pulp

# ----- data -----------------------------------------------------------------
TRAINS = ["A", "B", "C", "D"]
r = {"A": 0, "B": 2, "C": 1, "D": 4}   # release (earliest entry)
p = {"A": 5, "B": 3, "C": 4, "D": 2}   # running time on the segment
w = {"A": 1, "B": 2, "C": 1, "D": 3}   # priority weight
h = 1                                  # minimum headway
n = len(TRAINS)
M = max(r.values()) + sum(p.values()) + (n - 1) * h   # = 21, valid big-M
PAIRS = list(itertools.combinations(TRAINS, 2))        # ordered index pairs i<j

# ----- model ----------------------------------------------------------------
m = pulp.LpProblem("railway_bigm", pulp.LpMinimize)

t = {i: pulp.LpVariable(f"t_{i}", lowBound=0) for i in TRAINS}
C = {i: pulp.LpVariable(f"C_{i}", lowBound=0) for i in TRAINS}
y = {(i, j): pulp.LpVariable(f"y_{i}_{j}", cat="Binary") for (i, j) in PAIRS}

m += pulp.lpSum(w[i] * C[i] for i in TRAINS), "weighted_clearance"

for i in TRAINS:
    m += t[i] >= r[i], f"release_{i}"
    m += C[i] == t[i] + p[i], f"completion_{i}"

for (i, j) in PAIRS:
    m += t[j] >= t[i] + p[i] + h - M * (1 - y[(i, j)]), f"seq_{i}_before_{j}"
    m += t[i] >= t[j] + p[j] + h - M * y[(i, j)],       f"seq_{j}_before_{i}"

# ----- solve ----------------------------------------------------------------
m.solve(pulp.PULP_CBC_CMD(msg=False))

print("status :", pulp.LpStatus[m.status])
print("objective:", pulp.value(m.objective))
for i in sorted(TRAINS, key=lambda k: pulp.value(t[k])):
    print(f"  {i}: enter t={pulp.value(t[i]):.0f}  clear C={pulp.value(C[i]):.0f}")

# ----- export portable formats ---------------------------------------------
m.writeLP("model.lp")
m.writeMPS("model.mps")
