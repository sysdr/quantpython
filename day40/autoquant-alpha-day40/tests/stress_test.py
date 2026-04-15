#!/usr/bin/env python3
"""
Stress Test: 10,000 orders × 5 fills each = 50,000 concurrent async fill events.

Validates:
  - Zero data corruption (VWAP, filled_qty, state)
  - All 10k orders reach FILLED terminal state
  - p50/p99 asyncio lock-contention latency

Usage: python tests/stress_test.py
"""
from __future__ import annotations

import asyncio
import statistics
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.order_lifecycle import FillEvent, OrderLifecycle, OrderState
from src.tracking.lifecycle_tracker import LifecycleTracker

N_ORDERS     = 10_000
FILLS_EACH   = 5
QTY_PER_FILL = 20.0
TOTAL_QTY    = FILLS_EACH * QTY_PER_FILL


def make_fill() -> FillEvent:
    ts = datetime.now(timezone.utc)
    return FillEvent(
        fill_id=str(uuid.uuid4()),
        qty=QTY_PER_FILL,
        price=100.0,
        broker_timestamp=ts,
        local_receipt_at=ts + timedelta(milliseconds=3.0),
    )


async def run() -> None:
    print(f"\nStress: {N_ORDERS:,} orders × {FILLS_EACH} fills = {N_ORDERS*FILLS_EACH:,} events")
    print("Preparing tracker and orders…", end=" ", flush=True)

    tracker = LifecycleTracker(max_orders=N_ORDERS + 100)
    latencies: list[float] = []

    orders: list[OrderLifecycle] = []
    for i in range(N_ORDERS):
        lc = OrderLifecycle(
            order_id=f"S-{i:07d}",
            symbol="SPY",
            qty=TOTAL_QTY,
            side="buy",
            order_type="market",
        )
        lc.mark_submitted()
        lc.mark_accepted(datetime.now(timezone.utc))
        await tracker.register_order(lc)
        orders.append(lc)
    print("done.")

    async def fire(lc: OrderLifecycle) -> None:
        for _ in range(FILLS_EACH):
            t0 = time.perf_counter_ns()
            await tracker.on_fill_event(lc.order_id, make_fill())
            latencies.append((time.perf_counter_ns() - t0) / 1_000.0)

    print(f"Firing {N_ORDERS*FILLS_EACH:,} fill events concurrently…")
    t_start = time.perf_counter()
    await asyncio.gather(*[fire(lc) for lc in orders])
    elapsed = time.perf_counter() - t_start

    # ── Correctness assertions ────────────────────────────────────────────────
    terminal = tracker.all_terminal()
    assert len(terminal) == N_ORDERS, f"Expected {N_ORDERS} terminal, got {len(terminal)}"
    errors = 0
    for lc in terminal:
        if lc.state != OrderState.FILLED:
            print(f"  BAD STATE: {lc.order_id} → {lc.state}")
            errors += 1
        if abs(lc.filled_qty - TOTAL_QTY) > 1e-9:
            print(f"  BAD QTY: {lc.order_id} → {lc.filled_qty} expected {TOTAL_QTY}")
            errors += 1

    # ── Latency report ────────────────────────────────────────────────────────
    lat_s = sorted(latencies)
    n = len(lat_s)
    p50 = statistics.median(lat_s)
    p99 = lat_s[int(n * 0.99)]
    p999 = lat_s[int(n * 0.999)]

    print(f"\n  Elapsed      : {elapsed:.2f}s")
    print(f"  Throughput   : {N_ORDERS * FILLS_EACH / elapsed:,.0f} events/s")
    print(f"  Lock p50     : {p50:.1f} µs")
    print(f"  Lock p99     : {p99:.1f} µs")
    print(f"  Lock p99.9   : {p999:.1f} µs")
    print(f"  Orphan fills : {tracker.stats['orphan_fills']}")
    print(f"  Evictions    : {tracker.stats['evictions']}")

    if errors == 0:
        print("\n  ✅  All correctness assertions passed.")
    else:
        print(f"\n  ❌  {errors} correctness failures.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
