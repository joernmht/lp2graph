# lp2graph · translation demo UI

A lean, self-contained web UI to **show the translation feature live**: paste
a MILP formulation on the left, watch the generated typed graph appear in the
middle, read the deterministically-detected LP/MIP/MILP family and structural
metrics on the right.

Built to be pretty for a talk *and* trivial to drop onto a self-hosted site.

```
┌──────────── lp2graph · formulation → typed graph ─────────  [family: MILP] ┐
│  INPUT            │            GENERATED GRAPH            │     DETAILS     │
│  ┌─────────────┐  │   ┌───────────────────────────────┐  │  family / size  │
│  │ JSON editor │  │   │   ●──────■   (the SVG, hero)   │  │  metrics        │
│  └─────────────┘  │   │     ╲   ╱                      │  │  presence flags │
│  [schema|hybrid|  │   └───────────────────────────────┘  │                 │
│   ground]         │                                       │                 │
│  ▰ TRANSLATE ▰    │                                       │                 │
└───────────────────┴───────────────────────────────────────┴─────────────────┘
```

## Run it (≈30 seconds)

```bash
cd lp2graph/ui
pip install -r requirements.txt        # fastapi + uvicorn (+ lp2graph's own deps)
python server.py                       # → http://127.0.0.1:8000
```

That's it — it opens warm with the Big-M MILP already translated. No build
step, no install of `lp2graph` itself: the server imports the library straight
from `../src`, so **the core repo is never touched**.

Other ways to launch:

```bash
./run.sh --port 9000                   # custom port
python server.py --host 0.0.0.0        # expose on the LAN for the demo
python server.py --reload              # dev auto-reload
```

## What it does

* **Input** — a canonical formulation as JSON (the format `lp2graph` already
  loads). A dropdown loads every bundled `formulations/*.json` example.
* **Translate** — `POST /api/translate` derives the chosen view
  (schema / hybrid / ground), renders the library's own SVG, and computes the
  structural metrics + presence flags. Ground view auto-fills index
  cardinalities (default 4, editable per index).
* **Family detection** — deterministic, from variable domains only:
  * all continuous → **LP**
  * all integer/binary → **MIP** (pure integer program)
  * a mix → **MILP**
  The badge flags a mismatch if the declared `family` disagrees with what the
  domains imply. The same rule runs client-side as you type, for instant
  feedback, and server-side as the source of truth.

## Look & feel

* **Cupertino** base — frosted top bar, hairline borders, soft 18px cards,
  system font stack, a segmented control for the view switch, system-blue
  focus rings.
* **Bauhaus** accents — the brand mark (square + circle + triangle in
  blue/yellow/red) and the chunky primary **Translate** button with its
  primary-colour shapes, red wedge and tactile press.

## Wiring it into a self-hosted website (the "few changes")

The whole thing is a standard ASGI app, so:

* **Reverse proxy** — point nginx/Caddy at `uvicorn server:app` (e.g.
  `uvicorn server:app --host 127.0.0.1 --port 8000` behind your TLS proxy).
* **Mount under a path** — if you serve it at `example.org/lp2graph/`, set a
  `root_path` (`uvicorn ... --root-path /lp2graph`) and the relative
  `/static`, `/api/...` URLs keep working.
* **Embed only the graph** — every translation is one JSON POST returning an
  inline `<svg>`; you can call `/api/translate` from any existing front-end
  and drop the SVG wherever you like.
* **CORS** — if you call the API from another origin, add FastAPI's
  `CORSMiddleware` (one block in `server.py`).
* **Static hosting** — `static/` is plain HTML/CSS/JS; it can be served by any
  CDN with the API hosted separately.

## Decisions I made overnight (documented as asked)

1. **Input format is the canonical JSON formulation**, not raw LP/MPS or
   solver code. Reason: that *is* `lp2graph`'s translation feature
   (formulation → typed graph), and the repo ships no LP-text parser. Writing
   one overnight would have meant touching core / inventing a parser — out of
   scope for "don't change core files." The editor takes the same JSON the
   library's `load()` accepts; the example dropdown makes pasting unnecessary
   for the demo.
2. **FastAPI + uvicorn** over Streamlit/Gradio. Reason: you wanted the
   Cupertino + Bauhaus aesthetic and "ready for a self-hosted website" — that
   needs full control over HTML/CSS, which the dashboard frameworks fight. A
   tiny FastAPI app + static page is the cleanest self-host target and the
   easiest to embed.
3. **No install of `lp2graph`** — the server injects `../src` onto
   `sys.path`. The core stays pristine; nothing new appears outside `ui/`.
4. **"Deterministically find out which it is"** → interpreted as detecting the
   LP/MIP/MILP **family** from variable domains (textbook rule above), shown
   as a live badge and cross-checked against the declared `family`.
5. **Default view is `schema`** (the topology — the cleanest first impression),
   with hybrid and ground one click away. Ground auto-sizes each index to 4 so
   it never errors on a missing cardinality.
6. **Only `formulations/*.json` populate the examples** — the `corpus/*.json`
   files are repo-mined catalogs in a different shape and don't load as single
   formulations, so they're intentionally excluded.
7. **Auto-translate on load and on example/view change** so the screen is
   never empty during a talk. `Cmd/Ctrl+Enter` in the editor also translates.

## Files

```
ui/
├── server.py            FastAPI app: /api/examples, /api/translate, static
├── static/
│   ├── index.html       three-panel layout
│   ├── styles.css       Cupertino + Bauhaus, single file
│   └── app.js           no framework, ~1 fetch per translate
├── requirements.txt
├── run.sh
└── README.md
```

## Endpoints

| Method | Path              | Purpose                                   |
|--------|-------------------|-------------------------------------------|
| GET    | `/`               | the UI                                     |
| GET    | `/api/examples`   | bundled formulation catalog                |
| POST   | `/api/translate`  | `{source, view, cards}` → `{svg, family, metrics, meta}` |
| GET    | `/api/health`     | liveness + lp2graph version                |
