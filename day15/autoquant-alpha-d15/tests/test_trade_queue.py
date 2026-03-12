"""
Unit tests for TradeQueue FIFO semantics, circuit breaker, and state transitions.
Run: pytest tests/test_trade_queue.py -v
"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.models.order import OrderSide, OrderState, TradeOrder
from src.queue_engine.trade_queue import TradeQueue


def _order(symbol: str = "AAPL", qty: float = 1.0) -> TradeOrder:
    return TradeOrder(symbol=symbol, qty=qty, side=OrderSide.BUY)


class TestFIFOSemantics:
    """FIFO invariant: dequeue order must match enqueue order."""

    @pytest.mark.asyncio
    async def test_fifo_three_symbols(self) -> None:
        q = TradeQueue(maxsize=10)
        symbols = ["AAPL", "MSFT", "GOOG"]
        for s in symbols:
            await q.enqueue(_order(s))
        for expected in symbols:
            got = await q.dequeue()
            assert got.symbol == expected, f"FIFO violated: expected {expected}, got {got.symbol}"

    @pytest.mark.asyncio
    async def test_fifo_preserves_insertion_order_at_scale(self) -> None:
        n = 200
        q = TradeQueue(maxsize=n)
        orders = [_order(f"SYM{i:04d}") for i in range(n)]
        for o in orders:
            await q.enqueue(o)
        for expected_order in orders:
            got = await q.dequeue()
            assert got.order_id == expected_order.order_id


class TestStateTransitions:

    @pytest.mark.asyncio
    async def test_pending_to_queued_on_enqueue(self) -> None:
        q = TradeQueue()
        o = _order()
        assert o.state == OrderState.PENDING
        await q.enqueue(o)
        assert o.state == OrderState.QUEUED

    @pytest.mark.asyncio
    async def test_circuit_breaker_sets_dlq_state(self) -> None:
        q = TradeQueue(maxsize=2)
        o1, o2, o3 = _order(), _order(), _order()
        assert await q.enqueue(o1) is True
        assert await q.enqueue(o2) is True
        # Third must fail
        assert await q.enqueue(o3) is False
        assert o3.state == OrderState.DLQ
        assert o3.error is not None
        assert "capacity" in o3.error.lower()


class TestCircuitBreaker:

    @pytest.mark.asyncio
    async def test_dropped_counter_increments(self) -> None:
        q = TradeQueue(maxsize=1)
        await q.enqueue(_order())   # fills queue
        await q.enqueue(_order())   # dropped
        await q.enqueue(_order())   # dropped
        assert q.stats().dropped == 2

    @pytest.mark.asyncio
    async def test_stats_accounting(self) -> None:
        q = TradeQueue(maxsize=10)
        for _ in range(7):
            await q.enqueue(_order())
        for _ in range(3):
            await q.dequeue()
        s = q.stats()
        assert s.enqueued == 7
        assert s.dequeued == 3
        assert s.depth == 4
        assert s.dropped == 0


class TestLatencyMeasurement:

    @pytest.mark.asyncio
    async def test_queue_latency_increases_over_time(self) -> None:
        q = TradeQueue()
        o = _order()
        await q.enqueue(o)
        await asyncio.sleep(0.015)   # simulate 15ms queue wait
        o.submitted_ns = time.monotonic_ns()
        lat = o.queue_latency_ms()
        assert lat is not None
        assert lat >= 15.0, f"Expected >=15ms, got {lat:.2f}ms"

    @pytest.mark.asyncio
    async def test_slippage_calculation(self) -> None:
        o = TradeOrder(symbol="AAPL", qty=1.0, side=OrderSide.BUY, limit_px=100.0)
        o.filled_px = 100.5   # 50bps slippage
        slippage = o.slippage_bps()
        assert slippage is not None
        assert abs(slippage - 50.0) < 0.01
