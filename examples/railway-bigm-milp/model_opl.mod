// Railway single-track sequencing (big-M MILP) -- CPLEX OPL.
// Run in IBM ILOG CPLEX Optimization Studio:  oplrun model_opl.mod
// (Self-contained: data is inline, so no .dat file is needed.)

{string} TRAINS = {"A", "B", "C", "D"};                 // trains, in order
int r[TRAINS] = ["A":0, "B":2, "C":1, "D":4];           // release
int p[TRAINS] = ["A":5, "B":3, "C":4, "D":2];           // running time
int w[TRAINS] = ["A":1, "B":2, "C":1, "D":3];           // weight
int h = 1;                                              // headway
int M = (max(i in TRAINS) r[i]) + (sum(i in TRAINS) p[i]) + (card(TRAINS) - 1) * h;  // big-M = 21

dvar float+ t[TRAINS];          // entry time
dvar float+ C[TRAINS];          // clearance time
dvar boolean y[TRAINS][TRAINS]; // y[i][j]=1 iff i enters before j (i before j only)

minimize sum(i in TRAINS) w[i] * C[i];

subject to {
  forall(i in TRAINS) release:    t[i] >= r[i];
  forall(i in TRAINS) completion: C[i] == t[i] + p[i];
  forall(ordered i, j in TRAINS) {
    t[j] >= t[i] + p[i] + h - M * (1 - y[i][j]);    // i before j
    t[i] >= t[j] + p[j] + h - M * y[i][j];          // j before i
  }
}

execute DISPLAY {
  writeln("objective = ", cplex.getObjValue());
  for (var i in TRAINS)
    writeln("  ", i, ": enter t=", t[i], "  clear C=", C[i]);
}
