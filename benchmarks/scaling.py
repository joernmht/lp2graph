"""Scaling benchmark for lp2graph's size-sensitive paths (ADR-0017).

Not a test: wall-clock numbers depend on the machine, so CI asserts
*behaviour* (exactness, determinism) and this script measures *cost*. Run it
before and after a change to any path below and compare the growth between
rows -- a step that doubles the input should roughly double the time. A
quadratic path quadruples it, which is what this script exists to catch.

    PYTHONPATH=src python3 benchmarks/scaling.py            # default sizes
    PYTHONPATH=src python3 benchmarks/scaling.py --quick    # smaller, ~10 s

Inputs are generated from a fixed seed, so two runs measure the same models.
"""

from __future__ import annotations

import argparse
import random
import statistics
import time
from collections.abc import Callable
from pathlib import Path

from lp2graph import load
from lp2graph.interop.lp_format import from_lp_string
from lp2graph.interop.mps import from_mps_string, to_mps_string
from lp2graph.metrics.structural import structural_summary
from lp2graph.validation.pipeline import validate_text
from lp2graph.views import ground

ROOT = Path(__file__).resolve().parents[1]


def _ms(fn: Callable[[], object], repeat: int = 3) -> float:
    """Median wall-clock of ``repeat`` calls, in milliseconds."""
    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return statistics.median(times) * 1e3


def _sparse_lp(n: int, nnz_per_row: int = 5, seed: int = 0) -> str:
    """An ``n x n`` sparse covering LP in LP format: one template per column,
    the shape a flat import (MIPLIB-style) produces."""
    rng = random.Random(seed)
    lines = ["Minimize", " obj: " + " + ".join(f"{rng.randint(1, 9)} x{i}" for i in range(n))]
    lines.append("Subject To")
    for r in range(n):
        cols = sorted(rng.sample(range(n), nnz_per_row))
        body = " + ".join(f"{rng.randint(1, 9)} x{c}" for c in cols)
        lines.append(f" r{r}: {body} >= {rng.randint(1, 20)}")
    lines.append("End")
    return "\n".join(lines) + "\n"


def flat_import(sizes: list[int]) -> None:
    print("flat import (n rows x n columns, 5 nonzeros per row)")
    print(f"{'n':>7} {'from_lp':>10} {'from_mps':>10} {'validate_text':>14}")
    for n in sizes:
        lp = _sparse_lp(n)
        mps = to_mps_string(from_lp_string(lp, model_id="bench"))
        t_lp = _ms(lambda lp=lp: from_lp_string(lp, model_id="bench"))
        t_mps = _ms(lambda mps=mps: from_mps_string(mps, model_id="bench"))
        t_val = _ms(lambda lp=lp: validate_text(lp, fmt="lp", solve_check=False), repeat=1)
        print(f"{n:7d} {t_lp:8.0f}ms {t_mps:8.0f}ms {t_val:12.0f}ms")


def ground_metrics(sizes: list[int]) -> None:
    print("\nground view + structural metrics (every index at cardinality k)")
    print(f"{'model':>16} {'k':>4} {'nodes':>7} {'edges':>7} {'ground':>9} {'metrics':>9}")
    for name in ("assignment", "mip_2_1_big_m"):
        f = load(ROOT / "formulations" / "constraints" / f"{name}.json")
        for k in sizes:
            cards = {i.name: k for i in f.indices}
            g = ground(f, cards)
            t_g = _ms(lambda f=f, cards=cards: ground(f, cards), repeat=1)
            t_m = _ms(lambda g=g: structural_summary(g), repeat=1)
            print(
                f"{name:>16} {k:4d} {len(g.nodes):7d} {len(g.edges):7d} {t_g:7.0f}ms {t_m:7.0f}ms"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="smaller sizes")
    args = parser.parse_args()
    flat_import([250, 500, 1000] if args.quick else [500, 1000, 2000, 4000])
    ground_metrics([10, 20] if args.quick else [10, 20, 40])


if __name__ == "__main__":
    main()
