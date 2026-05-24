/* Railway single-track sequencing (big-M MILP) -- GNU MathProg (GMPL).
   Fully self-contained. Solve with:
       glpsol --model model_glpk.mod
*/

param n := 4;
set I := 1..n;                       /* trains, by position */
param nm{I}, symbolic;              /* train names */
param r{I};                         /* release (earliest entry) */
param p{I};                         /* running time on the segment */
param w{I};                         /* priority weight */
param h := 1;                       /* minimum headway */
param M := (max{i in I} r[i]) + (sum{i in I} p[i]) + (n - 1) * h;  /* big-M = 21 */

var t{I} >= 0;                       /* entry time */
var C{I} >= 0;                       /* clearance time */
var y{i in I, j in I: i < j}, binary;   /* y[i,j]=1 iff i enters before j */

minimize weighted_clearance: sum{i in I} w[i] * C[i];

s.t. release{i in I}:    t[i] >= r[i];
s.t. completion{i in I}: C[i] = t[i] + p[i];
s.t. seq_ij{i in I, j in I: i < j}: t[j] >= t[i] + p[i] + h - M * (1 - y[i,j]);
s.t. seq_ji{i in I, j in I: i < j}: t[i] >= t[j] + p[j] + h - M * y[i,j];

solve;

printf "objective = %g\n", sum{i in I} w[i] * C[i];
printf {i in I} "  %s: enter t=%g  clear C=%g\n", nm[i], t[i], C[i];

data;
param nm := 1 A  2 B  3 C  4 D;
param r  := 1 0  2 2  3 1  4 4;
param p  := 1 5  2 3  3 4  4 2;
param w  := 1 1  2 2  3 1  4 3;

end;
