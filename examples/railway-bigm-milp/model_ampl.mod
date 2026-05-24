# Railway single-track sequencing (big-M MILP) -- AMPL.
# Self-contained (model + data + solve). Run with:
#     ampl model_ampl.mod

set TRAINS ordered;
param r{TRAINS} >= 0;        # release (earliest entry)
param p{TRAINS} >  0;        # running time on the segment
param w{TRAINS} >= 0;        # priority weight
param h >= 0;                # minimum headway
param M := (max{i in TRAINS} r[i]) + (sum{i in TRAINS} p[i]) + (card(TRAINS) - 1) * h;  # big-M

var t{TRAINS} >= 0;          # entry time
var C{TRAINS} >= 0;          # clearance time
var y{i in TRAINS, j in TRAINS: ord(i) < ord(j)} binary;  # y[i,j]=1 iff i before j

minimize weighted_clearance: sum{i in TRAINS} w[i] * C[i];

subject to release {i in TRAINS}:    t[i] >= r[i];
subject to completion {i in TRAINS}: C[i] = t[i] + p[i];
subject to seq_ij {i in TRAINS, j in TRAINS: ord(i) < ord(j)}:
    t[j] >= t[i] + p[i] + h - M * (1 - y[i,j]);
subject to seq_ji {i in TRAINS, j in TRAINS: ord(i) < ord(j)}:
    t[i] >= t[j] + p[j] + h - M * y[i,j];

data;
set TRAINS := A B C D;
param:   r   p   w :=
    A    0   5   1
    B    2   3   2
    C    1   4   1
    D    4   2   3 ;
param h := 1;

option solver cbc;          # or gurobi, cplex, highs, ...
solve;
display weighted_clearance;
display t, C, y;
