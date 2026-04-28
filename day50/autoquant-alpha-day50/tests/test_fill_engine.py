"""
Unit tests for fill engine financial math.
Run: python -m pytest tests/test_fill_engine.py -v
"""
from __future__ import annotations

from decimal import Decimal

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.engine.fill_engine import (
    Quote, Side, FillResult, compute_arrival_price, estimate_market_impact_bps
)
from src.engine.slippage_tracker import SlippageTracker


class TestQuote:
    def test_mid_is_decimal_accurate(self):
        q = Quote.from_floats(bid=99.98, ask=100.02)
        assert q.mid == Decimal("100.0000")

    def test_spread_bps_correct(self):
        q = Quote.from_floats(bid=100.0, ask=100.02)
        spread = q.spread_bps
        assert abs(spread - 2.0) < 0.01

    def test_frozen_prevents_mutation(self):
        q = Quote.from_floats(bid=10.0, ask=10.02)
        with pytest.raises((AttributeError, TypeError)):
            q.bid = Decimal("11.0")  # type: ignore


class TestArrivalPriceFillEngine:
    def test_buy_fills_at_ask(self):
        q = Quote.from_floats(bid=99.98, ask=100.02)
        price = compute_arrival_price(q, Side.BUY)
        assert price == q.ask

    def test_sell_fills_at_bid(self):
        q = Quote.from_floats(bid=99.98, ask=100.02)
        price = compute_arrival_price(q, Side.SELL)
        assert price == q.bid

    def test_buy_slippage_positive_above_mid(self):
        mid = Decimal("100.00")
        fill = FillResult(
            order_id="x", symbol="SPY", side=Side.BUY,
            qty=Decimal("1"), arrival_mid=mid,
            arrival_price=Decimal("100.02"),
            fill_price=Decimal("100.05"),
            fill_timestamp_ns=0,
        )
        assert fill.slippage_bps > 0

    def test_buy_slippage_zero_at_mid(self):
        mid = Decimal("100.00")
        fill = FillResult(
            order_id="x", symbol="SPY", side=Side.BUY,
            qty=Decimal("1"), arrival_mid=mid,
            arrival_price=Decimal("100.02"),
            fill_price=mid,  # fill exactly at mid (lucky!)
            fill_timestamp_ns=0,
        )
        assert fill.slippage_bps == pytest.approx(0.0, abs=0.001)

    def test_sell_slippage_positive_below_mid(self):
        mid = Decimal("100.00")
        fill = FillResult(
            order_id="x", symbol="SPY", side=Side.SELL,
            qty=Decimal("1"), arrival_mid=mid,
            arrival_price=Decimal("99.98"),
            fill_price=Decimal("99.90"),
            fill_timestamp_ns=0,
        )
        assert fill.slippage_bps > 0


class TestSlippageTracker:
    def test_empty_stats_are_zero(self):
        t = SlippageTracker(window=10)
        s = t.stats()
        assert s.count == 0
        assert s.mean_bps == 0.0

    def test_mean_correct(self):
        t = SlippageTracker(window=100)
        for v in [1.0, 2.0, 3.0]:
            t.record(v)
        assert t.stats().mean_bps == pytest.approx(2.0, abs=0.001)

    def test_ring_buffer_wraps(self):
        t = SlippageTracker(window=3)
        for v in [1.0, 2.0, 3.0, 10.0]:  # 10.0 overwrites 1.0
            t.record(v)
        s = t.stats()
        assert s.count == 3
        assert s.mean_bps == pytest.approx(5.0, abs=0.01)

    def test_alarm_triggers(self):
        t = SlippageTracker(window=10)
        for _ in range(5):
            t.record(6.0)
        assert t.is_alarming(threshold_bps=5.0) is True

    def test_reset_clears_buffer(self):
        t = SlippageTracker(window=10)
        t.record(5.0)
        t.reset()
        assert t.stats().count == 0


class TestMarketImpact:
    def test_zero_adv_returns_zero(self):
        assert estimate_market_impact_bps(Decimal("100"), Decimal("0")) == 0.0

    def test_small_participation_low_impact(self):
        # 100 shares / 1M ADV = 0.01% participation
        impact = estimate_market_impact_bps(Decimal("100"), Decimal("1_000_000"))
        assert impact < 0.5  # should be tiny
