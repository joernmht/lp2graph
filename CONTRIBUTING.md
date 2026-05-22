# Contributing to lp2graph

Thank you for your interest. This project is in alpha; the foundation
is in place and the catalog is in active expansion. Almost every kind
of contribution moves it forward.

## Setup

```bash
git clone https://github.com/joernmht/lp2graph
cd lp2graph
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Day-to-day commands

```bash
ruff check src tests           # lint
ruff format src tests          # format
mypy src/lp2graph              # strict type-check
pytest                         # full suite
pytest --cov=lp2graph          # with coverage
```

CI runs all four on every PR across Linux + macOS for Python 3.11,
3.12, and 3.13. Failures block merge.

## What to contribute

- **A new formulation.** See [`docs/add-a-formulation.md`](docs/add-a-formulation.md).
  Use the `new-formulation` issue template to coordinate first.
- **A new metric.** Add to `lp2graph.metrics`. Pure function,
  deterministic, returns `MetricResult`. Add a test asserting the
  expected value on at least one catalog formulation.
- **An export adapter.** Add to `lp2graph.export`. Lazy framework
  imports. Round-trip test required.
- **A documentation improvement.** Especially welcome for the
  data-model and views docs.
- **An open question.** Look for the `open-question` label. These
  are intentionally unresolved; a thoughtful proposal in an issue is
  more valuable than a quick PR.

## PR expectations

- One logical change per PR. Atomic commits using **Conventional
  Commits** (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`,
  `chore:`).
- Reference the issue: `Closes #123`.
- Update docs when behavior changes.
- Add a test for new behavior. Modify an existing test only when the
  behavior under test has genuinely changed.
- Snapshot test changes need a brief explanation in the PR body.

## Coding standards

- Type-safe everywhere: `mypy --strict` passes from day one. No
  `Any` in public APIs.
- Public functions have docstrings. Module docstrings explain the
  module's purpose.
- Default to writing no comments. Add one when the *why* is
  non-obvious.
- Prefer the smaller change. A bug fix does not need surrounding
  refactoring.

## Versioning

Semantic versioning. Breaking changes require a MAJOR bump and a
migration note in `CHANGELOG.md`. Schema changes follow the policy in
[`docs/adr/0004-schema-versioning.md`](docs/adr/0004-schema-versioning.md).

## License

By submitting code, you agree that your contribution is licensed under
Apache 2.0 (matching the project license). No CLA required.
