% Railway single-track sequencing (big-M MILP) -- MATLAB (intlinprog).
%   run in MATLAB:  model_matlab
% (Octave users: replace the intlinprog call with the bundled `glpk`.)
%
% Variable vector x = [ t(1..n) , C(1..n) , y(1..np) ],  pairs i<j.

trains = {'A','B','C','D'};
r = [0 2 1 4];      % release (earliest entry)
p = [5 3 4 2];      % running time on the segment
w = [1 2 1 3];      % priority weight
h = 1;              % minimum headway
n = numel(trains);
M = max(r) + sum(p) + (n - 1) * h;     % big-M = 21

pairs = nchoosek(1:n, 2);              % rows [i j] with i<j
np = size(pairs, 1);
N  = 2 * n + np;                       % total variables
it = @(i) i;                           % index of t_i
iC = @(i) n + i;                       % index of C_i
iy = @(k) 2 * n + k;                   % index of y_k

% --- objective: min sum_i w_i C_i ---
f = zeros(N, 1);
f(iC(1:n)) = w;

% --- bounds + integrality (release t_i >= r_i as a lower bound) ---
lb = zeros(N, 1);  lb(it(1:n)) = r;
ub = inf(N, 1);    ub(iy(1:np)) = 1;
intcon = iy(1:np);

% --- equalities: C_i - t_i = p_i ---
Aeq = zeros(n, N);  beq = zeros(n, 1);
for i = 1:n
    Aeq(i, iC(i)) =  1;
    Aeq(i, it(i)) = -1;
    beq(i)        =  p(i);
end

% --- big-M inequalities (A x <= b) ---
A = zeros(2 * np, N);  b = zeros(2 * np, 1);
row = 0;
for k = 1:np
    i = pairs(k, 1);  j = pairs(k, 2);
    % seq_ij: t_j >= t_i + p_i + h - M(1 - y_k)  ->  t_i - t_j + M y_k <= M - p_i - h
    row = row + 1;
    A(row, it(i)) =  1;  A(row, it(j)) = -1;  A(row, iy(k)) =  M;
    b(row) = M - p(i) - h;
    % seq_ji: t_i >= t_j + p_j + h - M y_k       -> -t_i + t_j - M y_k <= -(p_j + h)
    row = row + 1;
    A(row, it(i)) = -1;  A(row, it(j)) =  1;  A(row, iy(k)) = -M;
    b(row) = -(p(j) + h);
end

opts = optimoptions('intlinprog', 'Display', 'off');
[x, fval] = intlinprog(f, intcon, A, b, Aeq, beq, lb, ub, [], opts);

fprintf('objective = %g\n', fval);
[~, ord] = sort(x(it(1:n)));
for idx = ord'
    fprintf('  %s: enter t=%g  clear C=%g\n', trains{idx}, x(it(idx)), x(iC(idx)));
end
