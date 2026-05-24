\* railway_bigm *\
Minimize
OBJ: C_A + 2 C_B + C_C + 3 C_D
Subject To
completion_A: C_A - t_A = 5
completion_B: C_B - t_B = 3
completion_C: C_C - t_C = 4
completion_D: C_D - t_D = 2
release_A: t_A >= 0
release_B: t_B >= 2
release_C: t_C >= 1
release_D: t_D >= 4
seq_A_before_B: - t_A + t_B - 21 y_A_B >= -15
seq_A_before_C: - t_A + t_C - 21 y_A_C >= -15
seq_A_before_D: - t_A + t_D - 21 y_A_D >= -15
seq_B_before_A: t_A - t_B + 21 y_A_B >= 4
seq_B_before_C: - t_B + t_C - 21 y_B_C >= -17
seq_B_before_D: - t_B + t_D - 21 y_B_D >= -17
seq_C_before_A: t_A - t_C + 21 y_A_C >= 5
seq_C_before_B: t_B - t_C + 21 y_B_C >= 5
seq_C_before_D: - t_C + t_D - 21 y_C_D >= -16
seq_D_before_A: t_A - t_D + 21 y_A_D >= 3
seq_D_before_B: t_B - t_D + 21 y_B_D >= 3
seq_D_before_C: t_C - t_D + 21 y_C_D >= 3
Binaries
y_A_B
y_A_C
y_A_D
y_B_C
y_B_D
y_C_D
End
