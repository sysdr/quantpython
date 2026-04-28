"""
Stress test: 10,000 synthetic fill computations.
Success criterion: < 800ms wall time for fill math on typical dev HW (no I/O).
Run: python tests/stress_test.py
"""
from __future__ import annotations

import sys
import time
from decimal import Decimal
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.engine.fill_engine import (
    Quote, Side, FillResult, compute_arrival_price
)
from src.engine.slippage_tracker import SlippageTracker


N = 10_000


def run_stress_test() -> None:
    print(f"\n=== Stress Test: {N:,} fill computations ===\n")

    # Generate synthetic market data
    rng = np.random.default_rng(42)
    mids = rng.uniform(100.0, 600.0, size=N)
    spreads = rng.uniform(0.01, 0.10, size=N)
    noise = rng.normal(0.5, 0.8, size=N)  # fill noise in bps

    tracker = SlippageTracker(window=N)

    t0 = time.perf_counter()

    for i in range(N):
        mid = mids[i]
        half = spreads[i] / 2
        q = Quote.from_floats(bid=mid - half, ask=mid + half)
        side = Side.BUY if i % 2 == 0 else Side.SELL
        arrival = compute_arrival_price(q, side)

        fill_noise = float(arrival) * noise[i] / 10_000
        fill_price = Decimal(str(round(float(arrival) + fill_noise, 4)))

        fill = FillResult(
            order_id=f"stress-{i}",
            symbol="SYN",
            side=side,
            qty=Decimal("10"),
            arrival_mid=q.mid,
            arrival_price=arrival,
            fill_price=fill_price,
            fill_timestamp_ns=0,
        )
        tracker.record(fill.slippage_bps)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    stats = tracker.stats()

    print(f"  Fills computed:   {N:,}")
    print(f"  Total time:       {elapsed_ms:.1f}ms")
    print(f"  Per-fill:         {elapsed_ms / N * 1000:.2f}µs")
    print()
    print(f"  Mean slippage:    {stats.mean_bps:+.3f} bps")
    print(f"  Std slippage:     {stats.std_bps:.3f} bps")
    print(f"  P95 slippage:     {stats.p95_bps:+.3f} bps")
    print(f"  P99 slippage:     {stats.p99_bps:+.3f} bps")
    print()

    if elapsed_ms < 800:
        print(f"  ✓  PASS: {elapsed_ms:.1f}ms < 800ms target")
    else:
        print(f"  ✗  FAIL: {elapsed_ms:.1f}ms exceeded 800ms target")
        sys.exit(1)

    print()


if __name__ == "__main__":
    run_stress_test()
