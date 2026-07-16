$title Railway single-track sequencing (big-M MILP) -- GAMS
* Run with:  gams model_gams.gms

Set i 'trains' / A, B, C, D /;
Alias (i, j);

Parameters
   r(i) 'release (earliest entry)' / A 0, B 2, C 1, D 4 /
   p(i) 'running time on the segment' / A 5, B 3, C 4, D 2 /
   w(i) 'priority weight' / A 1, B 2, C 1, D 3 /;

Scalar h 'minimum headway' / 1 /;
Scalar M 'big-M constant';
M = smax(i, r(i)) + sum(i, p(i)) + (card(i) - 1) * h;   display M;

Variables        z 'weighted clearance';
Positive Variables t(i) 'entry time', C(i) 'clearance time';
Binary Variables   y(i,j) 'y(i,j)=1 iff i enters before j';

Equations
   obj          'objective'
   release(i)   'earliest entry'
   completion(i) 'clearance = entry + running time'
   seq_ij(i,j)  'i before j'
   seq_ji(i,j)  'j before i';

obj..             z =e= sum(i, w(i) * C(i));
release(i)..      t(i) =g= r(i);
completion(i)..   C(i) =e= t(i) + p(i);
seq_ij(i,j)$(ord(i) < ord(j)).. t(j) =g= t(i) + p(i) + h - M * (1 - y(i,j));
seq_ji(i,j)$(ord(i) < ord(j)).. t(i) =g= t(j) + p(j) + h - M * y(i,j);

Model railway / all /;
solve railway using mip minimizing z;

display z.l, t.l, C.l, y.l;
