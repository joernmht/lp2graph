# Railway single-track sequencing (big-M MILP) -- ZIMPL.
# Generate an LP/MPS and solve, e.g.:
#     zimpl model_zimpl.zpl            # writes model_zimpl.lp
#     glpsol --lp model_zimpl.lp

set I := { 1 .. 4 };                       # trains, by position
param nm[I] := <1> "A", <2> "B", <3> "C", <4> "D";
param r[I]  := <1> 0,   <2> 2,   <3> 1,   <4> 4;     # release
param p[I]  := <1> 5,   <2> 3,   <3> 4,   <4> 2;     # running time
param w[I]  := <1> 1,   <2> 2,   <3> 1,   <4> 3;     # weight
param h     := 1;                                    # headway
param M     := (max <i> in I : r[i]) + (sum <i> in I : p[i]) + (card(I) - 1) * h;  # big-M

var t[I] >= 0;                             # entry time
var C[I] >= 0;                             # clearance time
var y[<i,j> in I * I with i < j] binary;   # y[i,j]=1 iff i enters before j

minimize weighted_clearance: sum <i> in I : w[i] * C[i];

subto release:    forall <i> in I : t[i] >= r[i];
subto completion: forall <i> in I : C[i] == t[i] + p[i];
subto seq_ij: forall <i,j> in I * I with i < j :
    t[j] >= t[i] + p[i] + h - M * (1 - y[i,j]);
subto seq_ji: forall <i,j> in I * I with i < j :
    t[i] >= t[j] + p[j] + h - M * y[i,j];
