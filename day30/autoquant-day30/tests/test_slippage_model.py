"""
Unit tests for SlippageModel and OrderRecord financial math.
Run with: pytest tests/test_slippage_model.py -v
"""

from decimal import Decimal
from datetime import datetime, timezone

import pytest

from src.execution.slippage_model import SlippageModel, SlippageRegime, SlippageBreachError
from src.execution.market_order import OrderRecord


# ── SlippageModel tests ───────────────────────────────────────────────────────

class TestSlippageModel:

    def test_empty_stats(self):
        model = SlippageModel()
        stats = model.compute_stats()
        assert stats.n == 0
        assert stats.p50_bps == 0.0
        assert stats.regime == SlippageRegime.NORMAL

    def test_normal_regime_low_slippage(self):
        model = SlippageModel(window=50)
        for _ in range(20):
            model.record(Decimal("1.5"))
        stats = model.compute_stats()
        assert stats.regime == SlippageRegime.NORMAL
        assert abs(stats.p50_bps - 1.5) < 0.01

    def test_elevated_regime(self):
        model = SlippageModel(window=50)
        for _ in range(20):
            model.record(Decimal("5.0"))
        stats = model.compute_stats()
        assert stats.regime == SlippageRegime.ELEVATED

    def test_high_regime(self):
        model = SlippageModel(window=50)
        for _ in range(20):
            model.record(Decimal("10.0"))
        stats = model.compute_stats()
        assert stats.regime == SlippageRegime.HIGH

    def test_breach_raises(self):
        model = SlippageModel(window=10, alert_threshold_bps=5.0)
        # Fill window with high slippage
        with pytest.raises(SlippageBreachError):
            for _ in range(10):
                model.record(Decimal("20.0"))

    def test_window_rolls(self):
        model = SlippageModel(window=5)
        for _ in range(5):
            model.record(Decimal("1.0"))
        model.record(Decimal("2.0"))  # pushes out oldest
        assert model.observation_count == 5

    def test_p99_single_element(self):
        model = SlippageModel()
        model.record(Decimal("3.75"))
        stats = model.compute_stats()
        assert stats.p99_bps == pytest.approx(3.75, abs=0.01)

    def test_signed_slippage_negative(self):
        """Sells below bid should record positive cost (negative fill direction)."""
        model = SlippageModel()
        model.record(Decimal("-2.0"))  # sold below bid
        stats = model.compute_stats()
        assert stats.mean_bps == pytest.approx(-2.0, abs=0.01)


# ── OrderRecord financial math ────────────────────────────────────────────────

class TestOrderRecord:

    def _make_record(
        self,
        expected: str,
        fill: str,
        slippage: str,
        qty: int = 100,
    ) -> OrderRecord:
        return OrderRecord(
            symbol="AAPL",
            side="buy",
            qty=qty,
            expected_price=Decimal(expected),
            submitted_at=datetime.now(tz=timezone.utc),
            order_id="test-uuid-001",
            fill_price=Decimal(fill),
            filled_at=datetime.now(tz=timezone.utc),
            slippage_bps=Decimal(slippage),
            status="FILLED",
        )

    def test_net_slippage_cost_basic(self):
        """1 bps on $150 * 100 shares = $1.50."""
        record = self._make_record("150.00", "150.15", "1.00", qty=100)
        cost = record.net_slippage_cost
        assert cost == Decimal("1.50")

    def test_net_slippage_zero(self):
        record = self._make_record("150.00", "150.00", "0.00")
        assert record.net_slippage_cost == Decimal("0.00")

    def test_net_slippage_none_when_no_fill(self):
        record = OrderRecord(
            symbol="AAPL",
            side="buy",
            qty=10,
            expected_price=Decimal("150.00"),
            submitted_at=datetime.now(tz=timezone.utc),
            order_id="test-timeout",
            fill_price=None,
            filled_at=None,
            slippage_bps=None,
            status="TIMEOUT",
        )
        assert record.net_slippage_cost is None

    def test_decimal_precision_no_float_drift(self):
        """Ensure no floating point drift in slippage calculation."""
        expected = Decimal("155.21")
        fill = Decimal("155.23")
        slippage_bps = ((fill - expected) / expected * Decimal("10000")).quantize(
            Decimal("0.01")
        )
        # Should be exactly 1.29 bps, not 1.2884...002 from float arithmetic
        assert slippage_bps == Decimal("1.29")
