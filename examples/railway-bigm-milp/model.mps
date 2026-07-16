*SENSE:Minimize
NAME          railway_bigm
ROWS
 N  OBJ
 G  release_A
 E  completion_A
 G  release_B
 E  completion_B
 G  release_C
 E  completion_C
 G  release_D
 E  completion_D
 G  seq_A_before_B
 G  seq_B_before_A
 G  seq_A_before_C
 G  seq_C_before_A
 G  seq_A_before_D
 G  seq_D_before_A
 G  seq_B_before_C
 G  seq_C_before_B
 G  seq_B_before_D
 G  seq_D_before_B
 G  seq_C_before_D
 G  seq_D_before_C
COLUMNS
    C_A       completion_A   1.000000000000e+00
    C_A       OBJ        1.000000000000e+00
    C_B       completion_B   1.000000000000e+00
    C_B       OBJ        2.000000000000e+00
    C_C       completion_C   1.000000000000e+00
    C_C       OBJ        1.000000000000e+00
    C_D       completion_D   1.000000000000e+00
    C_D       OBJ        3.000000000000e+00
    t_A       release_A   1.000000000000e+00
    t_A       completion_A  -1.000000000000e+00
    t_A       seq_A_before_B  -1.000000000000e+00
    t_A       seq_B_before_A   1.000000000000e+00
    t_A       seq_A_before_C  -1.000000000000e+00
    t_A       seq_C_before_A   1.000000000000e+00
    t_A       seq_A_before_D  -1.000000000000e+00
    t_A       seq_D_before_A   1.000000000000e+00
    t_B       release_B   1.000000000000e+00
    t_B       completion_B  -1.000000000000e+00
    t_B       seq_A_before_B   1.000000000000e+00
    t_B       seq_B_before_A  -1.000000000000e+00
    t_B       seq_B_before_C  -1.000000000000e+00
    t_B       seq_C_before_B   1.000000000000e+00
    t_B       seq_B_before_D  -1.000000000000e+00
    t_B       seq_D_before_B   1.000000000000e+00
    t_C       release_C   1.000000000000e+00
    t_C       completion_C  -1.000000000000e+00
    t_C       seq_A_before_C   1.000000000000e+00
    t_C       seq_C_before_A  -1.000000000000e+00
    t_C       seq_B_before_C   1.000000000000e+00
    t_C       seq_C_before_B  -1.000000000000e+00
    t_C       seq_C_before_D  -1.000000000000e+00
    t_C       seq_D_before_C   1.000000000000e+00
    t_D       release_D   1.000000000000e+00
    t_D       completion_D  -1.000000000000e+00
    t_D       seq_A_before_D   1.000000000000e+00
    t_D       seq_D_before_A  -1.000000000000e+00
    t_D       seq_B_before_D   1.000000000000e+00
    t_D       seq_D_before_B  -1.000000000000e+00
    t_D       seq_C_before_D   1.000000000000e+00
    t_D       seq_D_before_C  -1.000000000000e+00
    MARK      'MARKER'                 'INTORG'
    y_A_B     seq_A_before_B  -2.100000000000e+01
    y_A_B     seq_B_before_A   2.100000000000e+01
    MARK      'MARKER'                 'INTEND'
    MARK      'MARKER'                 'INTORG'
    y_A_C     seq_A_before_C  -2.100000000000e+01
    y_A_C     seq_C_before_A   2.100000000000e+01
    MARK      'MARKER'                 'INTEND'
    MARK      'MARKER'                 'INTORG'
    y_A_D     seq_A_before_D  -2.100000000000e+01
    y_A_D     seq_D_before_A   2.100000000000e+01
    MARK      'MARKER'                 'INTEND'
    MARK      'MARKER'                 'INTORG'
    y_B_C     seq_B_before_C  -2.100000000000e+01
    y_B_C     seq_C_before_B   2.100000000000e+01
    MARK      'MARKER'                 'INTEND'
    MARK      'MARKER'                 'INTORG'
    y_B_D     seq_B_before_D  -2.100000000000e+01
    y_B_D     seq_D_before_B   2.100000000000e+01
    MARK      'MARKER'                 'INTEND'
    MARK      'MARKER'                 'INTORG'
    y_C_D     seq_C_before_D  -2.100000000000e+01
    y_C_D     seq_D_before_C   2.100000000000e+01
    MARK      'MARKER'                 'INTEND'
RHS
    RHS       release_A   0.000000000000e+00
    RHS       completion_A   5.000000000000e+00
    RHS       release_B   2.000000000000e+00
    RHS       completion_B   3.000000000000e+00
    RHS       release_C   1.000000000000e+00
    RHS       completion_C   4.000000000000e+00
    RHS       release_D   4.000000000000e+00
    RHS       completion_D   2.000000000000e+00
    RHS       seq_A_before_B  -1.500000000000e+01
    RHS       seq_B_before_A   4.000000000000e+00
    RHS       seq_A_before_C  -1.500000000000e+01
    RHS       seq_C_before_A   5.000000000000e+00
    RHS       seq_A_before_D  -1.500000000000e+01
    RHS       seq_D_before_A   3.000000000000e+00
    RHS       seq_B_before_C  -1.700000000000e+01
    RHS       seq_C_before_B   5.000000000000e+00
    RHS       seq_B_before_D  -1.700000000000e+01
    RHS       seq_D_before_B   3.000000000000e+00
    RHS       seq_C_before_D  -1.600000000000e+01
    RHS       seq_D_before_C   3.000000000000e+00
BOUNDS
 BV BND       y_A_B   
 BV BND       y_A_C   
 BV BND       y_A_D   
 BV BND       y_B_C   
 BV BND       y_B_D   
 BV BND       y_C_D   
ENDATA
