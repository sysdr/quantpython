"""
Stress Test: on_tick() latency under HFT-scale tick volume.

Generates 100,000 synthetic ticks via Geometric Brownian Motion and
measures wall-clock latency for each on_tick() call.

Pass criterion: P99 latency < 1,000 µs (1 ms).
"""
import time
import statistics
import sys
import numpy as np

# Allow running from project root without install
import os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.types import MarketSnapshot
from src.strategies.momentum_scalp import MomentumScalp

TICK_COUNT = 100_000
P99_TARGET_US = 1_000.0   # 1 ms in microseconds


def gbm_ticks(n: int, s0: float = 100.0) -> list[MarketSnapshot]:
    """Synthetic price path via GBM. Deterministic (seed=42)."""
    rng     = np.random.default_rng(42)
    drifts  = rng.normal(0.0, 0.0002, n)
    prices  = s0 * np.exp(np.cumsum(drifts))
    spreads = rng.uniform(0.01, 0.05, n)
    volumes = rng.integers(10, 1_000, n).astype(int)
    base_ns = time.time_ns()
    return [
        MarketSnapshot(
            symbol       = "STRESS",
            bid          = float(prices[i]),
            ask          = float(prices[i] + spreads[i]),
            last         = float(prices[i]),
            volume       = int(volumes[i]),
            timestamp_ns = base_ns + i * 1_000_000,
        )
        for i in range(n)
    ]


def run() -> bool:
    print(f"[Stress] Generating {TICK_COUNT:,} GBM ticks ...")
    ticks = gbm_ticks(TICK_COUNT)

    strategy    = MomentumScalp(symbol="STRESS")
    latencies   : list[float] = []
    signal_count: int = 0

    print(f"[Stress] Running on_tick() ×{TICK_COUNT:,} ...")
    for tick in ticks:
        t0  = time.perf_counter_ns()
        sig = strategy.on_tick(tick)
        t1  = time.perf_counter_ns()
        latencies.append((t1 - t0) / 1_000.0)   # ns → µs
        if sig is not None:
            signal_count += 1

    latencies.sort()
    n   = len(latencies)
    p50 = statistics.median(latencies)
    p95 = latencies[int(n * 0.95)]
    p99 = latencies[int(n * 0.99)]
    p999= latencies[int(n * 0.999)]

    print("\n" + "═" * 52)
    print(f"  Stress Test  ·  {TICK_COUNT:,} ticks")
    print("═" * 52)
    print(f"  Signals generated : {signal_count:,}  ({signal_count/TICK_COUNT*100:.2f}%)")
    print(f"  Latency P50       : {p50:>8.1f} µs")
    print(f"  Latency P95       : {p95:>8.1f} µs")
    print(f"  Latency P99       : {p99:>8.1f} µs")
    print(f"  Latency P999      : {p999:>8.1f} µs")
    print("═" * 52)

    passed = p99 < P99_TARGET_US
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"\n{status}  P99={p99:.1f}µs  target=<{P99_TARGET_US:.0f}µs\n")
    return passed


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
