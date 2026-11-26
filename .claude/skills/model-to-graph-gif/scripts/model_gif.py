#!/usr/bin/env python3
"""Animate the canonical conversion of a whole model: equations -> typed graph.

The model's rows (objective first, then the constraints in model order) are
processed in batches of ``--batch`` (default 3). Each batch is highlighted in
the equation list on the left; the schema-graph nodes it introduces fly out of
its rows into the graph on the right, existing nodes glide to make room, and
the new edges grow. The graph is drawn as a layered tree (objective at the
root, then constraints, operators, variables and parameters, indices), so it
grows downward and outward as rows are added.

Everything shown is computed: the rows are lp2graph's canonical LaTeX
(``to_canonical_latex``) and the nodes and edges are its schema view.

Usage::

    PYTHONPATH=src python3 .claude/skills/model-to-graph-gif/scripts/model_gif.py \
        MODEL [--out model.gif] [--batch 3] [--fps 15] [--size 1280x720] \
        [--title "..."] [--keep-unused]

MODEL is an lp2graph JSON formulation, a canonical LaTeX document, or any
LaTeX document with a ``%@`` declaration header (read with ``ingest_latex``).
Needs Pillow, PyMuPDF (``fitz``), networkx and ``pdflatex`` on PATH.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

# --- palette (TU Dresden chair colours) -------------------------------------
WHITE = (255, 255, 255)
INK, MUT, EDGE = (20, 32, 43), (95, 107, 118), (160, 170, 178)
TUR, ORA, DBL, MBL, GEL, GREY = (
    (10, 119, 127),
    (200, 80, 0),
    (0, 20, 80),
    (47, 87, 178),
    (255, 199, 0),
    (138, 148, 158),
)
NODE_COL = {
    "objective": ORA,
    "constraint": MBL,
    "operator": GREY,
    "variable": TUR,
    "parameter": DBL,
    "index": GEL,
}
LAYER = {"objective": 0, "constraint": 1, "operator": 2, "variable": 3, "parameter": 3, "index": 4}
EDGE_COL = {"uses_index": (205, 210, 214), "uses_parameter": (226, 170, 130)}


# --- fonts --------------------------------------------------------------------
def _font_paths() -> tuple[str | None, str | None]:
    cands = [
        os.path.expanduser("~/.local/share/fonts"),
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/opentype/noto",
    ]
    for d in cands:
        r, b = Path(d, "NotoSans-Regular.ttf"), Path(d, "NotoSans-Bold.ttf")
        if r.exists() and b.exists():
            return str(r), str(b)
    try:
        import matplotlib

        d = Path(matplotlib.__file__).parent / "mpl-data/fonts/ttf"
        return str(d / "DejaVuSans.ttf"), str(d / "DejaVuSans-Bold.ttf")
    except ImportError:
        return None, None


_REG, _BOLD = _font_paths()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _BOLD if bold else _REG
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


# --- model loading ------------------------------------------------------------
def load_model(path: Path):
    from lp2graph import load
    from lp2graph.codec.latex import from_canonical_latex
    from lp2graph.mining.ingest import ingest_latex

    if path.suffix == ".json":
        return load(str(path))
    text = path.read_text(encoding="utf-8")
    try:
        return from_canonical_latex(text)
    except Exception:  # not canonical: run the full ingest (normalize, parse)
        res = ingest_latex(text, source=str(path))
        if not res.ok:
            sys.exit(f"{path}: ingest_latex failed: {res}")
        return res.formulation


def canonical_rows(f) -> list[tuple[str, str, str]]:
    """(kind, name, display LaTeX) per row, in the order of the canonical document."""
    from lp2graph.codec.latex import to_canonical_latex

    text = to_canonical_latex(f)
    body = text.split(r"\begin{align}", 1)[1].split(r"\end{align}", 1)[0]
    rows = []
    for raw in re.split(r"\\\\\s*\n", body):
        raw = raw.strip()
        if not raw:
            continue
        m = re.search(r"\\tag\{([^}]*)\}", raw)
        name = m.group(1).replace(r"\_", "_") if m else ""
        tex = re.sub(r"\\tag\{[^}]*\}", "", raw).replace("&", "").strip()
        tex = tex.replace(r"\quad", r"\;", 1) if tex.startswith(("\\min", "\\max")) else tex
        kind = "objective" if tex.startswith(("\\min", "\\max")) else "constraint"
        rows.append((kind, name, tex))
    return rows


# --- LaTeX -> image -------------------------------------------------------------
def tex_image(tex: str, scale: float = 3.0) -> Image.Image:
    d = tempfile.mkdtemp()
    Path(d, "f.tex").write_text(
        r"\documentclass[border=3pt]{standalone}\usepackage{amsmath,amssymb}"
        r"\begin{document}$\displaystyle " + tex + r"$\end{document}",
        encoding="utf-8",
    )
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "f.tex"], cwd=d, capture_output=True, check=False
    )
    pdf = Path(d, "f.pdf")
    if not pdf.exists():  # show the source rather than fail the whole video
        im = Image.new("RGB", (900, 60), WHITE)
        ImageDraw.Draw(im).text((4, 18), tex[:120], font=font(18), fill=INK)
        return im
    pix = fitz.open(str(pdf))[0].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def fit(im: Image.Image, w: int, h: int, base: float = 1.0) -> Image.Image:
    s = min(w / im.width, h / im.height, base)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)


# --- graph --------------------------------------------------------------------
def schema_graph(f, keep_unused: bool):
    """The schema view; by default only what some row reaches (declared but
    unused indices and parameters are left out, as in the WL core graph)."""
    import networkx as nx

    from lp2graph.mining.isomorphism.report import schema_nx

    g = schema_nx(f)
    if not keep_unused:
        roots = [n for n in g if n.startswith(("objective:", "constraint:"))]
        keep = set(roots)
        for r in roots:
            keep |= nx.descendants(g, r)
        g = g.subgraph(sorted(keep)).copy()
    return g


def row_node(kind: str, name: str) -> str:
    return "objective:0" if kind == "objective" else f"constraint:{name}"


def introduced(g, rows) -> dict[str, list[str]]:
    """Nodes each row brings in first (downstream of its row node, BFS order)."""
    seen: set[str] = set()
    out: dict[str, list[str]] = {}
    for kind, name, _ in rows:
        root = row_node(kind, name)
        new: list[str] = []
        if root in g:
            queue = [root]
            while queue:
                n = queue.pop(0)
                if n in seen:
                    continue
                seen.add(n)
                new.append(n)
                queue.extend(sorted(g.successors(n), key=_node_order))
        out[root] = new
    rest = [n for n in sorted(g, key=_node_order) if n not in seen]
    if rest:
        out["__unused__"] = rest
    return out


def _node_order(n: str) -> tuple[int, str]:
    return (LAYER.get(n.split(":", 1)[0].replace("var", "variable"), 9), n)


def cls_of(g, n: str) -> str:
    return g.nodes[n].get("cls", "operator")


def label_of(g, n: str) -> str:
    d = g.nodes[n]
    c = cls_of(g, n)
    if c == "operator":
        over = d.get("shape") or ()
        return f"{d.get('subtype', 'op')}_{','.join(over)}" if over else str(d.get("subtype", "op"))
    if c == "objective":
        return str(d.get("subtype", "obj"))
    lab = str(d.get("label") or n.split(":", 1)[-1])
    return lab if len(lab) <= 14 else lab[:13] + "."


def layout(g, present: list[str], box: tuple[int, int, int, int], prev: dict) -> dict:
    """Layered tree layout of the present nodes; order inside a layer follows
    the parents' x (barycenter), then the previous position, then first appearance."""
    x0, y0, x1, y1 = box
    layers: dict[int, list[str]] = {}
    for n in present:
        layers.setdefault(LAYER[cls_of(g, n)], []).append(n)
    used = sorted(layers)
    pos: dict[str, tuple[float, float]] = {}
    rank = {n: i for i, n in enumerate(present)}
    dy = (y1 - y0) / max(1, len(used) - 1) if len(used) > 1 else 0
    for li, layer in enumerate(used):
        nodes = layers[layer]

        def key(n: str) -> tuple[float, float, int]:
            parents = [p for p in g.predecessors(n) if p in pos]
            bary = sum(pos[p][0] for p in parents) / len(parents) if parents else math.inf
            return (bary, prev.get(n, (math.inf, 0))[0], rank[n])

        nodes.sort(key=key)
        k = len(nodes)
        step = (x1 - x0) / k
        y = y0 + li * dy if len(used) > 1 else (y0 + y1) / 2
        for i, n in enumerate(nodes):
            zig = (16 if i % 2 else -16) if step < 78 else 0
            pos[n] = (x0 + step * (i + 0.5), y + zig)
    return pos


# --- drawing --------------------------------------------------------------------
def ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return tuple(int(p + (q - p) * t) for p, q in zip(a, b, strict=True))


def seeded(n: str) -> float:
    return int(hashlib.sha1(n.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("model", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--batch", type=int, default=3)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--title")
    ap.add_argument("--keep-unused", action="store_true", help="show declared but unused nodes")
    a = ap.parse_args(argv)

    W, H = (int(v) for v in a.size.lower().split("x"))
    S = W / 1280  # everything is designed at 1280 wide
    fps = a.fps
    out = a.out or a.model.with_suffix(".gif")

    f = load_model(a.model)
    rows = canonical_rows(f)
    g = schema_graph(f, a.keep_unused)
    intro = introduced(g, rows)
    tf = font(int(25 * (W / 1280)), True)
    name, tail = str(f.name or f.id), ": from equations to the typed graph"
    title = a.title or name + tail
    while not a.title and tf.getlength(title) > W - 72 * (W / 1280) and len(name) > 12:
        name = name[: int(len(name) * 0.9)].rstrip(" :,-")
        title = name + "…" + tail

    # batches: objective alone as the root, then the constraints in groups
    obj = [r for r in rows if r[0] == "objective"]
    cons = [r for r in rows if r[0] == "constraint"]
    batches = ([obj] if obj else []) + [cons[i : i + a.batch] for i in range(0, len(cons), a.batch)]
    if "__unused__" in intro:
        batches.append([("unused", "declared, not used by any row", "")])

    # equation images
    LW = int(450 * S)
    RH = int(70 * S)
    imgs = {}
    for kind, name, tex in rows:
        # one type size for every row (0.52 of the 3x render ~ 18 px at 1280 wide);
        # only rows wider than the panel shrink further
        imgs[name or kind] = fit(tex_image(tex), LW - int(18 * S), RH, base=0.52 * S)
    if "__unused__" in intro:
        ph = Image.new("RGB", (LW - int(18 * S), int(30 * S)), WHITE)
        ImageDraw.Draw(ph).text(
            (0, 4), "declared, not used by any row", font=font(int(16 * S)), fill=MUT
        )
        imgs["declared, not used by any row"] = ph
    order = [r[1] or r[0] for b in batches for r in b]
    slot_h = {k: imgs[k].height + int(14 * S) for k in order}
    slot_y: dict[str, int] = {}
    acc = 0
    for k in order:
        slot_y[k] = acc
        acc += slot_h[k]
    list_top, list_bot = int(108 * S), H - int(52 * S)

    box = (int(540 * S), int(130 * S), W - int(40 * S), H - int(95 * S))
    frames: list[Image.Image] = []
    present: list[str] = []
    pos: dict[str, tuple[float, float]] = {}
    born: dict[str, int] = {}  # frame at which a node finished landing
    scroll = 0.0

    def draw_frame(cur: list[str], scroll_y: float, node_xy, edge_t, hl: float, caption: str):
        im = Image.new("RGB", (W, H), WHITE)
        d = ImageDraw.Draw(im)
        d.text((int(36 * S), int(20 * S)), title, font=font(int(25 * S), True), fill=INK)
        d.text((int(36 * S), int(58 * S)), caption, font=font(int(16 * S)), fill=MUT)
        # equation list
        done = set(order[: order.index(cur[0])]) if cur else set(order)
        for k in order:
            y = list_top + slot_y[k] - scroll_y
            if y + slot_h[k] < list_top - 4 or y > list_bot:
                continue
            src = imgs[k]
            if k in cur:
                d.rectangle(
                    (int(28 * S), y, int(33 * S), y + src.height),
                    fill=mix(WHITE, ORA, hl),
                )
                im.paste(src, (int(44 * S), int(y)))
            else:
                fade = 0.55 if k in done else 0.78
                im.paste(
                    Image.blend(src, Image.new("RGB", src.size, WHITE), fade), (int(44 * S), int(y))
                )
        # clip the list area edges
        d.rectangle((0, 0, int(520 * S), list_top - 6), fill=WHITE)
        d.rectangle((0, list_bot, int(520 * S), H), fill=WHITE)
        d.text((int(36 * S), int(20 * S)), title, font=font(int(25 * S), True), fill=INK)
        d.text((int(36 * S), int(58 * S)), caption, font=font(int(16 * S)), fill=MUT)
        d.line(
            (int(520 * S), int(100 * S), int(520 * S), H - int(60 * S)),
            fill=(225, 229, 232),
            width=1,
        )
        # edges
        r = max(5, int((12 if len(node_xy) < 40 else 9) * S))
        for u, v, data in g.edges(data=True):
            if u not in node_xy or v not in node_xy:
                continue
            t = edge_t(u, v)
            if t <= 0:
                continue
            (xa, ya), (xb, yb) = node_xy[u], node_xy[v]
            col = EDGE_COL.get(data.get("type"), EDGE)
            d.line(
                (xa, ya, xa + (xb - xa) * t, ya + (yb - ya) * t), fill=col, width=max(1, int(2 * S))
            )
        # nodes
        lab_font = font(int(12 * S))
        show_labels = len(node_xy) <= 70
        for n, (x, y) in node_xy.items():
            c = cls_of(g, n)
            d.ellipse((x - r, y - r, x + r, y + r), fill=NODE_COL[c], outline=INK, width=1)
            if show_labels or c in ("variable", "index", "objective"):
                s = label_of(g, n)
                tw = lab_font.getlength(s)
                d.text(
                    (x - tw / 2, y + r + 2), s, font=lab_font, fill=INK if c != "operator" else MUT
                )
        # legend
        lx = box[0]
        for c in ("objective", "constraint", "operator", "variable", "parameter", "index"):
            d.ellipse(
                (lx, H - int(44 * S), lx + int(12 * S), H - int(32 * S)),
                fill=NODE_COL[c],
                outline=INK,
            )
            d.text((lx + int(17 * S), H - int(48 * S)), c, font=font(int(14 * S)), fill=MUT)
            lx += int(17 * S) + font(int(14 * S)).getlength(c) + int(22 * S)
        d.text(
            (int(36 * S), H - int(30 * S)),
            f"{len(present)} nodes, {sum(1 for u, v in g.edges() if u in node_xy and v in node_xy)} edges"
            f"  |  lp2graph schema view  |  rows in canonical LaTeX",
            font=font(int(13 * S)),
            fill=MUT,
        )
        return im

    for batch in batches:
        keys = [r[1] or r[0] for r in batch]
        new: list[str] = []
        origin: dict[str, tuple[float, float]] = {}
        for (kind, name, _), k in zip(batch, keys, strict=True):
            nodes = intro["__unused__"] if kind == "unused" else intro.get(row_node(kind, name), [])
            for n in nodes:
                new.append(n)
                origin[n] = (k, seeded(n))
        # target scroll: keep the current batch in the upper third
        target_scroll = max(
            0.0, min(slot_y[keys[0]] - (list_bot - list_top) * 0.25, acc - (list_bot - list_top))
        )
        target_scroll = max(0.0, target_scroll)
        old_pos = dict(pos)
        present_next = present + new
        new_pos = layout(g, present_next, box, old_pos)
        what = (
            "the objective is the root"
            if batch[0][0] == "objective"
            else (
                "declarations no row uses"
                if batch[0][0] == "unused"
                else f"rows {order.index(keys[0]) + 1 - (1 if obj else 0)}-"
                f"{order.index(keys[-1]) + 1 - (1 if obj else 0)} of {len(cons)}: "
                f"{len(new)} new node{'s' if len(new) != 1 else ''}"
            )
        )
        n_hl, n_fly, n_edge, n_hold = (
            int(0.5 * fps),
            int(1.2 * fps),
            int(0.5 * fps),
            int(0.35 * fps),
        )
        stagger = min(0.5 * fps, n_fly * 0.5) / max(1, len(new))
        start_scroll = scroll
        total = n_hl + n_fly + n_edge + n_hold
        base = len(frames)
        for k in range(total):
            hl = ease(k / n_hl) if k < n_hl else 1.0
            s_t = ease(k / n_hl)
            scroll = start_scroll + (target_scroll - start_scroll) * s_t
            ft = (k - n_hl) / n_fly
            xy: dict[str, tuple[float, float]] = {}
            for n in present:  # existing nodes glide to their new slot
                (xa, ya), (xb, yb) = old_pos[n], new_pos[n]
                q = ease(ft)
                xy[n] = (xa + (xb - xa) * q, ya + (yb - ya) * q)
            for i, n in enumerate(new):
                q = ease((k - n_hl - i * stagger) / (n_fly - stagger * len(new) * 0.5 or 1))
                if q <= 0:
                    continue
                rk, u = origin[n]
                sy = list_top + slot_y[rk] - scroll + imgs[rk].height / 2
                sx = 44 * S + u * imgs[rk].width
                ex, ey = new_pos[n]
                cx, cy = (sx + ex) / 2, min(sy, ey) - 60 * S
                xy[n] = (
                    (1 - q) ** 2 * sx + 2 * (1 - q) * q * cx + q * q * ex,
                    (1 - q) ** 2 * sy + 2 * (1 - q) * q * cy + q * q * ey,
                )
                if q >= 1 and n not in born:
                    born[n] = base + k

            def edge_t(u, v, k=k, present=present, base=base, n_edge=n_edge):
                if u in present and v in present:
                    return 1.0
                land = max(born.get(u, 10**9), born.get(v, 10**9))
                return ease((base + k - land) / n_edge) if base + k >= land else 0.0

            frames.append(draw_frame(keys, scroll, xy, edge_t, hl, what))
        present = present_next
        pos = new_pos
        for n in new:
            born.setdefault(n, base + total)

    # final hold: everything settled, nothing highlighted
    hold = draw_frame(
        [],
        scroll,
        pos,
        lambda u, v: 1.0,
        0.0,
        f"done: {len(rows)} rows -> one connected typed graph",
    )
    frames += [hold] * int(2.5 * fps)

    pal = [fr.convert("P", palette=Image.ADAPTIVE, colors=96) for fr in frames]
    dur = [int(1000 / fps)] * len(pal)
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=dur, loop=0, disposal=1)
    hold.save(out.with_name(out.stem + "_poster.png"))
    print(
        f"{out}: {len(frames)} frames, {len(frames) / fps:.1f} s, {out.stat().st_size // 1024} KB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
