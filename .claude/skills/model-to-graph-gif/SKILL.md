---
name: model-to-graph-gif
description: >-
  Render an animated GIF of the canonical conversion of a WHOLE model: its
  canonical LaTeX rows are processed three at a time and the typed schema graph
  grows like a tree (objective at the root, then constraints, operators,
  variables/parameters, indices), with nodes flying out of the rows that
  introduce them. Use when asked to visualize / animate / make a video or GIF of
  how a model (lp2graph JSON, canonical LaTeX, or a document with a `%@` header)
  becomes the lp2graph graph, e.g. for a talk, a slide, or a README.
---

# Model -> typed graph, as a GIF

One script, `scripts/model_gif.py`, run from the repo root with `PYTHONPATH=src`:

```bash
PYTHONPATH=src python3 .claude/skills/model-to-graph-gif/scripts/model_gif.py \
    path/to/model.json --out /tmp/model.gif
```

| Option | Default | Meaning |
|---|---|---|
| `MODEL` | | `.json` formulation (`lp2graph.load`), canonical LaTeX (`from_canonical_latex`), or any LaTeX with a `%@` header (falls back to `ingest_latex`) |
| `--out` | `MODEL.gif` | GIF path; a `_poster.png` of the final frame is written next to it |
| `--batch` | 3 | rows processed per step |
| `--fps` | 15 | frame rate (each step is ~2.5 s) |
| `--size` | `1280x720` | canvas; everything scales from 1280 wide |
| `--title` | model name + ": from equations to the typed graph" | headline |
| `--keep-unused` | off | also show declared indices/parameters that no row reaches |

## What the video shows (all computed, nothing hand-placed)

- **Left:** the rows of `to_canonical_latex(f)` (objective first, then constraints in
  model order), typeset with `pdflatex`. The current batch gets an orange bar;
  processed rows fade, upcoming rows are pale; the list scrolls with the batch.
- **Right:** the schema view (`lp2graph.mining.isomorphism.report.schema_nx`). Step 1
  is the objective alone (the root). Each later step takes the next `--batch`
  constraints; the nodes they introduce first (BFS from the row node) fly from
  their row into a layered tree layout, the existing nodes glide to make room,
  and new edges grow once both ends have landed.
- **Layers:** objective, constraints, operators, variables + parameters, indices.
  The order inside a layer follows the parents (barycenter), so the tree stays
  readable as it widens. Crowded layers stagger.
- **Colours** (TU Dresden chair palette, fixed roles): objective orange, constraint
  blue, operator grey, variable Türkis, parameter dark blue, index yellow;
  index edges light grey, coefficient/parameter edges light orange.

## Rules

- **Elsevier corpus models stay private.** A GIF of a promoted corpus model shows the
  paper's equations: it is TDM-derived material and must not be published or
  committed to a public repo (lp2graph and the lab are public). Write it to a
  scratch folder or a private repo (e.g. `~/tudPresentations`). Seed models,
  repo-corpus models (check their licence) and invented demos are fine.
- Fonts: Noto Sans when installed (`~/.local/share/fonts`), else DejaVu from
  matplotlib. Rows use the LaTeX Computer Modern fonts.
- Needs Pillow, PyMuPDF (`fitz`), networkx and `pdflatex`. No lp2graph runtime dependency
  is added: the script lives outside `src/`.

## Size and time

A 12-row model: about 15 s, about 3 MB, about 2 minutes to render (every frame is drawn
from scratch). For slides keep `1280x720`; for a README use `--size 960x540 --fps 12`.
Very large models (> 70 nodes) only label variables, indices and the objective.
Run long renders in the background.

## Checking a render

PIL merges identical frames, so seek with `Image.open(gif).n_frames`, not the
printed frame count:

```python
from PIL import Image
im = Image.open("model.gif"); n = im.n_frames
for i, k in enumerate([n // 3, 2 * n // 3, n - 1]):
    im.seek(k); im.convert("RGB").save(f"frame_{i}.png")
```

Look at a mid-batch frame (nodes in flight, labels readable) and the poster.
