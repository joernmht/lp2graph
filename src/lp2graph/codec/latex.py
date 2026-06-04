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

    term      := ['-'|'+'] [aggreg] [coef '\cdot'] referent
    aggreg    := '\sum_{' binder (',' binder)* '}'
               | '\left|' ... '\right|'                 (abs)
               | '\max\left(' ... '\right)' | '\min\left(' ... '\right)'
               | '\mathbb{1}\left[' ... '\right]'       (indicator)
    binder    := ident '\in' '\mathcal{' SET '}'
    coef      := number | symbol
    referent  := symbol ['_{' expr (',' expr)* '}'] | number
    symbol    := letter | '\mathit{' name '}'
    expr      := ident ['-'|'+' integer]                (index, optional offset)

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
    a("% Reversible with lp2graph.codec.from_canonical_latex (schema "
      f"{SCHEMA}).")
    a(f"%@ meta id={f.id} family={f.family} schema={SCHEMA}")
    a(f"%@ name :: {_oneline(f.name)}")
    if f.description:
        a(f"%@ desc :: {_oneline(f.description)}")
    if f.tags:
        a(f"%@ tags :: {' | '.join(f.tags)}")
    if f.provenance is not None:
        prov = f.provenance
        for key, val in (("source", prov.source), ("reference", prov.reference),
                         ("author", prov.author), ("date", prov.date)):
            if val:
                a(f"%@ prov {key} :: {_oneline(val)}")
    for idx in f.indices:
        a(f"%@ index {idx.name} ordered={int(idx.ordered)} "
          f"cyclic={int(idx.cyclic)} :: {_oneline(idx.description)}")
    for p in f.parameters:
        a(f"%@ param {p.name} shape={_shape_tok(p.shape)} kind={p.kind} "
          f"domain={p.domain_class or '-'} :: {_oneline(p.description)}")
    for v in f.variables:
        a(f"%@ var {v.name} shape={_shape_tok(v.shape)} domain={v.domain} "
          f"role={v.role} drole={v.domain_role or '-'} "
          f"lo={_num_tok(v.lower)} hi={_num_tok(v.upper)} "
          f":: {_oneline(v.description)}")
    if f.objective is not None:
        o = f.objective
        a(f"%@ obj sense={o.sense} name={_tok(o.name)} "
          f"combination={o.combination} :: {_oneline(o.description)}")
    for c in f.constraints:
        ind = "-"
        if c.indicator is not None:
            ind = f"{c.indicator.binary}@{c.indicator.active_value}"
        a(f"%@ con {c.name} kind={c.kind} domain={c.domain_class or '-'} "
          f"indicator={ind} :: {_oneline(c.description)}")

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
            extra.append(
                f"{_sym(q.where.parameter)}_{{{q.index}}} = {_where_val(q.where.equals)}"
            )
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
            constraints.append(_parse_constraint_row(row, name, ann, sym))

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
    terms = _parse_term_sum(body, "objective", sym)
    return Objective(
        sense=info.get("sense", "min"),
        name=info.get("name", "objective"),
        description=info.get("desc", ""),
        combination=info.get("combination", "sum"),
        terms=tuple(terms),
    )


def _parse_constraint_row(
    row: str, name: str, ann: dict[str, Any], sym: _SymTab
) -> ConstraintTemplate:
    info = ann["con"].get(name, {})
    body = _strip_tag(row)
    # Split body from quantifier on \qquad.
    qpart = ""
    if r"\qquad" in body:
        body, qpart = body.split(r"\qquad", 1)
    body = body.replace("&", " ").strip()

    cmp, lhs_s, rhs_s = _split_comparison(body)
    lhs = _parse_term_sum(lhs_s, "lhs", sym)
    rhs = _parse_term_sum(rhs_s, "rhs", sym)
    quantifiers = _parse_quantifiers(qpart)

    indicator = None
    ind = info.get("indicator")
    if ind:
        binary, active = ind.split("@")
        from lp2graph.core.model import IndicatorTrigger

        indicator = IndicatorTrigger(binary=binary, active_value=int(active))

    return ConstraintTemplate(
        name=name,
        description=info.get("desc", ""),
        quantifiers=tuple(quantifiers),
        comparator=cmp,
        lhs=tuple(lhs),
        rhs=tuple(rhs),
        kind=info.get("kind", "linear"),
        domain_class=info.get("domain"),
        indicator=indicator,
    )


def _split_comparison(body: str) -> tuple[str, str, str]:
    for tok, cmp in ((r"\le", "le"), (r"\ge", "ge")):
        idx = _find_top(body, tok)
        if idx >= 0:
            return cmp, body[:idx], body[idx + len(tok):]
    idx = _find_top_eq(body)
    if idx >= 0:
        return "eq", body[:idx], body[idx + 1:]
    raise ValueError(f"no comparator in constraint body: {body!r}")


def _find_top(body: str, tok: str) -> int:
    depth = 0
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0 and body.startswith(tok, i):
            # avoid matching \leq/\geq tails when looking for \le/\ge is fine
            return i
        i += 1
    return -1


def _find_top_eq(body: str) -> int:
    depth = 0
    for i, ch in enumerate(body):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0 and ch == "=":
            return i
    return -1


# --- term-sum parsing ------------------------------------------------------


def _parse_term_sum(body: str, role: str, sym: _SymTab) -> list[Term]:
    body = body.strip()
    if body == "" or body == "0":
        # An explicit "0" RHS carries no terms.
        if body == "0":
            return []
        return []
    pieces = _split_signed(body)
    terms = []
    for sign, text in pieces:
        t = _parse_term(text, sign, role, sym)
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


def _parse_term(text: str, sign: int, role: str, sym: _SymTab) -> Term | None:
    text = text.strip()
    if not text:
        return None
    operator = "none"
    operator_over: tuple[str, ...] = ()

    # Aggregation wrappers.
    if text.startswith(r"\sum_"):
        sub, rest = _take_braced(text[len(r"\sum_"):])
        operator = "sum"
        operator_over = tuple(_setnames(sub))
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

    # Coefficient / referent.
    coefficient: float | str | None = 1
    if r"\cdot" in text:
        coef_s, ref_s = text.split(r"\cdot", 1)
        coefficient = _parse_coef(coef_s.strip())
        text = ref_s.strip()

    text = text.strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        value = float(text)
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


def _parse_coef(s: str) -> float | str:
    s = s.strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
        v = float(s)
        return int(v) if v.is_integer() else v
    return _read_sym(s)


def _parse_referent(text: str, sym: _SymTab) -> tuple[str, list[Binding]]:
    base, sub = _split_subscript(text)
    name = _read_sym(base)
    bindings: list[Binding] = []
    if sub:
        exprs = _split_top_commas(sub)
        shape = sym.shape(name)
        for pos, expr in enumerate(exprs):
            fam = shape[pos] if pos < len(shape) else (exprs and expr)
            bindings.append(
                Binding(index=fam, expr=expr.strip(), offset=_offset(expr))
            )
    return name, bindings


def _split_subscript(text: str) -> tuple[str, str]:
    m = re.search(r"_\{", text)
    if not m:
        return text.strip(), ""
    base = text[: m.start()]
    sub, _ = _take_braced(text[m.end() - 1:])  # include the '{'
    return base.strip(), sub


def _read_sym(s: str) -> str:
    s = s.strip()
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
                return s[1:i], s[i + 1:]
    raise ValueError(f"unbalanced braces: {s!r}")


def _between(text: str, open_t: str, close_t: str) -> str:
    inner = text[len(open_t):]
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
