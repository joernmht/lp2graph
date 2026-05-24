% Railway single-track sequencing (big-M MILP) -- MiniZinc.
% Solve with a MIP backend so the big-M form is kept linear, e.g.:
%     minizinc --solver coin-bc model_minizinc.mzn

enum TRAINS = { A, B, C, D };
array[TRAINS] of int: r = [0, 2, 1, 4];   % release (earliest entry)
array[TRAINS] of int: p = [5, 3, 4, 2];   % running time on the segment
array[TRAINS] of int: w = [1, 2, 1, 3];   % priority weight
int: h = 1;                               % minimum headway
int: n = card(TRAINS);
int: M = max(r) + sum(p) + (n - 1) * h;   % big-M = 21
int: ub = M + max(p);                     % safe horizon for the clocks

array[TRAINS] of var 0..ub: t;            % entry time
array[TRAINS] of var 0..ub: C;            % clearance time
array[TRAINS, TRAINS] of var 0..1: y;     % y[i,j]=1 iff i before j (used for i<j)

constraint forall(i in TRAINS)(t[i] >= r[i]);
constraint forall(i in TRAINS)(C[i] = t[i] + p[i]);
constraint forall(i, j in TRAINS where i < j)(
    t[j] >= t[i] + p[i] + h - M * (1 - y[i,j]) /\
    t[i] >= t[j] + p[j] + h - M * y[i,j]
);

var int: cost = sum(i in TRAINS)(w[i] * C[i]);
solve minimize cost;

output ["cost = \(cost)\n"] ++
       ["  \(i): enter t=\(t[i])  clear C=\(C[i])\n" | i in TRAINS];
