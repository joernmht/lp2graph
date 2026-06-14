"""lp2graph demo UI — a lean translation front-end.

This server is a thin, self-contained wrapper around the *existing*
``lp2graph`` library. It does not modify or depend on anything being
installed: it adds the sibling ``src/`` directory to ``sys.path`` and
imports the public API directly, so the core repository stays untouched.

What it exposes
---------------
* ``GET  /``               -> the single-page UI.
* ``GET  /api/examples``   -> the bundled ``formulations/*.json`` catalog.
* ``POST /api/translate``  -> the star of the show: turn a canonical
  formulation (JSON) into a typed graph, render it to SVG, detect the
  LP/MIP/MILP family deterministically, and compute structural metrics.

Run it
------
    python ui/server.py                 # http://127.0.0.1:8000
    python ui/server.py --port 9000     # custom port
    python ui/server.py --host 0.0.0.0  # expose on the network

See ``ui/README.md`` for deployment notes and the design decisions made
while building this overnight.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# --- Wire up the core library without installing it -----------------------
# The UI lives in <repo>/ui ; the library lives in <repo>/src .
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lp2graph import __version__ as LP2GRAPH_VERSION  # noqa: E402
from lp2graph.core.loader import loads  # noqa: E402
from lp2graph.core.validate import ValidationError  # noqa: E402
from lp2graph.metrics.flags import presence_flags  # noqa: E402
from lp2graph.metrics.structural import structural_summary  # noqa: E402
from lp2graph.render.svg import render_svg  # noqa: E402
from lp2graph.views import ground, hybrid, schema  # noqa: E402

from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
FORMULATIONS = REPO_ROOT / "formulations"

INT_DOMAINS = {"integer", "binary"}
CONT_DOMAINS = {"continuous", "non_negative"}


# --------------------------------------------------------------------------
# API-key access control
# --------------------------------------------------------------------------
# Opt-in: if no keys are configured the server runs OPEN (handy for a local
# run or an SSH tunnel). The moment one or more keys are configured — via the
# ``LP2GRAPH_API_KEYS`` env var (comma/whitespace separated) and/or a file
# named in ``LP2GRAPH_API_KEYS_FILE`` — the data endpoints require a valid key.
# A caller may present it as the ``X-API-Key`` header, an
# ``Authorization: Bearer <key>`` header, a ``?key=`` query parameter, or a
# ``lp2graph_key`` cookie (the browser UI uses the header).
def _load_api_keys() -> set[str]:
    raw = os.environ.get("LP2GRAPH_API_KEYS", "")
    key_file = os.environ.get("LP2GRAPH_API_KEYS_FILE")
    if key_file:
        try:
            raw += "\n" + Path(key_file).read_text(encoding="utf-8")
        except OSError:
            pass
    return {tok for tok in re.split(r"[,\s]+", raw) if tok.strip()}


API_KEYS = _load_api_keys()
AUTH_REQUIRED = bool(API_KEYS)


def _presented_key(request: Request) -> str | None:
    header = request.headers.get("x-api-key")
    if header:
        return header.strip()
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    query = request.query_params.get("key")
    if query:
        return query.strip()
    cookie = request.cookies.get("lp2graph_key")
    if cookie:
        return cookie.strip()
    return None


def require_key(request: Request) -> None:
    """FastAPI dependency: 401 unless a valid API key is presented.

    No-op when the server is running open (no keys configured). Uses a
    constant-time comparison so a wrong key can't be timed character by
    character.
    """
    if not AUTH_REQUIRED:
        return
    presented = _presented_key(request)
    if presented and any(hmac.compare_digest(presented, k) for k in API_KEYS):
        return
    raise HTTPException(status_code=401, detail="Missing or invalid API key.")


app = FastAPI(title="lp2graph translation demo", version=LP2GRAPH_VERSION)

# Optional CORS — only when you call the API from another origin (an embedded
# graph on your main site). Set LP2GRAPH_CORS_ORIGINS to a comma-separated
# allow-list, e.g. "https://example.org,https://www.example.org".
_cors = os.environ.get("LP2GRAPH_CORS_ORIGINS", "").strip()
if _cors:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in _cors.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


# --------------------------------------------------------------------------
# Deterministic family detection
# --------------------------------------------------------------------------
def detect_family(data: dict[str, Any]) -> dict[str, Any]:
    """Infer the LP/MIP/MILP family purely from variable domains.

    This is deliberately deterministic — no model, no heuristics beyond
    the textbook definition:

    * **LP**   — every variable is continuous.
    * **MIP**  — every variable is integer/binary (a pure integer program).
    * **MILP** — a mix of integer/binary *and* continuous variables.

    It reads the raw JSON (not the validated model) so the badge still
    lights up even when the rest of the document has a validation error.
    """
    variables = data.get("variables") or []
    domains = [v.get("domain") for v in variables if isinstance(v, dict)]
    has_int = any(d in INT_DOMAINS for d in domains)
    has_cont = any(d in CONT_DOMAINS for d in domains)

    if not domains:
        detected, reason = None, "No variables declared."
    elif has_int and has_cont:
        detected = "milp"
        reason = "Mix of integer/binary and continuous variables."
    elif has_int:
        detected = "mip"
        reason = "Every variable is integer or binary (pure integer program)."
    else:
        detected = "lp"
        reason = "Every variable is continuous."

    declared = data.get("family")
    return {
        "detected": detected,
        "declared": declared,
        "agree": (declared == detected) if (declared and detected) else None,
        "reason": reason,
        "counts": {
            "integer_or_binary": sum(1 for d in domains if d in INT_DOMAINS),
            "continuous": sum(1 for d in domains if d in CONT_DOMAINS),
            "total": len(domains),
        },
    }


# --------------------------------------------------------------------------
# Rendering helpers
# --------------------------------------------------------------------------
def _responsive(svg: str) -> str:
    """Drop the fixed width/height so the SVG scales to its container.

    The library keeps ``viewBox`` intact, so removing the absolute size
    lets CSS drive the dimensions without distorting the layout.
    """
    svg = re.sub(r'\swidth="\d+"', "", svg, count=1)
    svg = re.sub(r'\sheight="\d+"', "", svg, count=1)
    return svg


def _derive(formulation: Any, view: str, cards: dict[str, int]):
    if view == "schema":
        return schema(formulation)
    if view == "ground":
        return ground(formulation, cards)
    return hybrid(formulation)


def _metrics_payload(graph, formulation) -> dict[str, Any]:
    structural = {}
    for name, m in structural_summary(graph).items():
        structural[name] = {"value": m.value, "explanation": m.explanation}
    flags = {}
    for name, m in presence_flags(formulation).items():
        flags[name] = {"value": m.value, "explanation": m.explanation}
    return {"structural": structural, "flags": flags}


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
class TranslateRequest(BaseModel):
    source: str
    view: str = "hybrid"
    cards: dict[str, int] = {}


@app.get("/api/examples", dependencies=[Depends(require_key)])
def examples() -> JSONResponse:
    """The bundled formulation catalog, ready to drop into the editor."""
    out: list[dict[str, Any]] = []
    if FORMULATIONS.exists():
        for path in sorted(FORMULATIONS.rglob("*.json")):
            try:
                text = path.read_text(encoding="utf-8")
                data = json.loads(text)
            except (OSError, json.JSONDecodeError):
                continue
            out.append(
                {
                    "id": data.get("id", path.stem),
                    "name": data.get("name", path.stem),
                    "family": data.get("family"),
                    "group": path.parent.name,
                    "description": data.get("description", ""),
                    "source": text,
                }
            )
    return JSONResponse(out)


@app.post("/api/translate", dependencies=[Depends(require_key)])
def translate(req: TranslateRequest) -> JSONResponse:
    """Translate a formulation into a typed graph + SVG + metrics.

    Always returns HTTP 200 with an ``ok`` flag so the front-end can show
    the family badge even when validation fails. Parse/validation issues
    come back as a structured ``error`` payload.
    """
    view = req.view if req.view in ("schema", "hybrid", "ground") else "hybrid"

    # 1. Parse JSON (cheap, lets us detect family even if invalid).
    try:
        data = json.loads(req.source)
    except json.JSONDecodeError as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": {"kind": "json", "message": f"Invalid JSON: {exc}"},
                "family": None,
            }
        )

    family = detect_family(data) if isinstance(data, dict) else None

    # 2. Auto-fill cardinalities for the ground view (default 4 per index).
    indices = [i.get("name") for i in (data.get("indices") or [])] if isinstance(data, dict) else []
    cards = {k: int(v) for k, v in req.cards.items() if v}
    if view == "ground":
        for name in indices:
            cards.setdefault(name, 4)

    # 3. Validate + build the canonical model.
    try:
        formulation = loads(req.source)
    except ValidationError as exc:
        details = getattr(exc, "errors", None) or [str(exc)]
        return JSONResponse(
            {
                "ok": False,
                "error": {"kind": "validation", "message": str(exc), "details": details},
                "family": family,
            }
        )
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse(
            {
                "ok": False,
                "error": {"kind": "model", "message": str(exc)},
                "family": family,
            }
        )

    # 4. Derive the view, render, measure.
    try:
        graph = _derive(formulation, view, cards)
        svg = _responsive(render_svg(graph, title=formulation.name))
        metrics = _metrics_payload(graph, formulation)
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse(
            {
                "ok": False,
                "error": {"kind": "render", "message": str(exc)},
                "family": family,
            }
        )

    return JSONResponse(
        {
            "ok": True,
            "family": family,
            "view": view,
            "cards": cards if view == "ground" else {},
            "indices": indices,
            "svg": svg,
            "meta": {
                "id": formulation.id,
                "name": formulation.name,
                "description": formulation.description,
                "tags": list(formulation.tags),
                "n_variables": len(formulation.variables),
                "n_constraints": len(formulation.constraints),
                "n_indices": len(formulation.indices),
                "n_parameters": len(formulation.parameters),
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
            },
            "metrics": metrics,
        }
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "lp2graph": LP2GRAPH_VERSION}


@app.get("/api/auth/check")
def auth_check() -> dict[str, Any]:
    """Tell the front-end whether it must collect an API key (no key leaked)."""
    return {"auth_required": AUTH_REQUIRED}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main() -> None:
    parser = argparse.ArgumentParser(description="lp2graph translation demo UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="auto-reload (dev)")
    args = parser.parse_args()

    import uvicorn

    print(f"lp2graph {LP2GRAPH_VERSION} — demo UI at http://{args.host}:{args.port}")
    if AUTH_REQUIRED:
        print(f"auth: API key REQUIRED ({len(API_KEYS)} key(s) loaded)")
    else:
        print("auth: OPEN — no API keys configured (set LP2GRAPH_API_KEYS to lock it down)")
    uvicorn.run(
        "server:app" if args.reload else app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(Path(__file__).resolve().parent),
    )


if __name__ == "__main__":
    main()
