"""
tests/test_margin.py
Unit tests for MarginAccount — math, concurrency, PDT enforcement.
"""
from __future__ import annotations

import threading
import unittest
from decimal import Decimal

from src.margin.account import (
    AccountMode, MarginAccount, MarginHealth, PDT_EQUITY_THRESHOLD
)


class TestDecimalPrecision(unittest.TestCase):
    def test_equity_calculation_no_float_drift(self):
        acct = MarginAccount(Decimal("100000.00"))
        snap = acct.snapshot()
        # Exact equality — no IEEE754 drift
        self.assertEqual(snap.equity, Decimal("100000.00"))

    def test_rejects_float_input(self):
        with self.assertRaises(TypeError):
            MarginAccount(100000.0)


class TestBuyingPower(unittest.TestCase):
    def setUp(self):
        self.acct = MarginAccount(Decimal("50000.00"), mode=AccountMode.DAY_TRADE)

    def test_day_trade_bp_is_4x_equity(self):
        snap = self.acct.snapshot()
        self.assertEqual(snap.buying_power.day_trade_bp, Decimal("200000.00"))

    def test_overnight_bp_is_2x_equity(self):
        snap = self.acct.snapshot()
        self.assertEqual(snap.buying_power.overnight_bp, Decimal("100000.00"))

    def test_bp_reduces_after_reservation(self):
        self.acct.reserve("order-1", Decimal("20000.00"))
        snap = self.acct.snapshot()
        self.assertEqual(snap.buying_power.day_trade_bp, Decimal("180000.00"))


class TestAtomicReserve(unittest.TestCase):
    def setUp(self):
        self.acct = MarginAccount(Decimal("10000.00"), mode=AccountMode.DAY_TRADE)

    def test_reserve_success(self):
        r = self.acct.reserve("o1", Decimal("5000.00"))
        self.assertTrue(r.success)

    def test_reserve_exceeds_bp_fails(self):
        r = self.acct.reserve("o1", Decimal("500000.00"))
        self.assertFalse(r.success)
        self.assertEqual(r.reason, "INSUFFICIENT_BUYING_POWER")

    def test_duplicate_order_id_fails(self):
        self.acct.reserve("o1", Decimal("100.00"))
        r = self.acct.reserve("o1", Decimal("100.00"))
        self.assertFalse(r.success)
        self.assertEqual(r.reason, "DUPLICATE_ORDER_ID")

    def test_release_restores_bp(self):
        self.acct.reserve("o1", Decimal("5000.00"))
        self.acct.release("o1")
        snap = self.acct.snapshot()
        self.assertEqual(snap.reserved, Decimal("0"))

    def test_confirm_updates_cash_and_position(self):
        self.acct.reserve("o1", Decimal("1000.00"))
        self.acct.confirm("o1", Decimal("1005.00"), "AAPL",
                          Decimal("10"), Decimal("100.50"))
        snap = self.acct.snapshot()
        self.assertIn("AAPL", self.acct.positions)
        self.assertEqual(snap.cash, Decimal("8995.00"))


class TestConcurrentReserve(unittest.TestCase):
    """
    Stress test: 50 threads simultaneously try to reserve $1000 from a $10k account.
    Total approved must never exceed initial buying power.
    """

    def test_no_buying_power_violation(self):
        acct = MarginAccount(Decimal("10000.00"), mode=AccountMode.CASH)
        results = []
        lock = threading.Lock()

        def attempt(i: int):
            r = acct.reserve(f"order-{i}", Decimal("1000.00"))
            with lock:
                results.append(r.success)

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        approved = sum(results)
        # Cash mode: $10k / $1000 = exactly 10 approvals
        self.assertLessEqual(approved, 10)
        snap = acct.snapshot()
        self.assertLessEqual(snap.reserved, Decimal("10000.00"))


class TestPDTRule(unittest.TestCase):
    def test_pdt_restriction_triggers_below_25k(self):
        acct = MarginAccount(Decimal("24000.00"), mode=AccountMode.DAY_TRADE)
        # Record 4 day trades
        for _ in range(4):
            acct.record_day_trade()
        snap = acct.snapshot()
        self.assertEqual(snap.buying_power.mode.name, "CASH")

    def test_no_pdt_restriction_above_25k(self):
        acct = MarginAccount(Decimal("26000.00"), mode=AccountMode.DAY_TRADE)
        for _ in range(4):
            acct.record_day_trade()
        snap = acct.snapshot()
        self.assertEqual(snap.buying_power.mode.name, "DAY_TRADE")


class TestMarginHealth(unittest.TestCase):
    def test_healthy_with_no_positions(self):
        acct = MarginAccount(Decimal("50000.00"))
        snap = acct.snapshot()
        self.assertEqual(snap.health, MarginHealth.HEALTHY)

    def test_margin_call_detected(self):
        acct = MarginAccount(Decimal("10000.00"), mode=AccountMode.DAY_TRADE)
        # Reserve + confirm a large leveraged position
        acct.reserve("o1", Decimal("8000.00"))
        acct.confirm("o1", Decimal("8000.00"), "SPY",
                     Decimal("20"), Decimal("400.00"))
        # Crash the price by 80%
        acct.update_prices({"SPY": Decimal("80.00")})
        snap = acct.snapshot()
        self.assertIn(snap.health, [MarginHealth.MARGIN_CALL, MarginHealth.LIQUIDATING])


if __name__ == "__main__":
    unittest.main()
