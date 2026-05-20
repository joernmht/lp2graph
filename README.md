# lp2graph

[![ci](https://github.com/joernmht/lp2graph/actions/workflows/ci.yml/badge.svg)](https://github.com/joernmht/lp2graph/actions/workflows/ci.yml)
[![docs](https://github.com/joernmht/lp2graph/actions/workflows/docs.yml/badge.svg)](https://github.com/joernmht/lp2graph/actions/workflows/docs.yml)
[![PyPI](https://img.shields.io/pypi/v/lp2graph.svg)](https://pypi.org/project/lp2graph/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Typed-graph representation of LP, MIP, and MILP formulations.**

`lp2graph` is a focused library for representing optimization problems as
typed graphs and deriving multiple views of them — schema, hybrid, and
ground — from a single canonical data model. It ships:

- A version-stable JSON schema for formulations.
- Three view derivations that turn a formulation into a typed graph.
- Structural metrics computed deterministically over the model and views.
- SVG renderers and a static interactive viewer.
- Export adapters to PyG, DGL, NetworkX, LaTeX, and Pyomo.

The core has no solver dependency. Pyomo, JuMP, and friends are optional
extras.

## Install

```bash
pip install lp2graph                       # core only
pip install "lp2graph[networkx]"           # NetworkX export
pip install "lp2graph[pyg]"                # PyG export
pip install "lp2graph[all]"                # everything
```

## 60-second tour

```python
from lp2graph import load
from lp2graph.views import schema, hybrid, ground
from lp2graph.metrics.structural import structural_summary
from lp2graph.metrics.flags import presence_flags
from lp2graph.render.svg import render_svg

f = load("formulations/constraints/mip_2_1_big_m.json")

# Three views from one canonical model.
g_schema  = schema(f)                       # templates and indices
g_hybrid  = hybrid(f)                       # + offset-labeled edges
g_ground  = ground(f, {"I": 4})             # + degeneracy filters

# Metrics, deterministic.
print(structural_summary(g_schema)["graph_diameter"].value)
print(presence_flags(f)["has_big_m"].value)

# Render with the deliberate visual identity.
open("graph.svg", "w").write(render_svg(g_hybrid, title=f.name))
```

Or from the command line:

```bash
lp2graph validate formulations/constraints/lp_1_1_fixed_sequence.json
lp2graph render   formulations/constraints/mip_2_1_big_m.json --view hybrid --output mip_2_1.svg
lp2graph metrics  formulations/constraints/mip_2_4_time_indexed.json
lp2graph export   formulations/constraints/mip_2_8_pesp.json --format latex
```

## What goes in, what comes out

A **formulation** is a JSON document validated against
[`schema/canonical.schema.json`](schema/canonical.schema.json). It declares
*index families* (e.g. `I`, `T`), *parameters*, *variable templates*,
*constraint templates* with quantifiers and bindings, and an optional
*objective* with first-class terms.

The **schema view** exposes templates and indices — the topology of the
problem. The **hybrid view** adds per-term offset, sign, and modulo
labels. The **ground view** materializes every instance at given index
cardinalities and applies degeneracy filters.

See [`docs/data-model.md`](docs/data-model.md) and
[`docs/views.md`](docs/views.md) for the long form.

## Status

v0.1 is an alpha. The schema and the canonical model are stable for a
representative cross-section of formulations; the catalog is in active
expansion. Tracked open questions live as `open-question` issues so they
are visible.

## Documentation

- [Data model](docs/data-model.md)
- [Views](docs/views.md)
- [Metrics](docs/metrics.md)
- [Add a formulation](docs/add-a-formulation.md)
- [Design context](docs/design-context.md) (the seed document)
- [Extraction report](docs/extraction-report.md) (provenance from the source repo)
- ADRs in [`docs/adr/`](docs/adr/)

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Bugs, new formulations, design
decisions, and good-first-issues all have dedicated templates.

## License

Apache 2.0. Portions adapted from
[`joernmht/raiLPminerExperimentation`](https://github.com/joernmht/raiLPminerExperimentation)
under MIT — see [`docs/extraction-report.md`](docs/extraction-report.md).
