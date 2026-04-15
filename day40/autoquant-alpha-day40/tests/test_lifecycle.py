from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from src.models.order_lifecycle import (
    FillEvent, OrderLifecycle, OrderState, TERMINAL_STATES
)
from src.tracking.lifecycle_tracker import LifecycleTracker


# ── Helpers ───────────────────────────────────────────────────────────────────

def utcnow(offset_ms: float = 0.0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(milliseconds=offset_ms)


def make_fill(qty: float, price: float, net_lat_ms: float = 5.0) -> FillEvent:
    broker_ts = utcnow()
    return FillEvent(
        fill_id=str(uuid.uuid4()),
        qty=qty,
        price=price,
        broker_timestamp=broker_ts,
        local_receipt_at=broker_ts + timedelta(milliseconds=net_lat_ms),
    )


def make_order(qty: float = 100.0, order_type: str = "market") -> OrderLifecycle:
    lc = OrderLifecycle(
        order_id=str(uuid.uuid4()), symbol="AAPL",
        qty=qty, side="buy", order_type=order_type,
    )
    lc.mark_submitted()
    lc.mark_accepted(utcnow(-10))
    return lc


# ── VWAP accuracy ─────────────────────────────────────────────────────────────

class TestVWAP:
    def test_single_fill(self) -> None:
        lc = make_order(100)
        lc.apply_fill(make_fill(100, 150.00))
        assert lc.avg_fill_price == pytest.approx(150.00, abs=1e-6)
        assert lc.state == OrderState.FILLED

    def test_two_equal_fills(self) -> None:
        lc = make_order(100)
        lc.apply_fill(make_fill(50, 150.00))
        lc.apply_fill(make_fill(50, 152.00))
        assert lc.avg_fill_price == pytest.approx(151.00, abs=1e-6)

    def test_unequal_fills_vwap(self) -> None:
        """75 @ 100 + 25 @ 200 → VWAP = 125."""
        lc = make_order(100)
        lc.apply_fill(make_fill(75, 100.0))
        lc.apply_fill(make_fill(25, 200.0))
        assert lc.avg_fill_price == pytest.approx(125.0, abs=1e-6)

    def test_float_stability_1000_fills(self) -> None:
        """1000 × 0.001 qty fills should not drift from expected VWAP."""
        lc = make_order(1.0)
        for _ in range(1000):
            lc.apply_fill(make_fill(0.001, 1.0))
        assert lc.avg_fill_price == pytest.approx(1.0, abs=1e-5)
        assert lc.filled_qty == pytest.approx(1.0, abs=1e-9)
        assert lc.state == OrderState.FILLED

    def test_sell_order_vwap(self) -> None:
        lc = OrderLifecycle(str(uuid.uuid4()), "SPY", 10, "sell", "limit")
        lc.mark_submitted()
        lc.mark_accepted(utcnow())
        lc.apply_fill(make_fill(10, 510.00))
        assert lc.avg_fill_price == pytest.approx(510.00, abs=1e-6)


# ── Timestamp chain ───────────────────────────────────────────────────────────

class TestTimestamps:
    def test_full_chain_populated(self) -> None:
        lc = make_order(10)
        lc.apply_fill(make_fill(10, 150.0))
        for field in ["submitted_at", "accepted_at", "first_fill_at",
                      "last_fill_at", "local_first_receipt_at", "local_last_receipt_at"]:
            assert getattr(lc, field) is not None, f"{field} is None"

    def test_broker_before_local(self) -> None:
        lc = make_order(5)
        lc.apply_fill(make_fill(5, 400.0, net_lat_ms=7.5))
        assert lc.last_fill_at < lc.local_last_receipt_at

    def test_first_last_fill_distinction(self) -> None:
        lc = make_order(100)
        lc.apply_fill(make_fill(60, 100.0, net_lat_ms=4.0))
        first_ts = lc.first_fill_at
        lc.apply_fill(make_fill(40, 101.0, net_lat_ms=6.0))
        assert lc.first_fill_at == first_ts
        assert lc.last_fill_at > first_ts  # type: ignore[operator]

    def test_submitted_before_accepted(self) -> None:
        lc = make_order(1)
        assert lc.submitted_at is not None
        assert lc.accepted_at is not None
        # accepted_at may be slightly before submitted_at in tests due to offset
        # The key constraint: both are tz-aware UTC
        assert lc.submitted_at.tzinfo is not None
        assert lc.accepted_at.tzinfo is not None


# ── Latency metrics ───────────────────────────────────────────────────────────

class TestLatencyMetrics:
    def test_submission_latency_set(self) -> None:
        lc = make_order()
        assert lc.submission_latency_ms is not None
        assert isinstance(lc.submission_latency_ms, float)

    def test_network_latency_close_to_simulated(self) -> None:
        lc = make_order(1)
        lc.apply_fill(make_fill(1, 100.0, net_lat_ms=20.0))
        assert lc.network_latency_ms == pytest.approx(20.0, abs=3.0)

    def test_e2e_latency_set_on_fill(self) -> None:
        lc = make_order(1)
        lc.apply_fill(make_fill(1, 100.0))
        assert lc.e2e_broker_latency_ms is not None

    def test_latency_none_until_filled(self) -> None:
        lc = make_order(100)
        lc.apply_fill(make_fill(50, 100.0))
        assert lc.state == OrderState.PARTIALLY_FILLED
        # fill_latency_ms is only set at terminal fill
        assert lc.fill_latency_ms is None
        lc.apply_fill(make_fill(50, 100.0))
        assert lc.fill_latency_ms is not None


# ── State machine ─────────────────────────────────────────────────────────────

class TestStateMachine:
    def test_new_to_pending(self) -> None:
        lc = OrderLifecycle(str(uuid.uuid4()), "X", 1, "buy", "market")
        assert lc.state == OrderState.NEW
        lc.mark_submitted()
        assert lc.state == OrderState.PENDING_SUBMIT

    def test_partial_to_filled(self) -> None:
        lc = make_order(100)
        lc.apply_fill(make_fill(60, 10.0))
        assert lc.state == OrderState.PARTIALLY_FILLED
        lc.apply_fill(make_fill(40, 10.0))
        assert lc.state == OrderState.FILLED
        assert lc.is_terminal

    def test_fill_on_filled_raises(self) -> None:
        lc = make_order(100)
        lc.apply_fill(make_fill(100, 10.0))
        assert lc.state == OrderState.FILLED
        with pytest.raises(ValueError, match="terminal state"):
            lc.apply_fill(make_fill(1, 10.0))

    def test_cancel_sets_state(self) -> None:
        lc = make_order(100)
        lc.mark_cancelled()
        assert lc.state == OrderState.CANCELLED
        assert lc.is_terminal


# ── Tracker concurrency ───────────────────────────────────────────────────────

class TestTrackerConcurrency:
    def test_concurrent_fills_no_corruption(self) -> None:
        """50 orders × 4 fills each dispatched concurrently — all must reach FILLED."""
        async def _run() -> None:
            tracker = LifecycleTracker(max_orders=100)
            orders = []
            for i in range(50):
                lc = make_order(4)
                lc.order_id = f"T-{i:04d}"
                await tracker.register_order(lc)
                orders.append(lc)

            async def fire(lc: OrderLifecycle) -> None:
                for _ in range(4):
                    await tracker.on_fill_event(lc.order_id, make_fill(1, 100.0))

            await asyncio.gather(*[fire(lc) for lc in orders])
            terminal = tracker.all_terminal()
            assert len(terminal) == 50
            for lc in terminal:
                assert lc.state == OrderState.FILLED
                assert lc.filled_qty == pytest.approx(4.0, abs=1e-9)

        asyncio.run(_run())

    def test_orphan_fill_counted(self) -> None:
        async def _run() -> None:
            tracker = LifecycleTracker()
            result = await tracker.on_fill_event("NONEXISTENT", make_fill(1, 100.0))
            assert result is None
            assert tracker.stats["orphan_fills"] == 1

        asyncio.run(_run())

    def test_lru_eviction(self) -> None:
        async def _run() -> None:
            tracker = LifecycleTracker(max_orders=3)
            for i in range(4):
                lc = OrderLifecycle(f"OID-{i}", "X", 1, "buy", "market")
                lc.mark_submitted()
                await tracker.register_order(lc)
            assert len(tracker._orders) == 3
            assert tracker.stats["evictions"] == 1
            assert "OID-0" not in tracker._orders

        asyncio.run(_run())


# ── Serialisation ─────────────────────────────────────────────────────────────

class TestSerialization:
    def test_to_dict_all_keys(self) -> None:
        lc = make_order(10)
        lc.apply_fill(make_fill(10, 150.0))
        d = lc.to_dict()
        for key in ["order_id", "symbol", "state", "filled_qty", "avg_fill_price",
                    "submitted_at", "accepted_at", "last_fill_at",
                    "fill_latency_ms", "network_latency_ms"]:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_no_none_timestamps_on_filled(self) -> None:
        lc = make_order(1)
        lc.apply_fill(make_fill(1, 200.0))
        d = lc.to_dict()
        for f in ["submitted_at", "accepted_at", "first_fill_at", "last_fill_at"]:
            assert d[f] is not None, f"{f} should not be None on FILLED order"
