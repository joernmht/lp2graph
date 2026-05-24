// Railway single-track sequencing (big-M MILP) -- OR-Tools (Java).
//   javac -cp ortools.jar ModelOrTools.java
//   java  -cp .:ortools.jar ModelOrTools
import com.google.ortools.Loader;
import com.google.ortools.linearsolver.MPConstraint;
import com.google.ortools.linearsolver.MPObjective;
import com.google.ortools.linearsolver.MPSolver;
import com.google.ortools.linearsolver.MPVariable;

public class ModelOrTools {
  public static void main(String[] args) {
    Loader.loadNativeLibraries();

    String[] trains = {"A", "B", "C", "D"};
    double[] r = {0, 2, 1, 4};   // release
    double[] p = {5, 3, 4, 2};   // running time
    double[] w = {1, 2, 1, 3};   // weight
    double h = 1.0;              // headway
    int n = trains.length;

    double maxr = r[0], sump = 0;
    for (double v : r) maxr = Math.max(maxr, v);
    for (double v : p) sump += v;
    double M = maxr + sump + (n - 1) * h;   // big-M = 21

    MPSolver solver = MPSolver.createSolver("CBC");
    double inf = Double.POSITIVE_INFINITY;

    MPVariable[] t = new MPVariable[n];
    MPVariable[] C = new MPVariable[n];
    for (int i = 0; i < n; i++) {
      t[i] = solver.makeNumVar(0.0, inf, "t_" + trains[i]);
      C[i] = solver.makeNumVar(0.0, inf, "C_" + trains[i]);
    }
    MPVariable[][] y = new MPVariable[n][n];
    for (int i = 0; i < n; i++)
      for (int j = i + 1; j < n; j++)
        y[i][j] = solver.makeBoolVar("y_" + trains[i] + "_" + trains[j]);

    MPObjective obj = solver.objective();
    for (int i = 0; i < n; i++) obj.setCoefficient(C[i], w[i]);
    obj.setMinimization();

    for (int i = 0; i < n; i++) {
      MPConstraint rel = solver.makeConstraint(r[i], inf);   // t_i >= r_i
      rel.setCoefficient(t[i], 1.0);
      MPConstraint comp = solver.makeConstraint(p[i], p[i]); // C_i - t_i = p_i
      comp.setCoefficient(C[i], 1.0);
      comp.setCoefficient(t[i], -1.0);
    }
    for (int i = 0; i < n; i++) {
      for (int j = i + 1; j < n; j++) {
        // seq_ij: t_j - t_i - M*y_ij >= p_i + h - M
        MPConstraint c1 = solver.makeConstraint(p[i] + h - M, inf);
        c1.setCoefficient(t[j], 1.0);
        c1.setCoefficient(t[i], -1.0);
        c1.setCoefficient(y[i][j], -M);
        // seq_ji: t_i - t_j + M*y_ij >= p_j + h
        MPConstraint c2 = solver.makeConstraint(p[j] + h, inf);
        c2.setCoefficient(t[i], 1.0);
        c2.setCoefficient(t[j], -1.0);
        c2.setCoefficient(y[i][j], M);
      }
    }

    if (solver.solve() == MPSolver.ResultStatus.OPTIMAL) {
      System.out.println("objective = " + obj.value());
      for (int i = 0; i < n; i++) {
        System.out.printf("  %s: enter t=%.0f  clear C=%.0f%n",
            trains[i], t[i].solutionValue(), C[i].solutionValue());
      }
    }
  }
}
