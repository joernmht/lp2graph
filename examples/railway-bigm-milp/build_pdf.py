"""Assemble railway_bigm_milp.pdf -- one representation (taxonomy) per page.

    pip install reportlab
    python build_pdf.py

Reads the model files in this folder so the PDF always matches the sources.
"""
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Preformatted, PageBreak,
    KeepInFrame, Table, TableStyle, HRFlowable,
)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "railway_bigm_milp.pdf")

MARGIN = 14 * mm
FRAME_W = A4[0] - 2 * MARGIN
FRAME_H = A4[1] - 2 * MARGIN
ACCENT = colors.HexColor("#0B5394")
GREY = colors.HexColor("#666666")

ss = getSampleStyleSheet()
st_title = ParagraphStyle("title", parent=ss["Title"], fontSize=22, leading=26, textColor=ACCENT)
st_h = ParagraphStyle("h", parent=ss["Heading1"], fontSize=16, leading=19, textColor=ACCENT, spaceAfter=2)
st_sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=9.5, leading=12, textColor=GREY)
st_body = ParagraphStyle("body", parent=ss["Normal"], fontSize=10, leading=14)
st_math = ParagraphStyle("math", parent=ss["Code"], fontName="Courier", fontSize=10, leading=14)
st_code = ParagraphStyle("code", parent=ss["Code"], fontName="Courier", fontSize=6.9, leading=8.2)


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def page(flowables):
    """Force one logical unit onto a single page (shrink to fit)."""
    return [KeepInFrame(FRAME_W, FRAME_H - 2, flowables, mode="shrink"), PageBreak()]


def header(title, subtitle):
    return [
        Paragraph(title, st_h),
        Paragraph(subtitle, st_sub),
        HRFlowable(width="100%", thickness=1, color=ACCENT, spaceBefore=3, spaceAfter=8),
    ]


def code_page(title, subtitle, filename):
    return page(header(title, subtitle) + [Preformatted(read(filename).rstrip("\n"), st_code)])


# ---------------------------------------------------------------- page 1: cover
story = []
cover = [
    Spacer(1, 40),
    Paragraph("Railway Single-Track Sequencing", st_title),
    Paragraph("A big-M MILP, in every modelling dialect", st_h),
    Spacer(1, 14),
    Paragraph(
        "A small, complete, self-contained mixed-integer linear program from railway "
        "operations. Four trains share one single-track segment (a tunnel / bridge / "
        "passing-loop bottleneck): at most one train may occupy it at a time and a minimum "
        "headway must elapse between trains. Decide each train's entry time so as to "
        "minimise the total weighted clearance time. The mutual exclusion of any two trains "
        "is a disjunction, linearised with the classic <b>big-M</b> technique.",
        st_body,
    ),
    Spacer(1, 10),
    Paragraph("The same model appears on the following pages as a complete problem "
              "statement, the mathematical model, LaTeX, markdown/mathcal, and ~20 "
              "executable encodings &mdash; one representation per page.", st_body),
    Spacer(1, 16),
    Paragraph("Optimal objective: &nbsp; <b>&#931;<sub>i</sub> w<sub>i</sub>&middot;C<sub>i</sub> = 66</b> "
              "&nbsp;&nbsp; (order B &#8594; D &#8594; C &#8594; A) &mdash; verified with "
              "CBC, GLPK and OR-Tools CP-SAT.", st_body),
]
story += page(cover)

# ------------------------------------------------- page 2: problem description
inst = [["train", "release r_i", "running p_i", "weight w_i"],
        ["A", "0", "5", "1"], ["B", "2", "3", "2"],
        ["C", "1", "4", "1"], ["D", "4", "2", "3"]]
opt = [["train", "enter t_i", "clear C_i", "w_i*C_i"],
       ["B", "2", "5", "10"], ["D", "6", "8", "24"],
       ["C", "9", "13", "13"], ["A", "14", "19", "19"],
       ["", "", "total", "66"]]


def mk_table(data):
    t = Table(data, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF3FA")]),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


desc = header("1 &middot; Complete problem description", "sets, parameters, variables, data, optimum")
desc += [
    Paragraph("<b>Sets.</b> N = {A,B,C,D} (trains); P = {(i,j) : i &lt; j} (ordered index pairs).", st_body),
    Paragraph("<b>Parameters.</b> r_i release (earliest entry); p_i running time on the segment; "
              "w_i priority weight; h minimum headway (= 1); big-M constant "
              "M = max_i r_i + &#931;_i p_i + (|N|-1)&middot;h = 4 + 14 + 3 = <b>21</b>.", st_body),
    Paragraph("<b>Variables.</b> t_i &#8805; 0 entry time; C_i &#8805; 0 clearance time; "
              "y_ij &#8712; {0,1} with y_ij = 1 iff train i enters before train j.", st_body),
    Spacer(1, 8),
    Paragraph("Data instance", st_sub), mk_table(inst),
    Spacer(1, 10),
    Paragraph("Optimal schedule", st_sub), mk_table(opt),
]
story += page(desc)

# --------------------------------------------------- page 3: mathematical model
MATH = """minimize    sum_{i in N}  w_i * C_i           (weighted clearance)

subject to
  (release)     t_i  >=  r_i                             for all i in N
  (clearance)   C_i   =  t_i + p_i                       for all i in N
  (i before j)  t_j  >=  t_i + p_i + h - M*(1 - y_ij)    for all (i,j) in P
  (j before i)  t_i  >=  t_j + p_j + h - M*y_ij          for all (i,j) in P
  (domains)     t_i >= 0,   C_i >= 0,   y_ij in {0,1}

Why big-M works
  For a pair (i,j) the binary y_ij selects which of the two mutually
  exclusive sequencing constraints is enforced:
    * y_ij = 1 : "i before j" is tight  (t_j >= t_i + p_i + h),
                 "j before i" becomes  t_i >= t_j + p_j + h - M  (vacuous).
    * y_ij = 0 : symmetric -- the other constraint binds.
  M must be large enough never to cut a feasible schedule, yet as small as
  possible so the LP relaxation stays tight.  M = 21 is exactly tight here."""
model_pg = header("2 &middot; The mathematical model", "the MILP, solver-independent")
model_pg += [Preformatted(MATH, st_math)]
story += page(model_pg)

# --------------------------------------------------------- page 4: LaTeX source
story += code_page("3 &middot; LaTeX", "problem.tex &mdash; standalone, compile with pdflatex", "problem.tex")

# ----------------------------------------------- page 5: markdown / mathcal
MD = read("README.md")
# take the model section (markdown with \\mathcal) so the page stays readable
start = MD.find("## 2. The mathematical model")
end = MD.find("## 3.")
md_excerpt = MD[start:end].strip() if start != -1 and end != -1 else MD
story += page(header("4 &middot; Markdown / mathcal", "README.md model section (GitHub/MathJax)")
              + [Preformatted(md_excerpt, st_code)])

# ----------------------------------------------------- pages 6..N: the encodings
encodings = [
    ("5 &middot; PuLP", "model_pulp.py &mdash; Python", "model_pulp.py"),
    ("6 &middot; Gurobi (gurobipy)", "model_gurobi.py &mdash; Python", "model_gurobi.py"),
    ("7 &middot; Pyomo", "model_pyomo.py &mdash; Python", "model_pyomo.py"),
    ("8 &middot; Google OR-Tools", "model_ortools.py &mdash; Python (MPSolver)", "model_ortools.py"),
    ("9 &middot; Python-MIP", "model_python_mip.py &mdash; Python", "model_python_mip.py"),
    ("10 &middot; CVXPY", "model_cvxpy.py &mdash; Python", "model_cvxpy.py"),
    ("11 &middot; JuMP", "model_jump.jl &mdash; Julia", "model_jump.jl"),
    ("12 &middot; ompr / ROI", "model_ompr.R &mdash; R", "model_ompr.R"),
    ("13 &middot; intlinprog", "model_matlab.m &mdash; MATLAB / Octave", "model_matlab.m"),
    ("14 &middot; OR-Tools (C++)", "model_ortools.cpp &mdash; C++", "model_ortools.cpp"),
    ("15 &middot; OR-Tools (Java)", "ModelOrTools.java &mdash; Java", "ModelOrTools.java"),
    ("16 &middot; AMPL", "model_ampl.mod &mdash; algebraic modelling language", "model_ampl.mod"),
    ("17 &middot; GAMS", "model_gams.gms &mdash; algebraic modelling language", "model_gams.gms"),
    ("18 &middot; GNU MathProg (GMPL)", "model_glpk.mod &mdash; glpsol", "model_glpk.mod"),
    ("19 &middot; ZIMPL", "model_zimpl.zpl &mdash; algebraic modelling language", "model_zimpl.zpl"),
    ("20 &middot; MiniZinc", "model_minizinc.mzn &mdash; constraint/MIP modelling", "model_minizinc.mzn"),
    ("21 &middot; CPLEX LP format", "model.lp &mdash; portable exchange format", "model.lp"),
    ("22 &middot; MPS format", "model.mps &mdash; portable exchange format", "model.mps"),
]
for title, sub, fname in encodings:
    story += code_page(title, sub, fname)

# strip the trailing PageBreak so the last page isn't blank
if story and isinstance(story[-1], PageBreak):
    story.pop()


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(MARGIN, 8 * mm, "lp2graph · examples/railway-bigm-milp · big-M MILP")
    canvas.drawRightString(A4[0] - MARGIN, 8 * mm, "page %d" % doc.page)
    canvas.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                        topMargin=MARGIN, bottomMargin=MARGIN,
                        title="Railway single-track sequencing: a big-M MILP")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("wrote", OUT)
