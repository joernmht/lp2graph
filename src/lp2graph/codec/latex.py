r"""Reversible LaTeX codec for the canonical model.

The emitted document has two parts:

1. A ``%@`` *annotation header* — LaTeX comments carrying the metadata
   that has no algebraic surface form (ids, names, descriptions, index
   ``ordered``/``cyclic`` flags, parameter kinds, variable domains/roles,
   constraint kinds/domain-classes, objective combination). These lines
   are invisible when the document is typeset.

2. An ``align`` *body* — genuine paper-style LaTeX: ``\mathcal`` index
   sets, ``\sum`` aggregations, ``\forall`` quantifiers, ``\le``/``\ge``,
   big-M terms, ``\left| \cdot \right|`` for absolute values, and so on.
   The algebra alone determines the solvable model.

The parser reconstructs the structured model from the body using the
*symbol table* declared in the header: because every variable and
parameter is declared with its index shape, a natural subscripted symbol
like ``t_{j}`` or ``x_{i,t}`` is unambiguously resolved to a referent of
the right kind with the right index-family bindings.

Grammar of a body term (one summand)::

    term      := ['-'|'+'] [numfactor] [aggreg] [coef '\cdot'] referent
    aggreg    := '\sum_{' binder (',' binder)* '}'
               | '\left|' ... '\right|'                 (abs)
               | '\max\left(' ... '\right)' | '\min\left(' ... '\right)'
               | '\mathbb{1}\left[' ... '\right]'       (indicator)
    binder    := ident '\in' '\mathcal{' SET '}'
    numfactor := number | '\frac{' number '}{' number '}'
    coef      := number | numfrac | symbol ['_{' expr (',' expr)* '}']
    referent  := symbol ['_{' expr (',' expr)* '}'] | number
    symbol    := letter | '\mathit{' name '}'
    expr      := ident ['-'|'+' integer]                (index, optional offset)

The parser additionally accepts author spellings the emitter never
produces, each resolved *exactly* or refused with a named error:

- ``\leq``/``\geq``/``\leqslant``/``\geqslant`` as row comparators.
- A chained same-direction inequality row ``l \le e \le u`` becomes two
  constraints named ``<name>_lo`` and ``<name>_up`` sharing the row's
  quantifiers (mixed-direction or equality chains are refused).
- A subscripted coefficient ``w_{e} \cdot x_{e}`` resolves to the bare
  parameter name when the written indices match what grounding will use
  (the referent's bindings, or the unique in-scope binder/quantifier
  index per declared shape slot); any other indexing is refused.
- ``\frac{a}{b}`` with numeric arguments and a terminating decimal value
  folds into the term's numeric coefficient; every other ``\frac`` is
  refused by name (declare a ratio parameter instead).
- Trailing ``^{...}``/``_{...}``/juxtaposed material after a referent's
  subscript is refused by name — nothing is dropped silently.

See :mod:`lp2graph.codec` for the round-trip guarantees.
"""

from __future__ import annotations

import re
from typing import Any

from lp2graph.core.model import (
    Binding,
    ConstraintTemplate,
    Formulation,
    Index,
    Objective,
    Parameter,
    Quantifier,
    QuantifierWhere,
    Term,
    VariableTemplate,
)

SCHEMA = "0.1.0"

_CMP_OUT = {"le": r"\le", "ge": r"\ge", "eq": "="}
_RESTR_OUT = {
    "ne_other": r"\neq",
    "lt_other": "<",
    "le_other": r"\leq",
    "gt_other": ">",
    "ge_other": r"\geq",
    "ordered_pair": r"\prec",
}
_RESTR_IN = {v: k for k, v in _RESTR_OUT.items()}

# ===========================================================================
# Emitter
# ===========================================================================


def to_canonical_latex(f: Formulation) -> str:
    """Render ``f`` as a reversible, paper-style LaTeX document."""
    lines: list[str] = []
    a = lines.append

    a("% lp2graph canonical LaTeX")
    a(f"% Reversible with lp2graph.codec.from_canonical_latex (schema {SCHEMA}).")
    a(f"%@ meta id={f.id} family={f.family} schema={SCHEMA}")
    a(f"%@ name :: {_oneline(f.name)}")
    if f.description:
        a(f"%@ desc :: {_oneline(f.description)}")
    if f.tags:
        a(f"%@ tags :: {' | '.join(f.tags)}")
    if f.provenance is not None:
        prov = f.provenance
        for key, val in (
            ("source", prov.source),
            ("reference", prov.reference),
            ("author", prov.author),
            ("date", prov.date),
        ):
            if val:
                a(f"%@ prov {key} :: {_oneline(val)}")
    for idx in f.indices:
        a(
            f"%@ index {idx.name} ordered={int(idx.ordered)} "
            f"cyclic={int(idx.cyclic)} :: {_oneline(idx.description)}"
        )
    for p in f.parameters:
        a(
            f"%@ param {p.name} shape={_shape_tok(p.shape)} kind={p.kind} "
            f"domain={p.domain_class or '-'} :: {_oneline(p.description)}"
        )
    for v in f.variables:
        a(
            f"%@ var {v.name} shape={_shape_tok(v.shape)} domain={v.domain} "
            f"role={v.role} drole={v.domain_role or '-'} "
            f"lo={_num_tok(v.lower)} hi={_num_tok(v.upper)} "
            f":: {_oneline(v.description)}"
        )
    if f.objective is not None:
        o = f.objective
        a(
            f"%@ obj sense={o.sense} name={_tok(o.name)} "
            f"combination={o.combination} :: {_oneline(o.description)}"
        )
    for c in f.constraints:
        ind = "-"
        if c.indicator is not None:
            ind = f"{c.indicator.binary}@{c.indicator.active_value}"
        a(
            f"%@ con {c.name} kind={c.kind} domain={c.domain_class or '-'} "
            f"indicator={ind} :: {_oneline(c.description)}"
        )

    a(r"\begin{align}")
    if f.objective is not None:
        sense = r"\min" if f.objective.sense == "min" else r"\max"
        body = _emit_sum(f.objective.terms)
        a(rf"  {sense}\quad & {body} \tag{{{_tag(f.objective.name)}}} \\")
    for c in f.constraints:
        lhs = _emit_sum(c.lhs)
        rhs = _emit_sum(c.rhs) if c.rhs else "0"
        cmp = _CMP_OUT[c.comparator]
        quant = _emit_quantifiers(c.quantifiers)
        qpart = rf" \qquad {quant}" if quant else ""
        a(rf"  & {lhs} {cmp} {rhs}{qpart} \tag{{{_tag(c.name)}}} \\")
    a(r"\end{align}")
    return "\n".join(lines) + "\n"


def _emit_sum(terms: tuple[Term, ...]) -> str:
    if not terms:
        return "0"
    parts: list[str] = []
    for i, t in enumerate(terms):
        sign, body = _emit_term(t)
        if i == 0:
            parts.append(("- " + body) if sign < 0 else body)
        else:
            parts.append(("- " if sign < 0 else "+ ") + body)
    return " ".join(parts)


def _emit_term(t: Term) -> tuple[int, str]:
    """Return ``(display_sign, body_without_sign)``."""
    sign = t.sign
    if t.ref_kind == "literal":
        val = t.coefficient if t.coefficient is not None else 1
        if isinstance(val, (int, float)) and val < 0:
            sign = -sign
            val = -val
        return sign, _num(val)

    base = _sym(t.ref)
    sub = _subscript(t.bindings)
    body = base + sub

    coef = t.coefficient
    if isinstance(coef, str):
        body = f"{_sym(coef)} \\cdot {body}"
    elif isinstance(coef, (int, float)) and coef != 1:
        if coef < 0:
            sign = -sign
            coef = -coef
        body = f"{_num(coef)} \\cdot {body}"

    op = t.operator
    if op == "sum":
        body = rf"\sum_{{{_emit_sum_sub(t)}}} {body}"
    elif op == "abs":
        body = rf"\left| {body} \right|"
    elif op == "max":
        body = rf"\max\left( {body} \right)"
    elif op == "min":
        body = rf"\min\left( {body} \right)"
    elif op == "indicator":
        body = rf"\mathbb{{1}}\left[ {body} \right]"
    elif op == "modulo":
        body = rf"\left( {body} \right)"
    return sign, body


def _emit_sum_sub(t: Term) -> str:
    r"""Render the ``\sum`` binder set, pairing each summed family with a
    binder variable taken from the term's bindings."""
    remaining = list(t.bindings)
    binders: list[tuple[str, str]] = []
    for fam in t.operator_over:
        pick = next((b for b in remaining if b.index == fam), None)
        if pick is not None:
            remaining.remove(pick)
            binders.append((pick.expr, fam))
        else:
            binders.append((fam.lower(), fam))
    return ", ".join(rf"{expr} \in {_set(fam)}" for expr, fam in binders)


def _emit_quantifiers(quantifiers: tuple[Quantifier, ...]) -> str:
    if not quantifiers:
        return ""
    parts = [rf"\forall {q.index} \in {_set(q.over)}" for q in quantifiers]
    extra: list[str] = []
    for q in quantifiers:
        if q.restriction != "none":
            extra.append(f"{q.index} {_RESTR_OUT[q.restriction]} {q.restriction_other}")
        if q.where is not None:
            extra.append(f"{_sym(q.where.parameter)}_{{{q.index}}} = {_where_val(q.where.equals)}")
    return ",\\; ".join(parts + extra)


# --- emit helpers ----------------------------------------------------------


def _sym(name: str) -> str:
    if re.fullmatch(r"[A-Za-z]", name):
        return name
    return r"\mathit{" + name.replace("_", r"\_") + "}"


def _set(name: str) -> str:
    return r"\mathcal{" + name.replace("_", r"\_") + "}"


def _subscript(bindings: tuple[Binding, ...]) -> str:
    if not bindings:
        return ""
    return "_{" + ",".join(b.expr for b in bindings) + "}"


def _num(x: float | int | str) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, bool):
        return str(int(x))
    if float(x).is_integer():
        return str(int(x))
    return repr(x)


def _tag(name: str) -> str:
    return name.replace("_", r"\_")


def _oneline(s: str) -> str:
    return " ".join(s.split())


def _tok(s: str) -> str:
    """A space-free token for ``key=value`` annotations; '-' marks empty."""
    s = s.strip()
    if s == "":
        return "-"
    return s


def _shape_tok(shape: tuple[str, ...]) -> str:
    return ",".join(shape) if shape else "-"


def _num_tok(x: float | None) -> str:
    return "-" if x is None else _num(x)


def _where_val(v: bool | int | float | str) -> str:
    if isinstance(v, bool):
        return r"\mathrm{true}" if v else r"\mathrm{false}"
    if isinstance(v, (int, float)):
        return _num(v)
    return r"\mathrm{" + str(v) + "}"


# ===========================================================================
# Parser
# ===========================================================================


class _SymTab:
    def __init__(self) -> None:
        self.var_shape: dict[str, tuple[str, ...]] = {}
        self.param_shape: dict[str, tuple[str, ...]] = {}

    def kind(self, name: str) -> str:
        if name in self.var_shape:
            return "variable"
        if name in self.param_shape:
            return "parameter"
        return "literal"

    def shape(self, name: str) -> tuple[str, ...]:
        if name in self.var_shape:
            return self.var_shape[name]
        return self.param_shape.get(name, ())


def from_canonical_latex(text: str) -> Formulation:
    """Parse a document produced by :func:`to_canonical_latex` back into a
    :class:`Formulation`. Deterministic — no model in the loop."""
    ann = _parse_annotations(text)
    sym = _SymTab()
    for name, info in ann["param"].items():
        sym.param_shape[name] = info["shape"]
    for name, info in ann["var"].items():
        sym.var_shape[name] = info["shape"]

    body_rows = _body_rows(text)
    objective = None
    constraints: list[ConstraintTemplate] = []
    for row in body_rows:
        name, kind = _row_tag(row)
        if kind == "objective":
            objective = _parse_objective_row(row, ann, sym)
        else:
            constraints.extend(_parse_constraint_rows(row, name, ann, sym))

    meta = ann["meta"]
    kwargs: dict[str, object] = {
        "id": meta["id"],
        "name": ann["name"],
        "family": meta["family"],
        "description": ann.get("desc", ""),
        "tags": tuple(ann.get("tags", ())),
        "indices": tuple(
            Index(name=n, description=i["desc"], ordered=i["ordered"], cyclic=i["cyclic"])
            for n, i in ann["index"].items()
        ),
        "parameters": tuple(
            Parameter(
                name=n,
                description=i["desc"],
                shape=i["shape"],
                kind=i["kind"],
                domain_class=i["domain"],
            )
            for n, i in ann["param"].items()
        ),
        "variables": tuple(
            VariableTemplate(
                name=n,
                description=i["desc"],
                shape=i["shape"],
                domain=i["domain"],
                role=i["role"],
                domain_role=i["drole"],
                lower=i["lo"],
                upper=i["hi"],
            )
            for n, i in ann["var"].items()
        ),
        "constraints": tuple(constraints),
        "objective": objective,
    }
    if "prov" in ann:
        from lp2graph.core.model import Provenance

        kwargs["provenance"] = Provenance(**ann["prov"])
    return Formulation(**kwargs)


# --- annotation parsing ----------------------------------------------------


def _parse_annotations(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {"index": {}, "param": {}, "var": {}, "con": {}}
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("%@"):
            continue
        line = line[2:].strip()
        if "::" in line:
            head, desc = line.split("::", 1)
        else:
            head, desc = line, None
        head = head.strip()
        desc = desc.strip() if desc is not None else None
        toks = head.split()
        rec = toks[0]
        if rec == "meta":
            out["meta"] = _kv(toks[1:])
        elif rec == "name":
            out["name"] = desc or ""
        elif rec == "desc":
            out["desc"] = desc or ""
        elif rec == "tags":
            out["tags"] = tuple(t.strip() for t in (desc or "").split("|") if t.strip())
        elif rec == "prov":
            out.setdefault("prov", {})[toks[1]] = desc or ""
        elif rec == "index":
            kv = _kv(toks[2:])
            out["index"][toks[1]] = {
                "ordered": kv.get("ordered") == "1",
                "cyclic": kv.get("cyclic") == "1",
                "desc": desc or "",
            }
        elif rec == "param":
            kv = _kv(toks[2:])
            out["param"][toks[1]] = {
                "shape": _shape(kv.get("shape", "-")),
                "kind": kv.get("kind", "scalar"),
                "domain": _dash(kv.get("domain", "-")),
                "desc": desc or "",
            }
        elif rec == "var":
            kv = _kv(toks[2:])
            out["var"][toks[1]] = {
                "shape": _shape(kv.get("shape", "-")),
                "domain": kv.get("domain", "continuous"),
                "role": kv.get("role", "primary"),
                "drole": _dash(kv.get("drole", "-")),
                "lo": _numopt(kv.get("lo", "-")),
                "hi": _numopt(kv.get("hi", "-")),
                "desc": desc or "",
            }
        elif rec == "obj":
            kv = _kv(toks[1:])
            out["obj"] = {
                "sense": kv.get("sense", "min"),
                "name": _untok(kv.get("name", "objective")),
                "combination": kv.get("combination", "sum"),
                "desc": desc or "",
            }
        elif rec == "con":
            kv = _kv(toks[2:])
            out["con"][toks[1]] = {
                "kind": kv.get("kind", "linear"),
                "domain": _dash(kv.get("domain", "-")),
                "indicator": _dash(kv.get("indicator", "-")),
                "desc": desc or "",
            }
    return out


def _kv(toks: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in toks:
        if "=" in t:
            k, v = t.split("=", 1)
            out[k] = v
    return out


def _dash(v: str) -> str | None:
    return None if v == "-" else v


def _untok(v: str) -> str:
    return "" if v == "-" else v.replace(" ", " ")


def _shape(v: str) -> tuple[str, ...]:
    if v == "-" or v == "":
        return ()
    return tuple(v.split(","))


def _numopt(v: str) -> float | None:
    if v == "-":
        return None
    return float(v)


# --- body row parsing ------------------------------------------------------


def _body_rows(text: str) -> list[str]:
    m = re.search(r"\\begin\{align\}(.*?)\\end\{align\}", text, re.DOTALL)
    if not m:
        return []
    inner = m.group(1)
    rows = [r.strip() for r in inner.split(r"\\")]
    return [r for r in rows if r and not r.startswith("%")]


def _row_tag(row: str) -> tuple[str, str]:
    m = re.search(r"\\tag\{(.*?)\}", row)
    name = m.group(1).replace(r"\_", "_") if m else ""
    body = row[: m.start()] if m else row
    if r"\min" in body or r"\max" in body:
        return name, "objective"
    return name, "constraint"


def _strip_tag(row: str) -> str:
    return re.sub(r"\\tag\{.*?\}", "", row).strip()


def _parse_objective_row(row: str, ann: dict[str, Any], sym: _SymTab) -> Objective:
    info = ann.get("obj", {})
    body = _strip_tag(row).replace("&", " ")
    body = re.sub(r"\\min\\quad|\\max\\quad|\\min|\\max|\\quad", " ", body).strip()
    terms = _parse_term_sum(body, "objective", sym, {})
    return Objective(
        sense=info.get("sense", "min"),
        name=info.get("name", "objective"),
        description=info.get("desc", ""),
        combination=info.get("combination", "sum"),
        terms=tuple(terms),
    )


def _parse_constraint_rows(
    row: str, name: str, ann: dict[str, Any], sym: _SymTab
) -> list[ConstraintTemplate]:
    """Parse one align row into one constraint — or two, for a chained
    same-direction inequality ``l \\le e \\le u`` (``<name>_lo``/``<name>_up``,
    both inheriting the row's quantifiers)."""
    info = ann["con"].get(name, {})
    body = _strip_tag(row)
    # Split body from quantifier on \qquad.
    qpart = ""
    if r"\qquad" in body:
        body, qpart = body.split(r"\qquad", 1)
    body = body.replace("&", " ").strip()

    quantifiers = _parse_quantifiers(qpart)
    env = {q.index: q.over for q in quantifiers}

    rels = _find_relations(body)
    if not rels:
        raise ValueError(f"no comparator in constraint body: {body!r}")
    if len(rels) > 2:
        raise ValueError(
            f"chained relation with {len(rels)} comparators is not supported: {body!r}"
        )

    indicator = None
    ind = info.get("indicator")
    if ind:
        binary, active = ind.split("@")
        from lp2graph.core.model import IndicatorTrigger

        indicator = IndicatorTrigger(binary=binary, active_value=int(active))

    def build(cname: str, cmp: str, lhs_s: str, rhs_s: str) -> ConstraintTemplate:
        return ConstraintTemplate(
            name=cname,
            description=info.get("desc", ""),
            quantifiers=tuple(quantifiers),
            comparator=cmp,
            lhs=tuple(_parse_term_sum(lhs_s, "lhs", sym, env)),
            rhs=tuple(_parse_term_sum(rhs_s, "rhs", sym, env)),
            kind=info.get("kind", "linear"),
            domain_class=info.get("domain"),
            indicator=indicator,
        )

    if len(rels) == 1:
        (start, end, cmp) = rels[0]
        return [build(name, cmp, body[:start], body[end:])]

    (s1, e1, cmp1), (s2, e2, cmp2) = rels
    if cmp1 != cmp2 or cmp1 == "eq":
        raise ValueError(f"mixed-direction or equality chained relation is not supported: {body!r}")
    lo_seg, mid_seg, hi_seg = body[:s1], body[e1:s2], body[e2:]
    if cmp1 == "le":
        return [
            build(f"{name}_lo", "le", lo_seg, mid_seg),
            build(f"{name}_up", "le", mid_seg, hi_seg),
        ]
    return [
        build(f"{name}_up", "ge", lo_seg, mid_seg),
        build(f"{name}_lo", "ge", mid_seg, hi_seg),
    ]


#: Comparator spellings accepted in a row body, longest first so ``\leq``
#: is never read as ``\le`` followed by a stray ``q`` (and ``\left`` is
#: never read as ``\le``): every match requires a non-letter follower.
_CMP_TOKENS: tuple[tuple[str, str], ...] = (
    (r"\leqslant", "le"),
    (r"\geqslant", "ge"),
    (r"\leq", "le"),
    (r"\geq", "ge"),
    (r"\le", "le"),
    (r"\ge", "ge"),
)


def _find_relations(body: str) -> list[tuple[int, int, str]]:
    """All top-level comparator occurrences as ``(start, end, cmp)``."""
    out: list[tuple[int, int, str]] = []
    depth = 0
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0 and ch == "=":
            out.append((i, i + 1, "eq"))
        elif depth == 0 and ch == "\\":
            for tok, cmp in _CMP_TOKENS:
                if body.startswith(tok, i):
                    follower = body[i + len(tok) : i + len(tok) + 1]
                    if not follower.isalpha():
                        out.append((i, i + len(tok), cmp))
                        i += len(tok)
                        break
            else:
                i += 1
            continue
        i += 1
    return out


# --- term-sum parsing ------------------------------------------------------


def _parse_term_sum(body: str, role: str, sym: _SymTab, env: dict[str, str]) -> list[Term]:
    body = body.strip()
    if body == "" or body == "0":
        # An explicit "0" RHS carries no terms.
        if body == "0":
            return []
        return []
    pieces = _split_signed(body)
    terms = []
    for sign, text in pieces:
        t = _parse_term(text, sign, role, sym, env)
        if t is not None:
            terms.append(t)
    return terms


def _split_signed(body: str) -> list[tuple[int, str]]:
    """Split a term sum at top-level +/-, returning (sign, term_text)."""
    out: list[tuple[int, str]] = []
    depth = 0
    sign = 1
    cur: list[str] = []
    i = 0
    started = False
    while i < len(body):
        ch = body[i]
        if ch == "{":
            depth += 1
            cur.append(ch)
        elif ch == "}":
            depth -= 1
            cur.append(ch)
        elif depth == 0 and ch in "+-" and started and not _is_exponent(body, i):
            out.append((sign, "".join(cur).strip()))
            sign = -1 if ch == "-" else 1
            cur = []
        elif depth == 0 and ch in "+-" and not started:
            sign = -1 if ch == "-" else 1
        else:
            if not ch.isspace():
                started = True
            cur.append(ch)
        i += 1
    tail = "".join(cur).strip()
    if tail:
        out.append((sign, tail))
    return out


def _is_exponent(body: str, i: int) -> bool:
    return i > 0 and body[i - 1] in "eE" and (i >= 2 and body[i - 2].isdigit())


_NUM_RE = re.compile(r"-?\d+(\.\d+)?")
_FRAC_NUM_RE = re.compile(r"\\frac\s*\{\s*(-?\d+(?:\.\d+)?)\s*\}\s*\{\s*(-?\d+(?:\.\d+)?)\s*\}")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
#: One ``binder \in \mathcal{SET}`` pair inside a ``\sum`` subscript.
_BINDER_PAIR_RE = re.compile(r"([A-Za-z_]\w*)\s*\\in\s*\\mathcal\{([\w\\]+)\}")


def _frac_value(num: str, den: str, origin: str) -> float:
    """Exact value of a numeric ``\\frac`` — refused unless the decimal
    terminates (an author could equivalently have written the decimal)."""
    from fractions import Fraction

    d = Fraction(den)
    if d == 0:
        raise ValueError(f"\\frac with zero denominator: {origin!r}")
    frac = Fraction(num) / d
    rest = frac.denominator
    for p in (2, 5):
        while rest % p == 0:
            rest //= p
    if rest != 1:
        raise ValueError(
            f"\\frac value {origin!r} has no terminating decimal; it cannot be folded "
            "into a numeric coefficient exactly (declare a ratio parameter instead)"
        )
    return float(frac)


def _take_numeric_prefactor(text: str) -> tuple[float | None, str]:
    """Consume a leading numeric factor (``\\frac{a}{b}`` always; a plain
    number only when a ``\\sum`` follows, so literal terms stay literal)."""
    m = _FRAC_NUM_RE.match(text)
    if m:
        value = _frac_value(m.group(1), m.group(2), m.group(0))
        rest = text[m.end() :].lstrip()
        if rest.startswith(r"\cdot"):
            rest = rest[len(r"\cdot") :].lstrip()
        return value, rest
    m2 = re.match(r"(-?\d+(?:\.\d+)?)\s+(?=\\sum_)", text)
    if m2:
        return float(m2.group(1)), text[m2.end() :]
    return None, text


def _parse_term(text: str, sign: int, role: str, sym: _SymTab, env: dict[str, str]) -> Term | None:
    text = text.strip()
    if not text:
        return None
    operator = "none"
    operator_over: tuple[str, ...] = ()

    pre, text = _take_numeric_prefactor(text)
    if pre is not None and not text:
        # A bare numeric fraction is a literal term.
        text = _num(pre)
        pre = None

    # Aggregation wrappers.
    if text.startswith(r"\sum_"):
        sub, rest = _take_braced(text[len(r"\sum_") :])
        operator = "sum"
        operator_over = tuple(_setnames(sub))
        env = {**env, **{v: f.replace(r"\_", "_") for v, f in _BINDER_PAIR_RE.findall(sub)}}
        text = rest.strip()
    elif text.startswith(r"\left|"):
        operator = "abs"
        text = _between(text, r"\left|", r"\right|")
    elif text.startswith(r"\max\left("):
        operator = "max"
        text = _between(text, r"\max\left(", r"\right)")
    elif text.startswith(r"\min\left("):
        operator = "min"
        text = _between(text, r"\min\left(", r"\right)")
    elif text.startswith(r"\mathbb{1}\left["):
        operator = "indicator"
        text = _between(text, r"\mathbb{1}\left[", r"\right]")

    # A numeric factor may also sit after the wrapper: \sum_{..} \frac{1}{2} x.
    pre2, text = _take_numeric_prefactor(text)
    if pre2 is not None:
        pre = pre2 if pre is None else pre * pre2

    # Coefficient / referent.
    coef_s: str | None = None
    if r"\cdot" in text:
        raw_coef, ref_s = text.split(r"\cdot", 1)
        coef_s = raw_coef.strip()
        text = ref_s.strip()

    text = text.strip()
    if r"\frac" in text:
        raise ValueError(
            f"\\frac in referent position is not in the canonical grammar: {text!r} "
            "(only numeric fractions with a terminating decimal fold into a "
            "coefficient; declare a ratio parameter for symbolic ratios)"
        )
    if _NUM_RE.fullmatch(text):
        value = float(text)
        if coef_s is not None:
            cv = _resolve_coef(coef_s, "_const", [], sym, env)
            if isinstance(cv, str):
                raise ValueError(
                    f"symbolic coefficient {cv!r} on the literal {text!r} is not in the "
                    "canonical grammar (write the parameter as the referent instead)"
                )
            value *= cv
        if pre is not None:
            value *= pre
        if value.is_integer():
            value = int(value)
        return Term(
            ref="_const",
            ref_kind="literal",
            coefficient=value,
            sign=sign,
            role=role,
            operator=operator,
            operator_over=operator_over,
        )

    name, bindings = _parse_referent(text, sym)
    coefficient: float | str | None = 1
    if coef_s is not None:
        coefficient = _resolve_coef(coef_s, name, bindings, sym, env)
    if pre is not None:
        if isinstance(coefficient, str):
            raise ValueError(
                f"cannot fold the numeric factor {pre!r} into the symbolic coefficient "
                f"{coefficient!r} exactly (the canonical Term carries one coefficient; "
                "introduce a scaled parameter instead)"
            )
        value = pre * float(coefficient if coefficient is not None else 1)
        coefficient = int(value) if value.is_integer() else value
    return Term(
        ref=name,
        ref_kind=sym.kind(name),
        bindings=tuple(bindings),
        coefficient=coefficient,
        sign=sign,
        role=role,
        operator=operator,
        operator_over=operator_over,
    )


def _resolve_coef(
    coef_s: str,
    ref_name: str,
    ref_bindings: list[Binding],
    sym: _SymTab,
    env: dict[str, str],
) -> float | str:
    """Resolve the text left of ``\\cdot`` to a numeric value or a bare
    parameter name.

    A subscripted coefficient like ``w_{e}`` resolves to ``w`` only when
    the written indices are exactly what grounding will use for ``w``
    (:func:`lp2graph.solve.grounder._coef_value`): the referent's binding
    exprs when the shapes coincide, or the unique in-scope binder or
    quantifier index of each declared shape family otherwise. Anything
    else is refused by name — never silently reindexed.
    """
    s = coef_s.strip()
    if _NUM_RE.fullmatch(s):
        v = float(s)
        return int(v) if v.is_integer() else v
    m = _FRAC_NUM_RE.fullmatch(s)
    if m:
        return _frac_value(m.group(1), m.group(2), s)
    if r"\frac" in s:
        raise ValueError(
            f"symbolic \\frac coefficient {s!r} is not in the canonical grammar "
            "(declare a ratio parameter instead)"
        )
    base, sub, rest = _split_scripted(s)
    if rest.strip():
        raise ValueError(
            f"coefficient {s!r}: trailing {rest.strip()!r} after the subscript is not "
            "in the canonical grammar (superscript indices must be resolved upstream)"
        )
    name = _read_sym(base)
    if not sub:
        return name
    exprs = [" ".join(e.split()) for e in _split_top_commas(sub)]
    shape = sym.param_shape.get(name)
    if name in sym.var_shape:
        raise ValueError(
            f"subscripted coefficient {s!r} names the variable {name!r}: a "
            "variable-times-variable product is nonlinear and outside the grammar"
        )
    if shape is None:
        raise ValueError(
            f"subscripted coefficient {s!r} is not a declared parameter "
            f"(declare {name!r} with an explicit shape)"
        )
    if len(shape) != len(exprs):
        raise ValueError(
            f"subscripted coefficient {s!r} writes {len(exprs)} indices but "
            f"{name!r} is declared with shape {shape!r}"
        )
    ref_exprs = [" ".join(b.expr.split()) for b in ref_bindings]
    if exprs == ref_exprs and tuple(shape) == tuple(sym.shape(ref_name)):
        return name
    fam_vars: dict[str, set[str]] = {}
    for var, fam in env.items():
        fam_vars.setdefault(fam, set()).add(var)
    for b in ref_bindings:
        if _IDENT_RE.fullmatch(b.expr):
            fam_vars.setdefault(b.index, set()).add(b.expr)
    if all(fam_vars.get(fam) == {expr} for fam, expr in zip(shape, exprs, strict=True)):
        return name
    raise ValueError(
        f"subscripted coefficient {s!r} cannot be resolved exactly: its indices must "
        f"match the referent's bindings {ref_exprs!r} or the unique in-scope index of "
        f"each declared family in shape {shape!r} (in scope: {sorted(env)!r})"
    )


def _parse_referent(text: str, sym: _SymTab) -> tuple[str, list[Binding]]:
    base, sub, rest = _split_scripted(text)
    if rest and not re.fullmatch(r"[\s.,;:]*", rest):
        raise ValueError(
            f"referent {text!r}: trailing {rest.strip()!r} after the subscript is not "
            "part of the canonical grammar (superscript indices and juxtaposed factors "
            "must be resolved upstream; nothing is dropped silently)"
        )
    name = _read_sym(base)
    bindings: list[Binding] = []
    if sub:
        exprs = _split_top_commas(sub)
        shape = sym.shape(name)
        for pos, expr in enumerate(exprs):
            if pos < len(shape):
                fam = shape[pos]
            else:
                fam = expr.strip()
                if not _IDENT_RE.fullmatch(fam):
                    raise ValueError(
                        f"referent {name!r}: subscript {expr.strip()!r} cannot serve as "
                        f"an index family (declare {name!r} with an explicit shape; "
                        "constant and offset subscripts resolve only against a "
                        "declared shape)"
                    )
            bindings.append(Binding(index=fam, expr=expr.strip(), offset=_offset(expr)))
    return name, bindings


def _split_scripted(text: str) -> tuple[str, str, str]:
    """Split ``base_{sub}rest`` — ``sub`` and ``rest`` are ``''`` when absent."""
    m = re.search(r"_\{", text)
    if not m:
        return text.strip(), "", ""
    base = text[: m.start()]
    sub, rest = _take_braced(text[m.end() - 1 :])  # include the '{'
    return base.strip(), sub, rest


def _read_sym(s: str) -> str:
    s = s.strip()
    m = re.fullmatch(r"\{([^{}]*)\}", s)
    if m:
        # A redundant brace group around a symbol ({a}_{k}) is transparent.
        return _read_sym(m.group(1))
    m = re.fullmatch(r"\\mathit\{(.*)\}", s)
    if m:
        return m.group(1).replace(r"\_", "_")
    m = re.fullmatch(r"\\mathrm\{(.*)\}", s)
    if m:
        return m.group(1).replace(r"\_", "_")
    return s


def _offset(expr: str) -> int:
    m = re.search(r"[+-]\s*\d+\s*$", expr.replace(" ", ""))
    return int(m.group(0).replace(" ", "")) if m else 0


# --- quantifier parsing ----------------------------------------------------


def _parse_quantifiers(qpart: str) -> list[Quantifier]:
    qpart = qpart.replace("&", " ").strip()
    if not qpart:
        return []
    qpart = qpart.replace(r"\forall", "")
    clauses = [c.strip() for c in _split_clauses(qpart) if c.strip()]
    quants: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    extras: list[str] = []
    for cl in clauses:
        m = re.match(r"^(\w+)\s*\\in\s*\\mathcal\{([\w\\]+)\}$", cl)
        if m:
            idx = m.group(1)
            over = m.group(2).replace(r"\_", "_")
            quants[idx] = {"over": over, "restriction": "none", "other": None, "where": None}
            order.append(idx)
        else:
            extras.append(cl)
    for cl in extras:
        _apply_extra(cl, quants)
    return [
        Quantifier(
            index=i,
            over=quants[i]["over"],
            restriction=quants[i]["restriction"],
            restriction_other=quants[i]["other"],
            where=quants[i]["where"],
        )
        for i in order
    ]


def _apply_extra(cl: str, quants: dict[str, dict[str, Any]]) -> None:
    # where-clause:  sym_{idx} = value
    mw = re.match(r"^(.*?)_\{(\w+)\}\s*=\s*(.+)$", cl)
    if mw and mw.group(1).strip() not in ("",):
        idx = mw.group(2)
        if idx in quants:
            param = _read_sym(mw.group(1).strip())
            quants[idx]["where"] = QuantifierWhere(
                parameter=param, equals=_parse_where_val(mw.group(3).strip())
            )
            return
    # restriction:  idx OP other
    for tok, restr in _RESTR_IN.items():
        m = re.match(rf"^(\w+)\s*{re.escape(tok)}\s*(\w+)$", cl)
        if m:
            idx = m.group(1)
            if idx in quants:
                quants[idx]["restriction"] = restr
                quants[idx]["other"] = m.group(2)
            return


def _parse_where_val(s: str) -> bool | int | float | str:
    if s == r"\mathrm{true}":
        return True
    if s == r"\mathrm{false}":
        return False
    m = re.fullmatch(r"\\mathrm\{(.*)\}", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


# --- low-level string helpers ----------------------------------------------


def _take_braced(s: str) -> tuple[str, str]:
    """Given a string starting with ``{``, return (inner, remainder)."""
    assert s.startswith("{"), s
    depth = 0
    for i, ch in enumerate(s):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[1:i], s[i + 1 :]
    raise ValueError(f"unbalanced braces: {s!r}")


def _between(text: str, open_t: str, close_t: str) -> str:
    inner = text[len(open_t) :]
    if inner.endswith(close_t):
        inner = inner[: -len(close_t)]
    else:
        idx = inner.rfind(close_t)
        if idx >= 0:
            inner = inner[:idx]
    return inner.strip()


def _setnames(sub: str) -> list[str]:
    return [m.replace(r"\_", "_") for m in re.findall(r"\\mathcal\{([\w\\]+)\}", sub)]


def _split_top_commas(s: str) -> list[str]:
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in s:
        if ch == "{":
            depth += 1
            cur.append(ch)
        elif ch == "}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return [x.strip() for x in out]


def _split_clauses(s: str) -> list[str]:
    """Split quantifier clauses on top-level commas (``\\;`` already in text)."""
    s = s.replace(r"\;", ",")
    return _split_top_commas(s)


__all__ = ["from_canonical_latex", "to_canonical_latex"]
