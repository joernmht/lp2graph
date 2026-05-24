# Railway single-track sequencing (big-M MILP) -- ompr (R).
#   install.packages(c("ompr", "ompr.roi", "ROI.plugin.glpk", "magrittr"))
#   Rscript model_ompr.R
library(ompr)
library(ompr.roi)
library(ROI.plugin.glpk)
library(magrittr)

trains <- c("A", "B", "C", "D")
n <- length(trains)
r <- c(0, 2, 1, 4)   # release        (positions match `trains`)
p <- c(5, 3, 4, 2)   # running time
w <- c(1, 2, 1, 3)   # weight
h <- 1               # headway
M <- max(r) + sum(p) + (n - 1) * h   # big-M = 21

model <- MIPModel() %>%
  add_variable(t[i], i = 1:n, type = "continuous", lb = 0) %>%
  add_variable(C[i], i = 1:n, type = "continuous", lb = 0) %>%
  add_variable(y[i, j], i = 1:n, j = 1:n, i < j, type = "binary") %>%
  set_objective(sum_over(w[i] * C[i], i = 1:n), "min") %>%
  add_constraint(t[i] >= r[i], i = 1:n) %>%
  add_constraint(C[i] == t[i] + p[i], i = 1:n) %>%
  add_constraint(t[j] >= t[i] + p[i] + h - M * (1 - y[i, j]), i = 1:n, j = 1:n, i < j) %>%
  add_constraint(t[i] >= t[j] + p[j] + h - M * y[i, j],       i = 1:n, j = 1:n, i < j)

res <- solve_model(model, with_ROI(solver = "glpk"))

cat("objective =", objective_value(res), "\n")
tv <- get_solution(res, t[i])
Cv <- get_solution(res, C[i])
for (i in order(tv$value)) {
  cat(sprintf("  %s: enter t=%g  clear C=%g\n", trains[i], tv$value[i], Cv$value[i]))
}
