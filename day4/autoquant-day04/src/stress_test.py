"""
Stress test: 500 assets, 100,000 warm lookups.
Measures P50/P95/P99/Max latency.
"""
from __future__ import annotations

import random
import time

from src.asset_registry import AssetRegistry
from src.asset_metadata import AssetMetadata


def make_mock(sym: str) -> AssetMetadata:
    return AssetMetadata(
        symbol=sym, exchange="NASDAQ", asset_class="us_equity",
        tradable=True, fractionable=True, min_order_size=1.0,
        price_increment=0.01, fetched_at=time.monotonic(), ttl_seconds=3600.0,
    )


def run():
    N_ASSETS = 500
    N_LOOKUPS = 100_000

    symbols = [f"SYM{i:04d}" for i in range(N_ASSETS)]
    registry = AssetRegistry(ttl_seconds=3600.0)
    for sym in symbols:
        registry._store[sym] = make_mock(sym)

    print(f"Stress test: {N_LOOKUPS:,} lookups across {N_ASSETS} assets (warm cache)\n")

    times_ms = []
    t_total = time.monotonic()
    for _ in range(N_LOOKUPS):
        sym = random.choice(symbols)
        t0 = time.perf_counter()
        _ = registry[sym]
        times_ms.append((time.perf_counter() - t0) * 1_000)

    total_s = time.monotonic() - t_total
    times_ms.sort()
    p = lambda pct: times_ms[int(len(times_ms) * pct)]

    print(f"  Total wall time : {total_s*1000:.1f}ms")
    print(f"  Throughput      : {N_LOOKUPS/total_s:,.0f} lookups/sec")
    print(f"  P50 latency     : {p(0.50):.4f}ms")
    print(f"  P95 latency     : {p(0.95):.4f}ms")
    print(f"  P99 latency     : {p(0.99):.4f}ms")
    print(f"  Max latency     : {times_ms[-1]:.4f}ms")
    print(f"\n  Hit rate        : {registry.hit_rate:.2%}")

    if p(0.99) < 5.0:
        print("\n  \033[92m✓ P99 < 5ms — PASS\033[0m")
    else:
        print(f"\n  \033[91m✗ P99 {p(0.99):.3f}ms > 5ms — FAIL\033[0m")


if __name__ == "__main__":
    run()
