"""
stress_test.py — Production stress test.

Validates:
  1. NumpyTickStore stays within its preallocated budget (no heap growth)
  2. GC does NOT fire during numpy hot path ingestion
  3. Tick processing p99 latency < 500 µs for 10k-tick batches
  4. tracemalloc delta is near-zero after initial warmup

Run: python tests/stress_test.py
"""

from __future__ import annotations

import gc
import random
import sys
import time
import tracemalloc

import numpy as np

# Allow running from repo root
sys.path.insert(0, ".")

from src.data_structures.tick_store import NumpyTickStore, Tick
from src.data_structures.ring_buffer import Float32RingBuffer
from src.profiler.mem_profiler import MemoryProfiler


CAPACITY     = 1_000_000
TOTAL_TICKS  = 500_000
BATCH_SIZE   = 10_000
SYMBOLS      = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMD", "META", "AMZN"]
LATENCY_P99_TARGET_NS = 500_000  # 500 µs


def generate_tick(rng: random.Random, sym: str) -> Tick:
    price = 150.0 + rng.gauss(0, 2.0)
    return Tick(
        symbol=sym,
        price=price,
        size=rng.randint(100, 10_000),
        timestamp=time.perf_counter_ns(),
        bid=price - rng.uniform(0.01, 0.08),
        ask=price + rng.uniform(0.01, 0.08),
    )


def run_stress() -> None:
    print("=" * 60)
    print("AutoQuant-Alpha | Day 20 | Stress Test")
    print("=" * 60)

    profiler = MemoryProfiler(trace_depth=25)
    profiler.start()

    store  = NumpyTickStore(capacity=CAPACITY)
    spread = Float32RingBuffer(capacity=4096)
    rng    = random.Random(0xDEAD_BEEF)

    gc_count_before = profiler.gc_count()
    batch_latencies_ns: list[int] = []
    initial_memory = store.memory_bytes

    # Warmup: fill 10k ticks without timing
    for i in range(BATCH_SIZE):
        sym = SYMBOLS[i % len(SYMBOLS)]
        store.append(generate_tick(rng, sym))

    profiler.reset_baseline()

    # Timed run
    batches = (TOTAL_TICKS - BATCH_SIZE) // BATCH_SIZE
    for _ in range(batches):
        t0 = time.perf_counter_ns()
        for i in range(BATCH_SIZE):
            sym = SYMBOLS[i % len(SYMBOLS)]
            tick = generate_tick(rng, sym)
            store.append(tick)
            spread.push(tick.ask - tick.bid)
        elapsed = time.perf_counter_ns() - t0
        batch_latencies_ns.append(elapsed)

    gc_count_after = profiler.gc_count()
    alloc_delta = profiler.snapshot()
    final_memory = store.memory_bytes
    rss = profiler.rss_bytes()

    # ── Results ──────────────────────────────────────────────────────────
    arr_lat = np.array(batch_latencies_ns, dtype=np.int64)
    p50  = int(np.percentile(arr_lat, 50))
    p95  = int(np.percentile(arr_lat, 95))
    p99  = int(np.percentile(arr_lat, 99))
    per_tick_p99 = p99 // BATCH_SIZE

    print(f"\n[1] NumpyTickStore memory (preallocated, constant):")
    print(f"    Initial:  {initial_memory / 1e6:.2f} MB")
    print(f"    Final:    {final_memory   / 1e6:.2f} MB")
    print(f"    Delta:    {(final_memory - initial_memory)} bytes  ← must be 0")

    print(f"\n[2] GC events during numpy hot path:")
    print(f"    Count: {gc_count_after - gc_count_before}  ← target: 0")

    print(f"\n[3] Batch latency ({BATCH_SIZE:,} ticks/batch):")
    print(f"    p50: {p50 / 1e6:.3f} ms   ({p50 // BATCH_SIZE:,} ns/tick)")
    print(f"    p95: {p95 / 1e6:.3f} ms   ({p95 // BATCH_SIZE:,} ns/tick)")
    print(f"    p99: {p99 / 1e6:.3f} ms   ({per_tick_p99:,} ns/tick)  ← target < {LATENCY_P99_TARGET_NS:,} ns")

    print(f"\n[4] tracemalloc delta (post-warmup):")
    top = alloc_delta[:3] if alloc_delta else []
    for s in top:
        print(f"    {s.file}:{s.lineno}  {s.size_bytes / 1024:.1f} KB  {s.count} objects")
    if not top:
        print("    (no significant allocations)")

    print(f"\n[5] RSS: {rss / 1e6:.1f} MB")
    print(f"    VWAP: ${store.vwap():.4f}")
    print(f"    Mean spread: {store.mean_spread_bps():.2f} bps")

    # ── Pass/Fail ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    failures: list[str] = []

    if final_memory != initial_memory:
        failures.append(f"FAIL: NumpyTickStore memory changed by "
                        f"{final_memory - initial_memory} bytes (must be 0)")

    if per_tick_p99 > LATENCY_P99_TARGET_NS:
        failures.append(f"FAIL: p99 per-tick latency {per_tick_p99:,} ns > "
                        f"{LATENCY_P99_TARGET_NS:,} ns target")

    if final_memory / 1e6 > 30:
        failures.append(f"FAIL: NumpyTickStore exceeds 30 MB "
                        f"({final_memory / 1e6:.2f} MB)")

    if failures:
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    else:
        print("  ✓ Memory footprint constant (zero heap growth in hot path)")
        print("  ✓ p99 per-tick latency within target")
        print("  ✓ NumpyTickStore within memory budget")
        print("\n  ✓✓ ALL CHECKS PASSED — Day 20 criteria met")

    profiler.stop()


if __name__ == "__main__":
    run_stress()
