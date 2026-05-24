# Railway single-track sequencing (big-M MILP) -- JuMP (Julia).
#   import Pkg; Pkg.add(["JuMP", "HiGHS"])
#   julia model_jump.jl
using JuMP, HiGHS

trains = [:A, :B, :C, :D]
r = Dict(:A => 0, :B => 2, :C => 1, :D => 4)   # release
p = Dict(:A => 5, :B => 3, :C => 4, :D => 2)   # running time
w = Dict(:A => 1, :B => 2, :C => 1, :D => 3)   # weight
h = 1                                          # headway
n = length(trains)
M = maximum(values(r)) + sum(values(p)) + (n - 1) * h   # big-M = 21
pairs = [(trains[a], trains[b]) for a in 1:n for b in (a + 1):n]

model = Model(HiGHS.Optimizer)
@variable(model, t[trains] >= 0)               # entry time
@variable(model, C[trains] >= 0)               # clearance time
@variable(model, y[pairs], Bin)                # y[(i,j)]=1 iff i before j

@objective(model, Min, sum(w[i] * C[i] for i in trains))
@constraint(model, [i in trains], t[i] >= r[i])
@constraint(model, [i in trains], C[i] == t[i] + p[i])
@constraint(model, [(i, j) in pairs], t[j] >= t[i] + p[i] + h - M * (1 - y[(i, j)]))
@constraint(model, [(i, j) in pairs], t[i] >= t[j] + p[j] + h - M * y[(i, j)])

optimize!(model)

println("objective = ", objective_value(model))
for i in sort(trains, by = i -> value(t[i]))
    println("  $i: enter t=", round(Int, value(t[i])), "  clear C=", round(Int, value(C[i])))
end
