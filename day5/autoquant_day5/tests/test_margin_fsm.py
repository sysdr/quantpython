#!/usr/bin/env python3
"""
Unit tests for MarginFSM, HysteresisThreshold, and EquityCalculator.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from decimal import Decimal
import numpy as np
import pytest

from margin_monitor import (
    AlertLevel,
    HysteresisThreshold,
    MarginFSM,
    EquityCalculator,
)


class TestHysteresisThreshold:
    def test_valid_threshold(self):
        t = HysteresisThreshold(enter=0.80, exit=0.83)
        assert t.enter < t.exit

    def test_invalid_threshold_raises(self):
        with pytest.raises(AssertionError):
            HysteresisThreshold(enter=0.85, exit=0.80)


class TestMarginFSM:
    def test_initial_state_is_safe(self):
        fsm = MarginFSM()
        assert fsm.state == AlertLevel.SAFE

    def test_transition_to_warn(self):
        fsm = MarginFSM()
        result = fsm.update(0.88)  # below WARN enter threshold of 0.90
        assert result == AlertLevel.WARN
        assert fsm.state == AlertLevel.WARN

    def test_no_transition_above_warn(self):
        fsm = MarginFSM()
        result = fsm.update(0.95)
        assert result is None
        assert fsm.state == AlertLevel.SAFE

    def test_transition_to_critical(self):
        fsm = MarginFSM()
        fsm.update(0.88)  # → WARN
        result = fsm.update(0.78)  # → CRITICAL
        assert result == AlertLevel.CRITICAL

    def test_transition_to_margin_call(self):
        fsm = MarginFSM()
        fsm.update(0.88)
        fsm.update(0.78)
        result = fsm.update(0.68)
        assert result == AlertLevel.MARGIN_CALL

    def test_transition_to_liquidation(self):
        fsm = MarginFSM()
        fsm.update(0.88)
        fsm.update(0.78)
        fsm.update(0.68)
        result = fsm.update(0.55)
        assert result == AlertLevel.LIQUIDATION

    def test_hysteresis_prevents_recovery_too_early(self):
        """Recovering from WARN requires crossing exit=0.92, not just enter=0.90."""
        fsm = MarginFSM()
        fsm.update(0.88)               # → WARN (enter=0.90 crossed)
        result = fsm.update(0.91)      # above enter but below exit=0.92 → still WARN
        assert result is None
        assert fsm.state == AlertLevel.WARN

    def test_hysteresis_allows_recovery_at_exit(self):
        fsm = MarginFSM()
        fsm.update(0.88)               # → WARN
        result = fsm.update(0.93)      # above exit=0.92 → recover to SAFE
        assert result == AlertLevel.SAFE

    def test_no_duplicate_transition(self):
        fsm = MarginFSM()
        fsm.update(0.88)
        result = fsm.update(0.87)  # still in WARN, no new transition
        assert result is None


class TestEquityCalculator:
    def setup_method(self):
        self.calc = EquityCalculator()

    def test_unrealized_pnl_basic(self):
        qtys    = np.array([100.0, 50.0])
        entries = np.array([10.0,  20.0])
        prices  = np.array([12.0,  18.0])
        # 100*(12-10) + 50*(18-20) = 200 - 100 = 100
        pnl = self.calc.compute_unrealized_pnl(qtys, entries, prices)
        assert abs(pnl - 100.0) < 1e-9

    def test_unrealized_pnl_empty(self):
        pnl = self.calc.compute_unrealized_pnl(
            np.array([]), np.array([]), np.array([])
        )
        assert pnl == 0.0

    def test_equity_ratio_normal(self):
        ratio = self.calc.compute_equity_ratio(
            Decimal("85000"), Decimal("100000")
        )
        assert abs(ratio - 0.85) < 1e-4

    def test_equity_ratio_zero_last_equity(self):
        ratio = self.calc.compute_equity_ratio(
            Decimal("50000"), Decimal("0")
        )
        assert ratio == 1.0

    def test_equity_ratio_precision(self):
        """Verify Decimal arithmetic doesn't drift like float."""
        ratio = self.calc.compute_equity_ratio(
            Decimal("99990.00"), Decimal("100000.00")
        )
        assert ratio < 1.0
        assert ratio > 0.9990

    def test_vectorized_large_portfolio(self):
        """Stress: 10,000 positions should compute in < 10ms."""
        import time
        N = 10_000
        rng = np.random.default_rng(42)
        qtys    = rng.uniform(1, 1000, N)
        entries = rng.uniform(10, 500, N)
        prices  = entries * rng.uniform(0.9, 1.1, N)
        t0 = time.perf_counter()
        pnl = self.calc.compute_unrealized_pnl(qtys, entries, prices)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < 10.0, f"Took {elapsed_ms:.2f}ms, expected < 10ms"
        assert isinstance(pnl, float)
