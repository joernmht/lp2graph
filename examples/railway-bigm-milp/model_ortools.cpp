// Railway single-track sequencing (big-M MILP) -- OR-Tools (C++).
// Build against OR-Tools, e.g.:
//   g++ model_ortools.cpp -lortools -o railway && ./railway
#include <algorithm>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

#include "ortools/linear_solver/linear_solver.h"

namespace operations_research {

void RailwayBigM() {
  const std::vector<std::string> trains = {"A", "B", "C", "D"};
  const std::vector<double> r = {0, 2, 1, 4};   // release
  const std::vector<double> p = {5, 3, 4, 2};   // running time
  const std::vector<double> w = {1, 2, 1, 3};   // weight
  const double h = 1.0;                         // headway
  const int n = static_cast<int>(trains.size());

  double sump = 0.0;
  for (double v : p) sump += v;
  const double M = *std::max_element(r.begin(), r.end()) + sump + (n - 1) * h;  // 21

  std::unique_ptr<MPSolver> solver(MPSolver::CreateSolver("CBC"));
  const double inf = solver->infinity();

  std::vector<MPVariable*> t(n), C(n);
  for (int i = 0; i < n; ++i) {
    t[i] = solver->MakeNumVar(0.0, inf, "t_" + trains[i]);
    C[i] = solver->MakeNumVar(0.0, inf, "C_" + trains[i]);
  }
  std::vector<std::vector<MPVariable*>> y(n, std::vector<MPVariable*>(n, nullptr));
  for (int i = 0; i < n; ++i)
    for (int j = i + 1; j < n; ++j)
      y[i][j] = solver->MakeBoolVar("y_" + trains[i] + "_" + trains[j]);

  MPObjective* obj = solver->MutableObjective();
  for (int i = 0; i < n; ++i) obj->SetCoefficient(C[i], w[i]);
  obj->SetMinimization();

  for (int i = 0; i < n; ++i) {
    // release: t_i >= r_i
    MPConstraint* rel = solver->MakeRowConstraint(r[i], inf);
    rel->SetCoefficient(t[i], 1.0);
    // completion: C_i - t_i = p_i
    MPConstraint* comp = solver->MakeRowConstraint(p[i], p[i]);
    comp->SetCoefficient(C[i], 1.0);
    comp->SetCoefficient(t[i], -1.0);
  }
  for (int i = 0; i < n; ++i) {
    for (int j = i + 1; j < n; ++j) {
      // seq_ij: t_j - t_i - M*y_ij >= p_i + h - M
      MPConstraint* c1 = solver->MakeRowConstraint(p[i] + h - M, inf);
      c1->SetCoefficient(t[j], 1.0);
      c1->SetCoefficient(t[i], -1.0);
      c1->SetCoefficient(y[i][j], -M);
      // seq_ji: t_i - t_j + M*y_ij >= p_j + h
      MPConstraint* c2 = solver->MakeRowConstraint(p[j] + h, inf);
      c2->SetCoefficient(t[i], 1.0);
      c2->SetCoefficient(t[j], -1.0);
      c2->SetCoefficient(y[i][j], M);
    }
  }

  if (solver->Solve() == MPSolver::OPTIMAL) {
    std::cout << "objective = " << obj->Value() << "\n";
    for (int i = 0; i < n; ++i)
      std::cout << "  " << trains[i] << ": enter t=" << t[i]->solution_value()
                << "  clear C=" << C[i]->solution_value() << "\n";
  }
}

}  // namespace operations_research

int main() {
  operations_research::RailwayBigM();
  return 0;
}
