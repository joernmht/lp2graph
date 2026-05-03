"""Example 1: load and validate every formulation in the catalog."""

from __future__ import annotations

from pathlib import Path

from optgraph import load

ROOT = Path(__file__).resolve().parents[1]
FORMULATIONS = ROOT / "formulations"


def main() -> None:
    paths = sorted(FORMULATIONS.rglob("*.json"))
    print(f"Loading {len(paths)} formulation(s)...")
    for p in paths:
        f = load(p)
        print(
            f"  {f.id:36s} {f.family:5s}  "
            f"vars={len(f.variables):2d}  consts={len(f.constraints):2d}  "
            f"obj={'yes' if f.objective else 'no '}"
        )
    print("OK")


if __name__ == "__main__":
    main()
