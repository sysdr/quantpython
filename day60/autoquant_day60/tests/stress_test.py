#!/usr/bin/env python3.11
"""
Stress Test: ATR engine under 100K tick flood.
Validates performance and numeric stability.
"""

from __future__ import annotations

import sys
import time
import random
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.atr_engine import ATREngine, OHLCTick
from src.slippage_model import SlippageModel, OrderSide


def stress_atr_engine(n_ticks: int = 100_000, period: int = 14) -> None:
    engine = ATREngine(period=period)
    model = SlippageModel()

    price = 150.0
    latencies_us: list[float] = []

    for i in range(n_ticks):
        high = price * (1 + abs(random.gauss(0, 0.005)))
        low = price * (1 - abs(random.gauss(0, 0.005)))
        close = price * (1 + random.gauss(0, 0.003))
        price = close
        tick = OHLCTick(high=high, low=low, close=close)

        t0 = time.perf_counter_ns()
        atr = engine.update(tick)
        elapsed_ns = time.perf_counter_ns() - t0
        latencies_us.append(elapsed_ns / 1_000.0)

        if atr is not None and i % 10_000 == 0:
            est = model.estimate("TEST", OrderSide.BUY, close, atr)
            assert 0 < est.predicted_bps <= model.max_bps, (
                f"Slippage out of bounds at tick {i}: {est.predicted_bps}"
            )

    p50 = statistics.median(latencies_us)
    p99 = sorted(latencies_us)[int(0.99 * len(latencies_us))]
    print(f"\nStress Test: {n_ticks:,} ticks | period={period}")
    print(f"  ATR update latency — p50: {p50:.2f}µs  p99: {p99:.2f}µs")
    print(f"  Final ATR: {engine.value:.6f}")

    assert p99 < 500.0, f"p99 latency {p99:.1f}µs exceeds 500µs threshold!"
    assert engine.is_ready
    print("  [PASS] Stress test passed.\n")


if __name__ == "__main__":
    stress_atr_engine(100_000)
