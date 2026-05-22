# v1.0 acceptance criteria

`lp2graph` reaches v1.0 when every box below is checked. v0.1 ships
the foundation; the items here are explicit so contributors and users
can see how far the project has to go.

## Catalog

- [ ] All 18 formulations from the original taxonomy are present and
      pass validation, view derivation, and rendering.
- [ ] At least 5 objective-focused formulations beyond the original
      taxonomy (we ship 3 in v0.1).
- [ ] Every formulation has a one-paragraph description, provenance
      metadata, and at least one cited reference.

## Tests

- [ ] 100 % branch coverage on `lp2graph.core/`.
- [ ] Snapshot (golden) tests for every render output and every
      structural metric on every catalog formulation.
- [ ] Fuzz tests on the schema validator: random documents that
      almost-validate exercise every error path.
- [ ] Performance benchmarks for ground-view derivation at
      `cardinality = {32, 64, 128}` for each catalog formulation.

## Exports

- [ ] PyG export round-trips for every catalog formulation.
- [ ] DGL export round-trips for every catalog formulation.
- [ ] LaTeX export renders every catalog formulation to a compileable
      `align*` block.
- [ ] **Pyomo export emits compileable, runnable code** (not stubs)
      for every LP and MIP formulation. PESP/big-M tightening
      strategies documented.
- [ ] JuMP export at parity with Pyomo.

## Viewer

- [ ] Side-by-side comparison grid renders all 18+ formulations.
- [ ] Ground cardinality slider with reactive re-derivation.
- [ ] Metric panel with all structural metrics and presence flags.
- [ ] Hosted live at `<docs-site>/viewer/`.

## Documentation

- [ ] Every public function has a docstring (true at v0.1 for the
      surface that exists; v1.0 adds the items above and keeps this
      true).
- [ ] Every ADR has status `accepted` (or `superseded`); no
      `proposed` ADRs at release.
- [ ] Tutorial notebook reproduces every figure in the upstream
      research paper.

## Release engineering

- [ ] CI green on Linux + macOS + Windows for Python 3.11, 3.12,
      3.13.
- [ ] Schema versioning policy documented and tested with at least
      one migration scenario.
- [ ] `pip install lp2graph[all]` succeeds in a fresh environment.
- [ ] PyPI release pipeline triggered automatically on tag.

## Open questions resolved

Each `open-question` issue has a decision, an ADR, and a code change
implementing it (or a clear statement that it stays open by design).
