# Railway single-track sequencing — a big-M MILP, in every dialect

A small, **complete**, and **self-contained** mixed-integer linear program
(MILP) drawn from railway operations. It is deliberately tiny (four trains)
so the optimum can be checked by hand, yet it contains the one ingredient
that every practitioner eventually meets: a **big-M disjunction**.

The same model is written out in this folder in ~20 modelling dialects —
from algebraic modelling languages (AMPL, GAMS, GMPL, ZIMPL, MiniZinc,
CPLEX OPL), through solver-portable file formats (CPLEX LP, MPS), to
general-purpose programming languages (Python ×7 — incl. gurobipy and
DOcplex/CPLEX, Julia, R, MATLAB/Octave, C++, Java). A
[`build_pdf.py`](build_pdf.py) script renders the whole thing into
[`railway_bigm_milp.pdf`](railway_bigm_milp.pdf), **one representation per
page**.

This is a fleshed-out, single-instance companion to the catalogue
formulation [`formulations/constraints/mip_2_1_big_m.json`](../../formulations/constraints/mip_2_1_big_m.json).

---

## 1. The problem (plain words)

A set of trains must each traverse one shared **single-track segment** (a
tunnel, a bridge, a passing-loop bottleneck). The segment is a mutual-
exclusion resource: **at most one train may occupy it at a time**, and after
a train clears it a **minimum headway** `h` must elapse before the next train
may enter (signal reset, safety margin).

Each train `i`:

| symbol | meaning                                            |
|--------|----------------------------------------------------|
| `r_i`  | earliest time it can enter the segment (release)   |
| `p_i`  | running time it needs to occupy the segment        |
| `w_i`  | priority weight (how costly it is to delay it)     |

The dispatcher must decide, for every train, **when it enters** the segment
(`t_i`) and, implicitly, **in which order** the trains go. The goal is to
minimise the total **weighted clearance time** `Σ wᵢ·Cᵢ`, where the
clearance (completion) time is `Cᵢ = tᵢ + pᵢ`.

The hard part is the mutual exclusion: for any two trains `i` and `j`,
*either* `i` goes before `j` *or* `j` goes before `i`. That "either/or" is a
**disjunction**, and the standard way to linearise it is the **big-M**
trick with a binary ordering variable `y_{ij}`.

### The data instance

Four trains, `𝒩 = {A, B, C, D}`:

| train | `r_i` (release) | `p_i` (run) | `w_i` (weight) |
|:-----:|:---------------:|:-----------:|:--------------:|
| **A** | 0               | 5           | 1              |
| **B** | 2               | 3           | 2              |
| **C** | 1               | 4           | 1              |
| **D** | 4               | 2           | 3              |

Minimum headway `h = 1`.

Big-M constant — chosen as a **valid, reasonably tight** upper bound on any
sensible entry time (one train may have to wait behind all the others):

```
M = max_i r_i + Σ_i p_i + (|𝒩| − 1)·h
  =     4     +    14    +     3        = 21
```

---

## 2. The mathematical model (markdown / `\mathcal`)

> Rendered by GitHub/MathJax. The identical model in standalone LaTeX is in
> [`problem.tex`](problem.tex).

**Sets**

$$
\mathcal{N} = \{A,B,C,D\} \quad\text{(trains)}, \qquad
\mathcal{P} = \{(i,j)\in\mathcal{N}\times\mathcal{N} : i \prec j\} \quad\text{(ordered index pairs)}
$$

**Parameters**

$$
r_i \ \text{(release)},\quad
p_i \ \text{(running time)},\quad
w_i \ \text{(weight)},\quad
h \ \text{(headway)},\quad
M = \max_{i} r_i + \sum_{i\in\mathcal N} p_i + (|\mathcal N|-1)\,h
$$

**Decision variables**

$$
t_i \ge 0 \ \text{(entry time)},\qquad
C_i \ge 0 \ \text{(clearance time)},\qquad
y_{ij}\in\{0,1\}\ \ \forall (i,j)\in\mathcal{P}
$$

with the reading $y_{ij}=1 \iff$ train $i$ enters the segment before train $j$.

**Model**

$$
\begin{aligned}
\min_{t,\,C,\,y}\quad & \sum_{i\in\mathcal{N}} w_i\,C_i && \text{(weighted clearance)}\\[2pt]
\text{s.t.}\quad
& t_i \ge r_i && \forall i\in\mathcal{N} & (\text{release})\\
& C_i = t_i + p_i && \forall i\in\mathcal{N} & (\text{clearance})\\
& t_j \ge t_i + p_i + h - M\,(1 - y_{ij}) && \forall (i,j)\in\mathcal{P} & (\text{$i$ before $j$})\\
& t_i \ge t_j + p_j + h - M\,y_{ij} && \forall (i,j)\in\mathcal{P} & (\text{$j$ before $i$})\\
& t_i \ge 0,\; C_i \ge 0,\; y_{ij}\in\{0,1\}. &&
\end{aligned}
$$

**Why big-M works.** For a pair $(i,j)$ the binary $y_{ij}$ *selects* which
of the two mutually-exclusive sequencing constraints is enforced:

- If $y_{ij}=1$: the first constraint becomes the tight $t_j \ge t_i+p_i+h$
  (train $i$ then $j$), while the second becomes
  $t_i \ge t_j+p_j+h-M$ — with $M$ large this right-hand side is so negative
  that the constraint is **vacuous**.
- If $y_{ij}=0$: symmetric — the second constraint binds and the first is
  switched off.

$M$ must be large enough never to wrongly cut a feasible schedule, but no
larger, because an oversized $M$ weakens the LP relaxation and slows the
branch-and-bound. The bound above is exactly tight enough.

---

## 3. The optimal solution (so you can check any implementation)

Optimal objective value **`Σ wᵢ·Cᵢ = 66`**. One optimal schedule (order
**B → D → C → A**):

| train | enters `t_i` | clears `C_i` | `w_i·C_i` |
|:-----:|:------------:|:------------:|:---------:|
| **B** | 2            | 5            | 10        |
| **D** | 6            | 8            | 24        |
| **C** | 9            | 13           | 13        |
| **A** | 14           | 19           | 19        |
|       |              | **total**    | **66**    |

(The order respects priorities and headways: B clears at 5, D enters at
`5+1=6`, C at `8+1=9`, A at `13+1=14`. Verified independently with CBC and
with OR-Tools CP-SAT.)

---

## 4. The files — one model, many dialects

| file | dialect / tool | category |
|------|----------------|----------|
| [`problem.tex`](problem.tex)            | LaTeX (standalone)            | document |
| [`model_pulp.py`](model_pulp.py)        | PuLP (Python)                 | library  |
| [`model_gurobi.py`](model_gurobi.py)    | gurobipy (Python)             | library  |
| [`model_docplex.py`](model_docplex.py)  | DOcplex / CPLEX (Python)      | library  |
| [`model_pyomo.py`](model_pyomo.py)      | Pyomo (Python)                | library  |
| [`model_ortools.py`](model_ortools.py)  | OR-Tools MPSolver (Python)    | library  |
| [`model_python_mip.py`](model_python_mip.py) | Python-MIP               | library  |
| [`model_cvxpy.py`](model_cvxpy.py)      | CVXPY (Python)                | library  |
| [`model_jump.jl`](model_jump.jl)        | JuMP (Julia)                  | library  |
| [`model_ompr.R`](model_ompr.R)          | ompr / ROI (R)                | library  |
| [`model_matlab.m`](model_matlab.m)      | `intlinprog` (MATLAB/Octave)  | matrix   |
| [`model_ortools.cpp`](model_ortools.cpp)| OR-Tools (C++)                | library  |
| [`ModelOrTools.java`](ModelOrTools.java)| OR-Tools (Java)               | library  |
| [`model_ampl.mod`](model_ampl.mod)      | AMPL                          | AML      |
| [`model_gams.gms`](model_gams.gms)      | GAMS                          | AML      |
| [`model_glpk.mod`](model_glpk.mod)      | GNU MathProg / GMPL (glpsol)  | AML      |
| [`model_zimpl.zpl`](model_zimpl.zpl)    | ZIMPL                         | AML      |
| [`model_minizinc.mzn`](model_minizinc.mzn) | MiniZinc                   | CP/AML   |
| [`model_opl.mod`](model_opl.mod)        | CPLEX OPL (oplrun)            | AML      |
| [`model.lp`](model.lp)                  | CPLEX LP format               | exchange |
| [`model.mps`](model.mps)                | MPS format                    | exchange |
| [`data.json`](data.json)                | the instance (single source)  | data     |
| [`build_pdf.py`](build_pdf.py)          | PDF builder (reportlab)       | tooling  |

`model.lp` and `model.mps` are **generated** by `model_pulp.py`, so they are
guaranteed to be the exact same model.

### Running a few of them

```bash
# Python — each prints status, objective 66, and the schedule
pip install pulp        && python model_pulp.py
pip install pyomo       && python model_pyomo.py        # needs a solver, e.g. glpk/cbc
pip install ortools     && python model_ortools.py
pip install mip         && python model_python_mip.py
pip install cvxpy       && python model_cvxpy.py
pip install gurobipy    && python model_gurobi.py        # needs a Gurobi licence
pip install docplex cplex && python model_docplex.py     # CPLEX (pip Community Edition)

# Algebraic modelling languages
glpsol --model model_glpk.mod                            # GLPK, fully self-contained
ampl model_ampl.mod                                      # AMPL (data is inline)
gams model_gams.gms                                       # GAMS
zimpl model_zimpl.zpl && glpsol --lp model_zimpl.lp      # ZIMPL -> LP -> solve
minizinc --solver coin-bc model_minizinc.mzn             # MiniZinc
oplrun model_opl.mod                                      # CPLEX OPL (CPLEX Studio)

# Portable formats: feed straight to any solver
glpsol --lp  model.lp  --output sol.txt
glpsol --mps model.mps --output sol.txt
cbc model.lp solve solu stdout

# Julia / R / MATLAB
julia model_jump.jl
Rscript model_ompr.R
matlab -batch model_matlab           # MATLAB (intlinprog); Octave: swap in glpk()

# Build the all-in-one PDF (one representation per page)
pip install reportlab && python build_pdf.py
```

Every implementation encodes the **identical** formulation and instance and
returns the same optimum, **66**.
