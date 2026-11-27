# ADR-0018: Rows are read structurally; derived parameters and widening are recorded, never silent

- **Status:** accepted
- **Date:** 2026-11-26

## Context

M1b turned author LaTeX into the canonical grammar with an ordered table of 46
rewrite rules, almost all of them regular expressions over the row text. Regexes
map spellings; they cannot restructure algebra. Measured on the lab corpus
(228 papers, 6,284 candidate rows) the table left 91 % of the rows outside the
grammar, and the residue was structural: a parenthesised sum under a
coefficient, a product three levels deep, a `\sum` whose body is a sum, a
quantifier tail that names a tuple or a range, a term whose coefficient is a
product of two parameters. Each needs the row's tree, not its characters.

Two of those are not spelling at all. The canonical `Term` carries one
coefficient (a number or one parameter name), and the canonical `Quantifier`
binds one letter over one declared family. `\lambda C_k z_k`, `d_k / T`,
`(i, j) \in A` and `i \in I \setminus \{1\}` have no exact spelling in the
grammar. Extending the term schema was decided against; the codec's own error
messages already name the way out ("introduce a scaled parameter", "declare a
ratio parameter", "bind each index over its own family").

## Decision

1. **A structural reader (`mining.ingest.row_canon`) joins the rule table as
   two rules, `row_exact` and `row_widened`.** It lexes one `align` row, parses
   the algebra by recursive descent, proves the row is a *linear* relation over
   the document's declared symbols, and re-emits it in the canonical spelling.
   Every step of `row_exact` is an algebraic identity (distribution, a sum of a
   sum, nested sums merged, a factor moved under a sum, a numeric denominator).
   A row it cannot prove (an undeclared symbol, two variables multiplied, a
   power, any token it has no rule for) is returned unchanged, so the parser
   refuses it by name exactly as before.

2. **A product or ratio of parameters is a derived parameter.** It is data, not
   structure. The reader names it deterministically (`lambda_x_C`, `n2_x_M`,
   `d_over_T`, `sum_p_M_m_H` for a parameter sum under a fraction bar,
   `val_T` for the numeric value of an index over `T`), uses it as the
   coefficient, and the normalizer appends its `%@ param ... :: derived: ...`
   line to the header. Each is one recorded rewrite (`derived_parameter`).
   The header stays opaque to every other rule.

3. **Widening is a rule of its own.** A binder over a restricted, scripted or
   combined set, a tuple, a range, and a tail condition the model has no field
   for are widened to the base families of the letters. This is the
   approximation `restricted_set_widen` already recorded; it is applied only by
   `row_widened`, so the provenance separates exact rows from widened ones.
   Three guards keep widening from producing a different statement:
   - a tail clause is dropped only when every name in it is a declared
     parameter, an index family, a bound letter or a plain word; a statement
     about a variable, or about a symbol nobody declared, is algebra and is
     never dropped;
   - widening that would make two sums over *different* source sets the same
     term is refused (a flow balance would become a tautology);
   - a letter is read as a number (`\sum_t t x_t`) only next to an explicit
     operator and only when this row binds it.

4. **The header may state index letters.** `%@ letter i over=I` is read by M1b
   and ignored by the codec. It tells the script rules which letters are
   indices when no binder in the row says so; a caller feeds it from whatever
   it knows about the paper (the lab: its deterministic index reader).

5. **A mixed chain is a conjunction.** `a = b \le c` and `a \le b \ge c` split
   into consecutive pairs, each with its own comparator, as same-direction
   chains already did. The codec refused them before; nothing about them is
   ambiguous.

6. **A coefficient the term cannot index is read from the referent's
   position.** A canonical coefficient is a bare parameter name whose indices
   are implied (the referent's, or the one letter in scope per family).
   `t_{k-1} x_{i,k}`, `n_{p} z_{p,q}` with two letters of one family in scope
   and a fixed element `t_{0} y_{i,k}` have no such reading. The parameter as
   seen from the referent is still data: it becomes a derived parameter over
   the referent's shape (`t_km1_on_x`). This is exact only while every index
   of the coefficient is one of the referent's own; see point 15 for the two
   cases that are not (amended `rewrite-2026.11.2`).

7. **Piecewise terms are rewritten where, and only where, that is exact.**
   `|e|`, `max(e_1, e_2)`, `min(..)` and an extremum over a binder have no
   canonical spelling beyond the single-term `|c x|`.
   - In a constraint, alone on the convex side of one inequality, they are a
     conjunction: `|e| \le b` is `-b \le e \le b`, `max(e_1, e_2) \le b` is
     the mixed chain `e_1 \le b \ge e_2`, `\max_{i} e_i \le b` quantifies
     the inequality over `i`. An equation with an extremum, or the non-convex
     side, is refused.
   - In an objective that is minimised (or the mirror cases), the term is
     replaced by an explicit auxiliary variable with its defining
     inequalities (`u \ge e`, `u \ge -e`): the standard exact reformulation.
     The variable is a *derived variable* (`aux_<row>_<n>`, role `auxiliary`,
     `derived_variable` rewrite) and its rows follow the objective row under
     tags `<row>_aux<n>_<k>`. A symbolic weight is taken to be non-negative,
     and the variable's description says so. The model that results is
     equivalent to the paper's, not identical to it: it has variables and rows
     the paper does not write, each marked as derived.

8. **Cardinalities and index values are data.** `|S|` over an index family
   (or a labelled or indexed subset) is the derived parameter `card_S`; an
   index letter used as a number next to an explicit operator, in a row that
   binds it, is `val_T`.

9. **In an objective, a `\sum` reaches the terms that need it.** An objective
   is a number, so a term with a free index letter is summed; it is bound by
   the nearest preceding sum that binds that letter
   (`\sum_{i,k} |a_{ik}| + |d_{ik}|`). This is a reading of the notation and
   is recorded as widening.

10. **`distribute_param` no longer fires behind a sign or a factor** (issue
   #67): `- M (1 - x)` became `- M - M x`. The structural reader handles those
   rows exactly.

11. **A case distinction of constants is data** (`rewrite-2026.11.1`). The
   rule `cases_groups` regroups `\begin{cases}` and brace-matrix blocks as
   `\casesof{value}{condition}...` before line breaks are dropped. The reader
   turns the block into one derived parameter `case_<row>_<n>` over the index
   letters its conditions name, when every branch value is free of variables
   and every condition tests index letters and declared data only (the node
   balance `= 1 if i = o, -1 if i = d, 0 otherwise`). A branch that holds a
   variable is a second constraint under another condition, and a condition
   in words (`0 if activity a is maintained`) defines what a variable means:
   both are left to the parser, which refuses them.

12. **A family and a symbol may share a name.** Papers write the periods
   `\mathcal{T}` and the horizon `T`, the time index `t` and the times
   `t_{e,a}`. The canonical model keeps families and symbols in separate
   name spaces, so M1b now does too (`DocContext.families`): in a binder the
   name is the set, between bars its size, as a term the symbol. A letter that
   names a *subscripted* symbol still binds when written bare.

13. **Two restrictions of one set are never widened into one.** The older
   rule `restricted_set_widen` rewrote `\delta^{-}(v)` and `\delta^{+}(v)`
   both to `\delta` before the reader saw them, so the reader's guard
   (point 5) had nothing to compare and a flow balance came out as
   `\sum x - \sum x = 0`. The rule now declines when the same summand is
   summed over two restrictions of one base; the reader then keeps the sets
   apart as their own families (`delta_minus`, `delta_plus`). Found by
   scanning promoted models for cancelling sums (lab
   `scripts/checks/cancelling_sums_check.py`): the hole dated from
   `rewrite-2026.09`.

14. **A sign above a symbol is part of its name.** `overset_base` dropped
   whatever stood above a base, which read `\overset{\leftarrow}{S}` and a
   tilde written as U+02DC as the plain letter. It now drops only annotations
   (words, a brace, an equation reference, anything above a relation). Left
   arrows, dots and breves are accents with their own suffix (`S_lvec`,
   `v_dot`); a sign the table does not know stays in place, so the row is
   refused instead of renamed.

15. **A coefficient that departs from its declaration, or from the referent,
   is a recorded departure** (`rewrite-2026.11.2`; amends point 6).
   - *Written against its declaration*: `v` is declared over `R` and the row
     writes `\sum_{p \in P} v_p x_p`, or `M` is declared with three indices
     and written `M_{i,s}`. Until now such a row was refused by name. The row
     is the evidence at hand: when every index is a letter the row binds, the
     coefficient becomes the derived parameter `v_idx_P` over the families
     the row binds those letters over. A letter nothing binds (a label,
     `f_{L}`) is still refused.
   - *An index from outside the referent*: `d_{i,j} \cdot y` under
     `\forall i, j` with `i` and `j` of one family. The term has no place for
     the two indices and the derived parameter over the referent's shape
     cannot hold them. `2026.11.0` produced it all the same and called the
     row exact, which it is not. The reading is kept, as a departure.

   Both make the row a `row_widened` one and are spelled out in the derived
   parameter's description, so a consumer can drop exactly these rows. The
   same reading applies to a parameter that stands alone as a term. A
   *variable* written against its declaration is never re-declared: two
   variables of one letter would be two unconnected nodes of the model, which
   is a statement about the model and not about its data.

   Callers that audit or repair declarations must see the mismatch, not the
   repair: `normalize_latex(..., redeclare=False)` leaves such symbols as
   written (the lab's declaration rules read shapes off those uses).

16. **An objective stated several times is read from the first statement
   that can be read.** `min Z = Z_1 + d Z_2 = \sum c x + d \sum e y` states
   one objective twice; when the first statement names undeclared parts, the
   next one that holds a variable is taken (never a trailing value).

## Consequences

- Rule table `rewrite-2026.11.2` (54 rules; `2026.11.0` had 52). On the lab corpus the rows that
  parse with their header rose from 9 % to 37 % with the lab's deterministic
  declarations (lab ADR-0026); the reader alone accounts for the first step,
  9 % to 18 %.
- A canonical document is a fixed point: the structural rules compare a row's
  spelling with the emitter's free choices removed and leave an equal row
  alone, and a document that already declares a derived parameter reuses it.
- Derived parameters appear in a model's parameter list. A consumer that counts
  or clusters parameters sees them; their description starts with `derived:`.
- Widened rows are weaker statements than their source, by construction of the
  guard never stronger in a way that merges terms. Whether a widened row counts
  as canonical for a given analysis is the caller's decision; the rewrite log
  carries what it needs to tell them apart.
- Label words (`min`, `max`, `arr`, ...) are a frozen lexicon inside the rule
  resource: with index letters declared in the header, `h_{min}` must not
  split into `m`, `i`, `n`.
