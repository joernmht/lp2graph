# ADR-0014: Every extra must resolve on every supported Python

- **Status:** accepted
- **Date:** 2026-09-21

## Context

`pyproject.toml` advertises `requires-python = ">=3.11"` with trove classifiers
for 3.11, 3.12 and 3.13, and the CI matrix tests all three on Linux and macOS.
It also declared:

```toml
dgl = ["dgl>=2.0", "torch>=2.0"]
all = [..., "dgl>=2.0", ...]     # "Every non-commercial optional backend"
```

DGL's PyPI presence does not support that claim. Checked 2026-09-21:

| Release | Python tags | Platforms | sdist |
|---|---|---|---|
| 2.0.0 | cp37–cp311 | macos, manylinux aarch64, win | no |
| 2.1.0 | cp38–cp312 | macos, manylinux x86_64/aarch64 | no |
| 2.2.0 | cp38–cp312 | macos only | no |
| 2.2.1 (latest) | cp38–cp312 | **win_amd64 only** | no |

No 2.x release publishes a `cp313` wheel, and **none publishes an sdist**, so
there is nothing for pip to fall back to and build. The last upload was
2024-05-13 — the project is effectively dormant on PyPI.

Because pip resolves an extra atomically, one unresolvable member takes the
whole extra down. So `pip install "lp2graph[all]"` **failed outright on Python
3.13 on every platform**, denying the user `networkx`, `pyomo`, `pulp`,
`highspy`, `nltk` and `hdbscan` as well — none of which has any problem. The
failure surfaces as a bare "no matching distribution found for dgl", which a
user cannot distinguish from a typo, a proxy problem or an outage.

The knowledge was already in the repo, in the wrong place: `ci.yml`'s
`backends` job explains that it avoids `[all]` partly because "dgl wheels lag
new Python releases". A CI comment does not help someone running `pip install`.

`all` already had the right principle stated for a different case — `gurobi` is
excluded because it is commercial and licence-gated, "so `pip install
"lp2graph[all]"` must not fail for a user without a licence". That principle
simply had not been applied to platform availability.

## Decision

**An extra must be installable on every environment `requires-python` claims,
or declare its limit in metadata.**

1. Requirements that cannot resolve everywhere carry an environment marker:
   `dgl = ['dgl>=2.0; python_version < "3.13"', "torch>=2.0"]`. On 3.13 the
   extra installs and is simply inert — `export/dgl.py` is lazily imported
   (ADR-0007), so the feature reports itself unavailable through the normal
   `_optional.require` path instead of breaking installation.
2. **`all` contains only unmarked requirements.** A member needing a marker is
   reachable through its own extra, never bundled into the aggregate, because
   an aggregate that fails takes unrelated backends with it. `dgl` is therefore
   out of `all`; install it deliberately on Python 3.11/3.12.
3. `tests/test_optional_deps.py` asserts both halves: no member of `all` carries
   an environment marker, and the platform-limited extras carry theirs.

## Consequences

- `pip install "lp2graph[all]"` works on 3.11, 3.12 and 3.13.
- `pip install "lp2graph[dgl]"` installs on 3.13 without pulling DGL; DGL-backed
  export raises the ADR-0007 `ImportError` naming the extra. This is a quiet
  behaviour change on 3.13 only, where the previous behaviour was a failed
  install.
- Anyone wanting DGL out of `[all]` must now ask for it. Acceptable: DGL is the
  least-used exporter, it is dormant upstream, and the `torch`+`dgl` pair is
  ~2 GB.
- The rule generalizes. `torch`/`torch_geometric` are the next candidates to
  outgrow it — they are in `all` and currently publish cp313 wheels, but a new
  Python release typically lands months before their wheels do. The extras
  table should be re-checked against PyPI whenever the CI matrix gains a
  Python version; that check belongs with the matrix bump, not after a user
  reports a failed install.
