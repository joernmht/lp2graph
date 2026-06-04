# Codec pipeline validation

End-to-end validation of the deterministic **text ⇄ graph ⇄ MILP**
pipeline (see [`docs/text-graph-interface.md`](../../../docs/text-graph-interface.md)).

For every instance in [`instances/`](./instances), `run.py` executes the
full loop

```
formulation JSON --latex--> LaTeX --parse--> model --ground+solve--> objective
```

and checks four things:

1. **codec round-trip** — the model reconstructed from LaTeX has the same
   canonical normal form as the original, and the LaTeX is a fixed point;
2. **pipeline-solve == direct-solve** — solving the model reconstructed
   *from LaTeX* gives the same objective as solving the JSON directly;
3. **cross-solver agreement** — CBC, HiGHS (and Gurobi, if licensed) return
   the same objective (determinism, not a solver artifact);
4. **known optimum** — the objective equals an independently established
   reference value.

## Run it

```bash
python3 run.py          # writes results/codec_pipeline_results.json
```

It self-bootstraps `PYTHONPATH` from the repo `src/` and the vendored
solver deps in `../.deps`.

## Cases

| Instance | Model | Optimum | Reference |
|----------|-------|--------:|-----------|
| `assignment_4x4` | linear assignment | 13 | brute-force matching |
| `bigm_ordering_4` | big-M disjunctive ordering | 30 | closed form |
| `fixed_sequence_4` | sequential timetabling LP | 18 | closed form |
| `pesp_2events` | PESP cyclic timetabling | 1 | closed form |
| `time_indexed_4x4` | time-indexed set packing | 4 | closed form |

Each instance file also records its `expected_optimum` and a prose
`optimum_source`, so the reference is auditable.

## Paper anchors

`results/codec_pipeline_results.json` additionally records the published /
benchmark optima proven by the sibling [`run_experiments.py`](../scripts/run_experiments.py)
harness for corpus models of the same structural classes the pipeline
handles: **timtab1 = 764772** (MIPLIB PESP cyclic timetabling) and
**marcotallone maintenance scheduling = 3913.47** (big-M time-indexed).
