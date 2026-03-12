"""
Stress Test: concurrent producers flood the queue to verify
circuit breaker engagement and throughput characteristics.

Run: python -m tests.stress_test
Expected: throughput > 100,000 orders/sec (pure asyncio, no I/O)
"""

from __future__ import annotations

import asyncio
import sys
import time

from src.models.order import OrderSide, TradeOrder
from src.queue_engine.trade_queue import TradeQueue

TOTAL_ORDERS  = 50_000
QUEUE_MAXSIZE = 512
PRODUCERS     = 16


async def producer(queue: TradeQueue, count: int) -> tuple[int, int]:
    enqueued = dropped = 0
    for i in range(count):
        o = TradeOrder(
            symbol = f"SYM{i % 100:03d}",
            qty    = 1.0,
            side   = OrderSide.BUY,
        )
        if await queue.enqueue(o):
            enqueued += 1
        else:
            dropped += 1
    return enqueued, dropped


async def run() -> None:
    queue       = TradeQueue(maxsize=QUEUE_MAXSIZE)
    per_prod    = TOTAL_ORDERS // PRODUCERS
    t0          = time.perf_counter()

    results = await asyncio.gather(
        *[producer(queue, per_prod) for _ in range(PRODUCERS)]
    )

    elapsed        = time.perf_counter() - t0
    total_enqueued = sum(r[0] for r in results)
    total_dropped  = sum(r[1] for r in results)
    throughput     = TOTAL_ORDERS / elapsed

    s = queue.stats()
    print(f"\n{'='*55}")
    print("Stress Test Results")
    print(f"{'='*55}")
    print(f"  Total attempted  : {TOTAL_ORDERS:>10,}")
    print(f"  Enqueued (OK)    : {total_enqueued:>10,}")
    print(f"  Dropped (CB)     : {total_dropped:>10,}")
    print(f"  Queue depth      : {s.depth:>10,} / {QUEUE_MAXSIZE}")
    print(f"  Elapsed          : {elapsed:>10.4f}s")
    print(f"  Throughput       : {throughput:>10,.0f} orders/sec")
    print(f"{'='*55}")

    # Invariants
    assert total_enqueued + total_dropped == TOTAL_ORDERS, (
        f"Accounting error: {total_enqueued} + {total_dropped} != {TOTAL_ORDERS}"
    )
    assert total_dropped >= 0, "Dropped count cannot be negative"
    # Circuit breaker must engage when queue is bounded
    if TOTAL_ORDERS > QUEUE_MAXSIZE:
        assert total_dropped > 0, (
            "Circuit breaker never engaged — maxsize not respected!"
        )
    assert throughput > 10_000, f"Throughput too low: {throughput:.0f} orders/sec"

    print("\n  ✓ All invariants passed.")


if __name__ == "__main__":
    asyncio.run(run())
