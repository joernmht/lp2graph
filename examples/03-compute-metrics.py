"""Example 3: compute every metric on every catalog formulation."""

from __future__ import annotations

from pathlib import Path

from optgraph import load
from optgraph.metrics.flags import presence_flags
from optgraph.metrics.structural import structural_summary
from optgraph.views import schema

ROOT = Path(__file__).resolve().parents[1]
FORMULATIONS = ROOT / "formulations"


def main() -> None:
    print(f"{'id':36s}  diam  cv-ratio  big-m  ints  slack  agg")
    print("-" * 85)
    for p in sorted(FORMULATIONS.rglob("*.json")):
        f = load(p)
        g = schema(f)
        s = structural_summary(g)
        flags = presence_flags(f)
        print(
            f"{f.id:36s}  {s['graph_diameter'].value:4d}  "
            f"{s['constraint_variable_ratio'].value:8.2f}  "
            f"{str(flags['has_big_m'].value):5s}  "
            f"{str(flags['has_integer_vars'].value):5s}  "
            f"{str(flags['has_soft_slack'].value):5s}  "
            f"{str(flags['has_aggregation_operator'].value):5s}"
        )


if __name__ == "__main__":
    main()
