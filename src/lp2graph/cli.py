"""Command-line entry point: ``lp2graph``.

Subcommands:

- ``lp2graph validate <file>`` — end-to-end validation of a model file in
  any supported format (parse with fallbacks, semantic and structural
  checks, optional solve smoke check); exit 0 unless invalid.
- ``lp2graph view <file> --view {schema,hybrid,ground} [--card I=5 ...]``
  — derive a view and print a summary.
- ``lp2graph render <file> --view ... --output graph.svg`` — render to
  SVG.
- ``lp2graph metrics <file>`` — compute and print all metrics.
- ``lp2graph export <file> --format {networkx,pyg,dgl,latex,pyomo}`` —
  export.
- ``lp2graph convert <in> <out>`` — code ⇄ graph ⇄ code between modeling
  languages, routed by file extension (.json/.tex/.lp/.mps/.gms/.mod/.jl,
  plus .py output via ``--python-api``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from lp2graph import load
from lp2graph import views as _views
from lp2graph.metrics.flags import presence_flags
from lp2graph.metrics.structural import structural_summary
from lp2graph.render.svg import render_svg

if TYPE_CHECKING:
    from lp2graph.core.graph import Graph
    from lp2graph.core.model import Formulation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lp2graph")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser(
        "validate",
        help="Validate a model file end-to-end (any supported format): "
        "parse with fallbacks, semantic + structural checks, solve smoke check.",
    )
    p_validate.add_argument(
        "path",
        type=Path,
        help="Model file: .json (canonical), .tex, .lp, .mps, .gms, .mod, .jl; "
        "unknown extensions are format-sniffed.",
    )
    p_validate.add_argument(
        "--fmt",
        default=None,
        help="Explicit format override (json/latex/lp/mps/gams/ampl/jump).",
    )
    p_validate.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    p_validate.add_argument(
        "--no-solve", action="store_true", help="Skip the grounding/solve smoke check."
    )
    p_validate.add_argument(
        "--instance",
        type=Path,
        default=None,
        help="Instance JSON for the solve check (default: synthesized smoke data).",
    )
    p_validate.add_argument("--solver", choices=("cbc", "highs", "gurobi"), default="cbc")
    p_validate.add_argument(
        "--time-limit", type=float, default=20.0, help="Solve-check time limit in seconds."
    )

    p_view = sub.add_parser("view", help="Derive a view and print a summary.")
    p_view.add_argument("path", type=Path)
    p_view.add_argument("--view", choices=("schema", "hybrid", "ground"), default="schema")
    p_view.add_argument(
        "--card",
        action="append",
        default=[],
        help="Cardinality, e.g. --card I=5 --card T=8 (only for --view ground).",
    )

    p_render = sub.add_parser("render", help="Render a view to SVG.")
    p_render.add_argument("path", type=Path)
    p_render.add_argument("--view", choices=("schema", "hybrid", "ground"), default="hybrid")
    p_render.add_argument("--card", action="append", default=[])
    p_render.add_argument("--output", type=Path, required=True)

    p_metrics = sub.add_parser("metrics", help="Compute all metrics.")
    p_metrics.add_argument("path", type=Path)
    p_metrics.add_argument("--view", choices=("schema", "hybrid"), default="schema")

    p_export = sub.add_parser("export", help="Export to a downstream format.")
    p_export.add_argument("path", type=Path)
    p_export.add_argument(
        "--format",
        choices=("networkx", "pyg", "dgl", "latex", "pyomo"),
        required=True,
    )
    p_export.add_argument("--view", choices=("schema", "hybrid", "ground"), default="hybrid")
    p_export.add_argument("--card", action="append", default=[])
    p_export.add_argument("--output", type=Path, default=None)

    p_latex = sub.add_parser(
        "latex", help="Emit reversible, paper-style canonical LaTeX (graph -> text)."
    )
    p_latex.add_argument("path", type=Path)
    p_latex.add_argument("--output", type=Path, default=None)

    p_parse = sub.add_parser(
        "parse", help="Parse a canonical-LaTeX document back to JSON (text -> graph)."
    )
    p_parse.add_argument("path", type=Path, help="A .tex file produced by `lp2graph latex`.")
    p_parse.add_argument("--output", type=Path, default=None)

    p_describe = sub.add_parser(
        "describe",
        help="Generate a natural-language problem description (graph -> text).",
    )
    p_describe.add_argument("path", type=Path)
    p_describe.add_argument("--instance", type=Path, default=None)
    p_describe.add_argument("--output", type=Path, default=None)

    p_convert = sub.add_parser(
        "convert",
        help="Convert between modeling languages via the canonical graph "
        "(code -> graph -> code), routed by file extension.",
    )
    p_convert.add_argument(
        "input",
        type=Path,
        help="Source model: .json (canonical), .tex (canonical LaTeX), "
        ".lp, .mps, .gms (GAMS), .mod (AMPL), .jl (JuMP).",
    )
    p_convert.add_argument(
        "output",
        type=Path,
        help="Target file: .json, .tex, .lp, .mps, .gms, .mod, .jl, or .py "
        "(solver-API script; pick the API with --python-api).",
    )
    p_convert.add_argument(
        "--instance",
        type=Path,
        default=None,
        help="Instance JSON (cardinalities + parameter values); required to "
        "export a template-level formulation.",
    )
    p_convert.add_argument(
        "--python-api",
        choices=("gurobipy", "pulp", "pyomo"),
        default="pulp",
        help="Which solver API a .py output targets (default: pulp).",
    )

    p_solve = sub.add_parser("solve", help="Ground with instance data and solve the MILP.")
    p_solve.add_argument("path", type=Path)
    p_solve.add_argument("--instance", type=Path, required=True)
    p_solve.add_argument("--solver", choices=("cbc", "highs", "gurobi"), default="cbc")

    args = parser.parse_args(argv)

    if args.cmd == "validate":
        from lp2graph.validation import validate_path

        inst = None
        if args.instance is not None:
            from lp2graph.solve import Instance

            inst = Instance.load(args.instance)
        report = validate_path(
            args.path,
            fmt=args.fmt,
            solve_check=not args.no_solve,
            instance=inst,
            solver=args.solver,
            time_limit=args.time_limit,
        )
        print(report.to_json() if args.json else report.summary())
        return 0 if report.verdict != "invalid" else 1

    if args.cmd == "view":
        f = load(args.path)
        g = _derive(f, args.view, args.card)
        print(json.dumps({"nodes": len(g.nodes), "edges": len(g.edges), "view": g.view}, indent=2))
        return 0

    if args.cmd == "render":
        f = load(args.path)
        g = _derive(f, args.view, args.card)
        svg = render_svg(g, title=f.name)
        args.output.write_text(svg, encoding="utf-8")
        print(f"wrote {args.output}")
        return 0

    if args.cmd == "metrics":
        f = load(args.path)
        g = _derive(f, args.view, [])
        result: dict[str, object] = {}
        for name, m in structural_summary(g).items():
            result[name] = m.value
        for name, m in presence_flags(f).items():
            result[name] = m.value
        print(json.dumps(result, indent=2, default=str))
        return 0

    if args.cmd == "export":
        f = load(args.path)
        if args.format == "latex":
            from lp2graph.export.latex import to_latex

            out = to_latex(f)
        elif args.format == "pyomo":
            from lp2graph.export.pyomo_stub import to_pyomo_stub

            out = to_pyomo_stub(f)
        else:
            g = _derive(f, args.view, args.card)
            if args.format == "networkx":
                from lp2graph.export.networkx_adapter import to_networkx

                nxg = to_networkx(g)
                out = f"<NetworkX MultiDiGraph: {len(nxg)} nodes, {nxg.number_of_edges()} edges>"
            elif args.format == "pyg":
                from lp2graph.export.pyg import to_pyg

                pyg = to_pyg(g)
                out = repr(pyg)
            else:  # dgl
                from lp2graph.export.dgl import to_dgl

                dglg = to_dgl(g)
                out = repr(dglg)
        if args.output:
            args.output.write_text(out, encoding="utf-8")
            print(f"wrote {args.output}")
        else:
            print(out)
        return 0

    if args.cmd == "latex":
        from lp2graph.codec import to_canonical_latex

        out = to_canonical_latex(load(args.path))
        _emit(out, args.output)
        return 0

    if args.cmd == "parse":
        from lp2graph.codec import from_canonical_latex

        text = args.path.read_text(encoding="utf-8")
        f = from_canonical_latex(text)
        _emit(f.model_dump_json(indent=2, exclude_defaults=True), args.output)
        return 0

    if args.cmd == "describe":
        from lp2graph.nl import describe

        inst = None
        if args.instance is not None:
            from lp2graph.solve import Instance

            inst = Instance.load(args.instance)
        out = describe(load(args.path), inst)
        _emit(out, args.output)
        return 0

    if args.cmd == "convert":
        return _convert(args)

    if args.cmd == "solve":
        from lp2graph.solve import Instance, make_solver, solve

        solver = make_solver(args.solver, msg=False)
        res = solve(load(args.path), Instance.load(args.instance), solver=solver)
        print(
            json.dumps(
                {
                    "status": res.status,
                    "objective": res.objective,
                    "n_vars": res.n_vars,
                    "n_constraints": res.n_constraints,
                    "solver": res.solver,
                },
                indent=2,
            )
        )
        return 0

    return 0


def _convert(args: argparse.Namespace) -> int:
    """Route ``convert`` by file extension through the canonical Formulation."""
    f = _read_model(args.input)
    instance = None
    if args.instance is not None:
        from lp2graph.solve import Instance

        instance = Instance.load(args.instance)
    text = _write_model(f, args.output.suffix.lower(), instance, args.python_api)
    args.output.write_text(text, encoding="utf-8")
    print(
        f"wrote {args.output} ({f.id}: {len(f.variables)} variables, "
        f"{len(f.constraints)} constraints)"
    )
    return 0


def _read_model(path: Path) -> Formulation:
    ext = path.suffix.lower()
    if ext == ".json":
        return load(path)
    text = path.read_text(encoding="utf-8")
    if ext == ".tex":
        from lp2graph.codec import from_canonical_latex

        return from_canonical_latex(text)
    readers = {
        ".lp": "from_lp_string",
        ".mps": "from_mps_string",
        ".gms": "from_gams",
        ".mod": "from_ampl",
        ".jl": "from_jump",
    }
    if ext not in readers:
        raise SystemExit(f"cannot read {ext!r} files; supported: .json .tex {' '.join(readers)}")
    import lp2graph.interop as interop

    reader = getattr(interop, readers[ext])
    return reader(text)  # type: ignore[no-any-return]


def _write_model(f: Formulation, ext: str, instance: object, python_api: str) -> str:
    if ext == ".json":
        return f.model_dump_json(indent=2, exclude_defaults=True)
    if ext == ".tex":
        from lp2graph.codec import to_canonical_latex

        return to_canonical_latex(f)
    writers = {
        ".lp": "to_lp_string",
        ".mps": "to_mps_string",
        ".gms": "to_gams",
        ".mod": "to_ampl",
        ".jl": "to_jump",
        ".py": {
            "gurobipy": "to_gurobipy_code",
            "pulp": "to_pulp_code",
            "pyomo": "to_pyomo_code",
        }[python_api],
    }
    if ext not in writers:
        raise SystemExit(f"cannot write {ext!r} files; supported: .json .tex {' '.join(writers)}")
    import lp2graph.interop as interop

    writer = getattr(interop, writers[ext])
    return writer(f, instance)  # type: ignore[no-any-return]


def _emit(text: str, output: Path | None) -> None:
    if output is not None:
        output.write_text(text, encoding="utf-8")
        print(f"wrote {output}")
    else:
        print(text)


def _derive(f: Formulation, view: str, card_args: list[str]) -> Graph:
    if view == "schema":
        return _views.schema(f)
    if view == "hybrid":
        return _views.hybrid(f)
    cards = {k: int(v) for arg in card_args for k, v in [arg.split("=", 1)]}
    return _views.ground(f, cards)


if __name__ == "__main__":
    sys.exit(main())
