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

6. **`distribute_param` no longer fires behind a sign or a factor** (issue
   #67): `- M (1 - x)` became `- M - M x`. The structural reader handles those
   rows exactly.

## Consequences

- Rule table `rewrite-2026.11.0` (50 rules). On the lab corpus the rows that
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
