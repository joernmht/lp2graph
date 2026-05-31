# Extracted MILP/LP Corpus — Index

**17 repositories · 28 formulations · 224 constraint entries · 123 decision-variable entries.**  
Generated from the per-repo JSON files; see [`METHODOLOGY.md`](./METHODOLOGY.md) for process & design decisions.

All 17 repositories were processed — **none skipped** (all licenses confirmed permissive). Each row is one `model_id`; `n_constraints`/`n_variables` are entry counts (not instances). Every constraint/objective in every JSON carries verified source line references (407 refs checked, 0 missing, 0 out-of-bounds).

| # | Repo | model_id | Area | Solver | License | n_constraints | n_variables | Confidence | JSON |
|---|------|----------|------|--------|---------|:--:|:--:|------------|------|
| 1 | Gurobi/modeling-examples | `railway-dispatching-mip` | railway-rescheduling | Gurobi | Apache-2.0 | 9 | 4 | high | [json](./Gurobi__modeling-examples.json) |
| 2 | INFORMSJoC/2021.0094 | `backup-rolling-stock-allocation-timetable-rescheduling-2stage-stochastic` | railway-rescheduling | CPLEX 12.80 | MIT | 11 | 6 | medium | [json](./INFORMSJoC__2021.0094.json) |
| 3 | INFORMSJoC/2023.0391 | `erst-event-based-rsto-milp` | railway-rescheduling | CPLEX 12.80 | MIT | 10 | 6 | medium | [json](./INFORMSJoC__2023.0391.json) |
| 4 | INFORMSJoC/2023.0391 | `prst-path-based-set-partitioning-master` | railway-rescheduling | CPLEX 12.80 | MIT | 4 | 1 | medium | [json](./INFORMSJoC__2023.0391.json) |
| 5 | iitis/quantum-stochastic-optimization-railways | `light-rail-rescheduling-ilp` | railway-rescheduling | CPLEX (docplex; classical baseline), w | CC0-1.0 | 5 | 2 | high | [json](./iitis__quantum-stochastic-optimization-railways.json) |
| 6 | iitis/railways_HOBO | `single-track-dispatching-qubo-hobo` | railway-rescheduling | D-Wave (quantum annealer / LeapHybridS | Apache-2.0 | 7 | 2 | high | [json](./iitis__railways_HOBO.json) |
| 7 | IBMDecisionOptimization/Decision-Optimization-with-CPLEX-samples | `timtab1-cyclic-timetabling-milp` | railway-timetabling | CPLEX | Apache-2.0 | 1 | 2 | medium | [json](./IBMDecisionOptimization__Decision-Optimization-with-CPLEX-samples.json) |
| 8 | cda-tum/mtct | `gen-po-moving-block-routing-milp` | railway-timetabling | Gurobi | MIT | 15 | 11 | medium-high | [json](./cda-tum__mtct.json) |
| 9 | cda-tum/mtct | `vss-generation-timetable-milp` | railway-timetabling | Gurobi | MIT | 21 | 20 | medium-high | [json](./cda-tum__mtct.json) |
| 10 | lintim/openlintim | `delay-management-dm2-ip` | railway-timetabling | Gurobi, CPLEX, XPRESS (+ OSS fallback) | MIT | 4 | 3 | high | [json](./lintim__openlintim.json) |
| 11 | lintim/openlintim | `line-planning-cost-model` | railway-timetabling | Gurobi, CPLEX, XPRESS (+ OSS fallback) | MIT | 2 | 1 | high | [json](./lintim__openlintim.json) |
| 12 | lintim/openlintim | `line-planning-direct-travelers` | railway-timetabling | Gurobi, CPLEX, XPRESS (+ OSS fallback) | MIT | 6 | 3 | high | [json](./lintim__openlintim.json) |
| 13 | lintim/openlintim | `periodic-timetabling-pesp-ip` | railway-timetabling | Gurobi, CPLEX, XPRESS (+ OSS fallback) | MIT | 2 | 2 | high | [json](./lintim__openlintim.json) |
| 14 | lintim/openlintim | `vehicle-scheduling-ip` | railway-timetabling | Gurobi, CPLEX, XPRESS (+ OSS fallback) | MIT | 2 | 1 | high | [json](./lintim__openlintim.json) |
| 15 | marcotallone/railway-scheduling | `maintenance-scheduling-milp` | railway-timetabling | Gurobi | MIT | 16 | 5 | high | [json](./marcotallone__railway-scheduling.json) |
| 16 | sma-software/openviriato.algorithm-platform.showcase.spot | `spot-pesp-passenger-timetabling` | railway-timetabling | Gurobi | Apache-2.0 | 11 | 9 | high | [json](./sma-software__openviriato.algorithm-platform.showcase.spot.json) |
| 17 | INFORMSJoC/2023.0014 | `c-path-odmts-adoption-aware-design` | transport-operations | Gurobi | MIT | 12 | 8 | medium | [json](./INFORMSJoC__2023.0014.json) |
| 18 | INFORMSJoC/2023.0014 | `p-path-odmts-adoption-aware-design` | transport-operations | Gurobi | MIT | 13 | 7 | medium | [json](./INFORMSJoC__2023.0014.json) |
| 19 | INFORMSJoC/2023.0404 | `mevrsptw-set-partitioning-master-lp` | transport-operations | CPLEX (master LP) + jORLib branch-and- | MIT | 6 | 1 | high | [json](./INFORMSJoC__2023.0404.json) |
| 20 | INFORMSJoC/2024.0698 | `duty-deviation-conversion-lp` | transport-operations | CPLEX 22.1 | MIT | 3 | 3 | medium | [json](./INFORMSJoC__2024.0698.json) |
| 21 | INFORMSJoC/2024.0698 | `mdvsp-ts-arc-flow-time-expanded` | transport-operations | CPLEX 22.1 | MIT | 5 | 2 | medium | [json](./INFORMSJoC__2024.0698.json) |
| 22 | INFORMSJoC/2024.0698 | `mdvsp-ts-set-partitioning-master` | transport-operations | CPLEX 22.1 | MIT | 4 | 1 | medium | [json](./INFORMSJoC__2024.0698.json) |
| 23 | Yinwenxu-1212/crewScheduling | `crew-pairing-set-covering-master` | transport-operations | Gurobi | MIT | 3 | 3 | high | [json](./Yinwenxu-1212__crewScheduling.json) |
| 24 | mesenrj/transit-network-optimization | `transit-line-config-passenger-assignment-milp` | transport-operations | Xpress | MIT | 9 | 3 | high | [json](./mesenrj__transit-network-optimization.json) |
| 25 | michieluithetbroek/A-MDVRP | `amdvrp-branch-and-cut-2index` | transport-operations | CPLEX (branch-and-cut, model A) and Gu | MIT | 11 | 2 | high | [json](./michieluithetbroek__A-MDVRP.json) |
| 26 | michieluithetbroek/A-MDVRP | `amdvrp-compact-flow-mtz` | transport-operations | CPLEX (branch-and-cut, model A) and Gu | MIT | 17 | 5 | high | [json](./michieluithetbroek__A-MDVRP.json) |
| 27 | romain-montagne/vrpy | `vrp-pricing-subproblem-lp` | transport-operations | CBC / CoinOR (also supports CPLEX, Gur | MIT | 11 | 5 | high | [json](./romain-montagne__vrpy.json) |
| 28 | romain-montagne/vrpy | `vrp-set-covering-master` | transport-operations | CBC / CoinOR (also supports CPLEX, Gur | MIT | 4 | 5 | high | [json](./romain-montagne__vrpy.json) |

## Skips

**None.** All 17 repositories existed and carried unchanged permissive licenses at extraction time (2026-05-31).

## Discrepancies & anomalies vs. the input table

These deviations were found during extraction and are recorded faithfully (the input table's pre-identified fields were not blindly trusted where the code disagreed):

- **iitis/railways_HOBO (#3 in the input table)** — listed as "CPLEX (classical baseline)", but the repository contains **no MILP/ILP at all**: it is a pure **QUBO/HOBO** codebase (D-Wave Ocean only; no CPLEX/docplex/pulp/gurobi). No linear model was fabricated. The genuinely-linear underlying operational conditions (objective + 7 constraints) are recorded, each annotated with its quadratic-penalty encoding; the cubic track-occupancy condition is quadratized via Rosenberg with auxiliary binaries. Solver field reflects reality (D-Wave). Treat this entry as *structurally* MILP-like but *not* a linear program.
- **mesenrj/transit-network-optimization (#14)** — listed as "Python (Jupyter)"; the actual MILP lives in **FICO Xpress Mosel** (`xpress/transit-network-optimization.mos`). The Python/notebook files only generate instance data and run a heuristic. Language recorded as Mosel.
- **IBMDecisionOptimization/…CPLEX-samples (#9)** — README declares Apache-2.0 but the referenced `LICENSE.txt` is **absent upstream**. Not skipped (license unchanged, just undelivered); the README license statement was copied into the sidecar with a note. The model (`timtab1.mps`) is the anonymous MIPLIB instance: structure is certain (397 vars, 171 equality rows, −60 PESP period coefficient) but per-row real-world **semantics are not recoverable** and are set to `null` rather than invented.

## Cross-cutting extraction notes

- **No written math ⇒ extractor-assigned symbols (confidence `medium`).** The INFORMSJoC replication repos (2021.0094, 2023.0014, 2023.0391, 2024.0698) ship run-instructions only, no formulation. Math symbols are the extractor's mapping of code identifiers; the exact code names are preserved in every `source_symbol`. DOIs for these were taken verbatim from each README (not inferred); where a DOI appears nowhere in-repo it is `null` (Gurobi webinar example, crewScheduling, OpenLinTim, mtct's multi-paper span, the Mosel transit model, both iitis baselines).
- **Column-generation repos — pricing subproblems not faked as LPs.** Where the pricing/separation step is an algorithm (labeling DP / ESPPRC / min-cut), it is documented in the model's `notes` and **not** emitted as a fabricated LP: vrpy, crewScheduling, INFORMSJoC/2023.0404, INFORMSJoC/2024.0698. Where a subproblem *is* a genuine LP in code (vrpy's optional `subproblem_lp.py`), it is captured as its own `models[]` entry.
- **Lazy/dynamic cuts (A-MDVRP)** — statically-added cuts are listed as constraints; exponential cut families separated in callbacks are recorded by name + source path in `notes`, with closed-form LaTeX only for the two families (rounded-capacity SEC, Laporte SEC) that have an explicit lhs; algorithmically-built cuts are not given fabricated static expressions.
- **Nonlinear-under-settings (cda-tum/mtct)** — both models become MIQCP / PWL-MINLP under certain toggles (braking curves, product linearizations); flagged in `notes`. The non-MILP A* solver was excluded.
- **PESP modulo representation (openviriato SPOT)** — the cycle-wrap variable `k` is declared *binary* (single-period-wrap simplification), not a general integer modulo variable; flagged for downstream parsers.
