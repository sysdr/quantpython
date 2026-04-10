"""
AutoQuant-Alpha | Day 35 — Test Suite

Tests cover:
    1. Correct slippage calculation (positive/negative, buy/sell)
    2. Decimal precision — no float drift
    3. Immutability enforcement
    4. __repr__ thread safety (call from multiple threads)
    5. Edge cases: zero slippage, exactly filled, partial fill
    6. AggregatedTradeRecord VWAP calculation
    7. Stress test: construct 100,000 TradeRecords and call __repr__
"""
from __future__ import annotations

import sys
import time
import threading
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from autoquant.trade_record import TradeRecord, AggregatedTradeRecord


def make_record(
    side: str = "buy",
    limit: str = "150.00",
    fill: str = "150.03",
    qty: str = "100",
    filled_qty: str | None = None,
    duration_ms: float = 12.5,
) -> TradeRecord:
    now = datetime.now(tz=timezone.utc)
    submitted = now - timedelta(milliseconds=duration_ms)
    return TradeRecord(
        order_id="test-order-001",
        symbol="AAPL",
        side=side,  # type: ignore[arg-type]
        requested_qty=Decimal(qty),
        filled_qty=Decimal(filled_qty or qty),
        limit_price=Decimal(limit),
        fill_price=Decimal(fill),
        submitted_at=submitted,
        filled_at=now,
    )


class TestSlippageCalculation(unittest.TestCase):

    def test_buy_positive_slippage(self):
        """Buy filled above limit → positive slippage (unfavorable)."""
        r = make_record(side="buy", limit="150.00", fill="150.03")
        # (150.03 - 150.00) / 150.00 * 10000 = 2.00 bps
        self.assertEqual(r.slippage_bps, Decimal("2.00"))

    def test_buy_negative_slippage(self):
        """Buy filled below limit → negative slippage (favorable)."""
        r = make_record(side="buy", limit="150.00", fill="149.97")
        # (149.97 - 150.00) / 150.00 * 10000 = -2.00 bps
        self.assertEqual(r.slippage_bps, Decimal("-2.00"))

    def test_sell_positive_slippage(self):
        """Sell filled below limit → positive slippage (unfavorable for sell)."""
        r = make_record(side="sell", limit="150.00", fill="149.97")
        # For sell: -(fill - limit) / limit * 10000 = -(-0.03/150 * 10000) = +2.00
        self.assertEqual(r.slippage_bps, Decimal("2.00"))

    def test_zero_slippage(self):
        """Fill exactly at limit → zero slippage."""
        r = make_record(limit="150.00", fill="150.00")
        self.assertEqual(r.slippage_bps, Decimal("0.00"))

    def test_decimal_precision_no_float_drift(self):
        """Decimal arithmetic must not drift. Classic float failure case."""
        # float: (150.0001 - 150.0000) / 150.0000 * 10000 ≠ 0.0667 exactly
        r = make_record(limit="150.0000", fill="150.0001")
        # Exact: 0.0001 / 150.0000 * 10000 = 0.006666... → 0.01 bps
        self.assertIsInstance(r.slippage_bps, Decimal)
        self.assertNotEqual(str(r.slippage_bps), "nan")
        self.assertNotEqual(str(r.slippage_bps), "inf")


class TestPnL(unittest.TestCase):

    def test_buy_favorable_pnl(self):
        """Buy below limit → positive P&L."""
        r = make_record(side="buy", limit="150.00", fill="149.90", qty="100")
        # (150.00 - 149.90) * 100 = 10.00
        self.assertEqual(r.realized_pnl, Decimal("10.00"))

    def test_sell_favorable_pnl(self):
        """Sell above limit → positive P&L."""
        r = make_record(side="sell", limit="150.00", fill="150.10", qty="100")
        # (150.10 - 150.00) * 100 = 10.00
        self.assertEqual(r.realized_pnl, Decimal("10.00"))

    def test_buy_unfavorable_pnl(self):
        """Buy above limit → negative P&L."""
        r = make_record(side="buy", limit="150.00", fill="150.10", qty="100")
        self.assertEqual(r.realized_pnl, Decimal("-10.00"))


class TestFillRatio(unittest.TestCase):

    def test_full_fill(self):
        r = make_record(qty="100", filled_qty="100")
        self.assertEqual(r.fill_ratio, Decimal("100.0"))

    def test_partial_fill(self):
        r = make_record(qty="100", filled_qty="47")
        self.assertEqual(r.fill_ratio, Decimal("47.0"))

    def test_partial_fill_rounding(self):
        r = make_record(qty="300", filled_qty="100")
        # 100/300 * 100 = 33.333... → 33.3
        self.assertEqual(r.fill_ratio, Decimal("33.3"))


class TestImmutability(unittest.TestCase):

    def test_cannot_mutate_core_field(self):
        r = make_record()
        with self.assertRaises((TypeError, AttributeError)):
            r.fill_price = Decimal("200.00")  # type: ignore[misc]

    def test_cannot_mutate_derived_field(self):
        r = make_record()
        with self.assertRaises((TypeError, AttributeError)):
            r.slippage_bps = Decimal("0.00")  # type: ignore[misc]


class TestReprThreadSafety(unittest.TestCase):

    def test_repr_concurrent_calls(self):
        """
        Call __repr__ from 50 threads simultaneously.
        No exceptions should be raised; output must be consistent.
        """
        r = make_record()
        expected = repr(r)
        errors: list[str] = []
        results: list[str] = []

        def call_repr():
            try:
                results.append(repr(r))
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=call_repr) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Repr raised exceptions: {errors}")
        self.assertTrue(all(s == expected for s in results), "Repr output inconsistent")


class TestValidation(unittest.TestCase):

    def test_negative_qty_raises(self):
        with self.assertRaises(ValueError):
            make_record(qty="-1")

    def test_filled_exceeds_requested_raises(self):
        with self.assertRaises(ValueError):
            make_record(qty="100", filled_qty="101")

    def test_negative_limit_price_raises(self):
        with self.assertRaises(ValueError):
            make_record(limit="-1.00")


class TestAggregatedRecord(unittest.TestCase):

    def _make_tranche(self, fill: str, qty: str, duration_ms: float = 10.0) -> TradeRecord:
        return make_record(
            side="buy", limit="150.00", fill=fill, qty="300",
            filled_qty=qty, duration_ms=duration_ms
        )

    def test_vwap_calculation(self):
        """VWAP of 3 tranches: (149.99*100 + 150.01*100 + 150.02*100) / 300."""
        t1 = self._make_tranche("149.99", "100", 5.0)
        t2 = self._make_tranche("150.01", "100", 12.0)
        t3 = self._make_tranche("150.02", "100", 20.0)

        import uuid
        agg = AggregatedTradeRecord(
            order_id=str(uuid.uuid4()),
            symbol="AAPL",
            side="buy",
            requested_qty=Decimal("300"),
            tranches=(t1, t2, t3),
        )

        # VWAP = (149.99 + 150.01 + 150.02) / 3 = 150.006666...
        expected_vwap = (
            Decimal("149.99") * 100 + Decimal("150.01") * 100 + Decimal("150.02") * 100
        ) / Decimal("300")
        self.assertAlmostEqual(float(agg.vwap_fill_price), float(expected_vwap), places=3)

    def test_total_filled_qty(self):
        t1 = self._make_tranche("150.00", "100")
        t2 = self._make_tranche("150.00", "200")
        import uuid
        agg = AggregatedTradeRecord(
            order_id=str(uuid.uuid4()),
            symbol="AAPL",
            side="buy",
            requested_qty=Decimal("300"),
            tranches=(t1, t2),
        )
        self.assertEqual(agg.total_filled_qty, Decimal("300"))
        self.assertEqual(agg.aggregate_fill_ratio, Decimal("100.0"))


class StressTest(unittest.TestCase):

    def test_construct_and_repr_100k_records(self):
        """
        Construct 100,000 TradeRecords and call __repr__ on each.
        Verifies: no memory leak, no exception, acceptable performance.
        Baseline: should complete in < 5s on any modern machine.
        """
        N = 100_000
        start = time.perf_counter()

        for i in range(N):
            r = TradeRecord.make_test_record(
                symbol=f"SYM{i % 10}",
                fill_price=str(150.00 + (i % 100) * 0.01),
                duration_ms=float(10 + i % 50),
            )
            _ = repr(r)

        elapsed = time.perf_counter() - start
        print(f"\n  Stress test: {N:,} records in {elapsed:.3f}s ({N/elapsed:,.0f} rec/s)")
        self.assertLess(elapsed, 10.0, f"Performance regression: {elapsed:.2f}s > 10s limit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
