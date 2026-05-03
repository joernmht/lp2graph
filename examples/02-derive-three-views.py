"""Example 2: derive the three views from a single formulation."""

from __future__ import annotations

from optgraph import load
from optgraph.views import ground, hybrid, schema


def main() -> None:
    f = load("formulations/constraints/mip_2_1_big_m.json")

    g_schema = schema(f)
    g_hybrid = hybrid(f)
    g_ground = ground(f, {"I": 4})

    for g in (g_schema, g_hybrid, g_ground):
        print(f"view={g.view:8s}  nodes={len(g.nodes):3d}  edges={len(g.edges):3d}")

    # Example offsets carried by hybrid edges:
    print("\nFirst few hybrid edges from constraint:order_a:")
    for e in g_hybrid.out_edges("constraint:order_a")[:3]:
        offsets = e.data.get("offsets", {})
        print(f"  -> {e.dst}  role={e.role}  offsets={dict(offsets)}")


if __name__ == "__main__":
    main()
