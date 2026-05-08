"""Unit tests for SlippageModel."""

from __future__ import annotations

import math
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.slippage_model import SlippageModel, OrderSide, SlippageEstimate


class TestSlippageModelEstimate:
    def test_buy_adjusts_price_up(self) -> None:
        model = SlippageModel(base_bps=5.0, atr_scalar=0.0)
        est = model.estimate("X", OrderSide.BUY, 100.0, 0.0)
        assert est.adjusted_price > 100.0

    def test_sell_adjusts_price_down(self) -> None:
        model = SlippageModel(base_bps=5.0, atr_scalar=0.0)
        est = model.estimate("X", OrderSide.SELL, 100.0, 0.0)
        assert est.adjusted_price < 100.0

    def test_zero_atr_equals_base_bps(self) -> None:
        model = SlippageModel(base_bps=3.0, atr_scalar=0.35)
        est = model.estimate("X", OrderSide.BUY, 100.0, 0.0)
        assert math.isclose(est.predicted_bps, 3.0, rel_tol=1e-6)

    def test_atr_increases_slippage(self) -> None:
        model = SlippageModel(base_bps=3.0, atr_scalar=0.35)
        est_low = model.estimate("X", OrderSide.BUY, 100.0, 0.5)
        est_high = model.estimate("X", OrderSide.BUY, 100.0, 5.0)
        assert est_high.predicted_bps > est_low.predicted_bps

    def test_max_bps_cap_respected(self) -> None:
        model = SlippageModel(base_bps=3.0, atr_scalar=10.0, max_bps=20.0)
        # Very high ATR relative to price
        est = model.estimate("X", OrderSide.BUY, 1.0, 100.0)
        assert est.predicted_bps <= 20.0

    def test_negative_mid_price_raises(self) -> None:
        model = SlippageModel()
        with pytest.raises(ValueError):
            model.estimate("X", OrderSide.BUY, -10.0, 1.0)

class TestSlippageModelReconciliation:
    def test_realized_slippage_buy_positive_when_fill_above_mid(self) -> None:
        model = SlippageModel()
        realized = model.realized_slippage_bps(100.0, 100.1, OrderSide.BUY)
        assert realized > 0

    def test_realized_slippage_sell_positive_when_fill_below_mid(self) -> None:
        model = SlippageModel()
        realized = model.realized_slippage_bps(100.0, 99.9, OrderSide.SELL)
        assert realized > 0

    def test_price_improvement_gives_negative_slippage(self) -> None:
        model = SlippageModel()
        realized = model.realized_slippage_bps(100.0, 99.9, OrderSide.BUY)
        assert realized < 0

    def test_model_error_sign(self) -> None:
        model = SlippageModel(base_bps=5.0, atr_scalar=0.0)
        est = model.estimate("X", OrderSide.BUY, 100.0, 0.0)
        # Fill exactly at mid (price improvement scenario)
        error = model.model_error_bps(est, 100.0)
        # predicted=5bps, realized=0bps → error=+5
        assert error > 0

class TestSlippageModelValidation:
    def test_negative_base_bps_raises(self) -> None:
        with pytest.raises(ValueError):
            SlippageModel(base_bps=-1.0)

    def test_max_bps_below_base_raises(self) -> None:
        with pytest.raises(ValueError):
            SlippageModel(base_bps=10.0, max_bps=5.0)
