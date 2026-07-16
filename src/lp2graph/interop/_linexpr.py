"""A tiny deterministic linear-expression parser shared by the text formats.

Parses the affine subset every modeling language writes for small linear
models: signed terms of the form ``3 x``, ``3*x``, ``x``, ``4.5``,
``2e-1 * x``, plus JuMP-style implicit multiplication ``4x``. Anything
else (parentheses, division by a variable, nonlinear products) raises
:class:`~lp2graph.interop._grounded.InteropError` — a lossy parse is
never returned.
"""

from __future__ import annotations

import re

from lp2graph.interop._grounded import InteropError

__all__ = ["parse_linexpr"]

_TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<number>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)"
    r"|(?P<ident>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op>[+\-*/])"
    r"|(?P<bad>\S)"
    r")"
)


def _tokens(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:  # only trailing whitespace remains
            break
        pos = m.end()
        for kind in ("number", "ident", "op", "bad"):
            val = m.group(kind)
            if val is not None:
                if kind == "bad":
                    raise InteropError(f"unexpected character {val!r} in expression {text!r}")
                out.append((kind, val))
                break
    return out


def parse_linexpr(text: str) -> tuple[dict[str, float], float]:
    """Parse an affine expression into ``(variable coefficients, constant)``.

    Coefficients of repeated variables accumulate; variable order in the
    returned dict is first appearance (insertion order).
    """
    toks = _tokens(text)
    coefs: dict[str, float] = {}
    const = 0.0
    i = 0
    n = len(toks)
    if n == 0:
        return coefs, const
    while i < n:
        sign = 1.0
        # 1. Leading signs (any run of +/-).
        while i < n and toks[i][0] == "op" and toks[i][1] in "+-":
            if toks[i][1] == "-":
                sign = -sign
            i += 1
        if i >= n:
            raise InteropError(f"dangling sign at end of expression {text!r}")
        # 2. One term: number, ident, number*ident, number ident, ident*number.
        kind, val = toks[i]
        if kind == "number":
            coef = float(val)
            i += 1
            if i < n and toks[i][0] == "op" and toks[i][1] in "*/":
                op = toks[i][1]
                i += 1
                if i >= n:
                    raise InteropError(f"dangling {op!r} in expression {text!r}")
                nk, nv = toks[i]
                if nk == "ident":
                    if op == "/":
                        raise InteropError(f"division by variable {nv!r} in {text!r}")
                    _add(coefs, nv, sign * coef)
                    i += 1
                elif nk == "number":
                    const += sign * (coef * float(nv) if op == "*" else coef / float(nv))
                    i += 1
                else:
                    raise InteropError(f"cannot parse term after {op!r} in {text!r}")
            elif i < n and toks[i][0] == "ident":
                _add(coefs, toks[i][1], sign * coef)  # implicit product: "4x"
                i += 1
            else:
                const += sign * coef
        elif kind == "ident":
            var = val
            coef = 1.0
            i += 1
            if i < n and toks[i][0] == "op" and toks[i][1] in "*/":
                op = toks[i][1]
                i += 1
                if i >= n or toks[i][0] != "number":
                    what = toks[i][1] if i < n else "end of input"
                    raise InteropError(f"nonlinear or malformed term near {what!r} in {text!r}")
                coef = float(toks[i][1]) if op == "*" else 1.0 / float(toks[i][1])
                i += 1
            _add(coefs, var, sign * coef)
        else:
            raise InteropError(f"cannot parse expression {text!r} near {val!r}")
    return coefs, const


def _add(coefs: dict[str, float], var: str, value: float) -> None:
    coefs[var] = coefs.get(var, 0.0) + value
