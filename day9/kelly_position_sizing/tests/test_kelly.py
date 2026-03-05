"""
tests/test_kelly.py

Unit tests for Kelly estimator and position sizer.
Run: pytest tests/test_kelly.py -v
"""
from __future__ import annotations

import numpy as np
import pytest

from src.kelly.estimator import KellyEstimator
from src.kelly.sizer import PositionSizer


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

@pytest.fixture()
def estimator() -> KellyEstimator:
    return KellyEstimator(n_bootstrap=1_000, spread_bps=5.0, seed=0)


@pytest.fixture()
def sizer() -> PositionSizer:
    return PositionSizer(kelly_fraction=0.5, max_position_fraction=0.15)


def _returns(n: int, win_rate: float, avg_win: float, avg_loss: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    wins = rng.choice([True, False], size=n, p=[win_rate, 1 - win_rate])
    vals = np.where(wins, rng.normal(avg_win, avg_win * 0.2, n), -rng.normal(avg_loss, avg_loss * 0.2, n))
    return vals


# -----------------------------------------------------------------------
# Estimator tests
# -----------------------------------------------------------------------

class TestKellyEstimator:

    def test_clear_edge_detected(self, estimator):
        """Strong win rate + good b-ratio → has_edge = True, positive Kelly."""
        r = _returns(200, win_rate=0.60, avg_win=0.020, avg_loss=0.010)
        est = estimator.estimate("TEST", r)
        assert est.has_edge
        assert est.boot_kelly_p5 > 0.0
        assert est.raw_win_rate > 0.50

    def test_no_edge_detected(self, estimator):
        """Win rate at 50%, tight b-ratio → after spread adjustment, no edge."""
        r = _returns(200, win_rate=0.50, avg_win=0.010, avg_loss=0.010)
        est = estimator.estimate("TEST", r)
        assert not est.has_edge

    def test_insufficient_data(self, estimator):
        """Fewer than 10 trades → immediate no-edge, no crash."""
        r = _returns(5, win_rate=0.80, avg_win=0.05, avg_loss=0.01)
        est = estimator.estimate("TEST", r)
        assert not est.has_edge
        assert est.n_trades == 5

    def test_bootstrap_p5_lte_mean(self, estimator):
        """p5 must be ≤ mean of bootstrap distribution."""
        r = _returns(150, win_rate=0.55, avg_win=0.018, avg_loss=0.012)
        est = estimator.estimate("TEST", r)
        assert est.boot_kelly_p5 <= est.boot_kelly_mean

    def test_kelly_clipped_non_negative(self, estimator):
        """Bootstrap Kelly output must never be negative (clipped to 0)."""
        r = _returns(200, win_rate=0.47, avg_win=0.008, avg_loss=0.010)
        est = estimator.estimate("TEST", r)
        assert est.boot_kelly_p5 >= 0.0

    def test_spread_reduces_b_ratio(self, estimator):
        """Spread-adjusted b_ratio must be less than raw b_ratio."""
        r = _returns(200, win_rate=0.55, avg_win=0.015, avg_loss=0.010)
        est = estimator.estimate("TEST", r)
        assert est.spread_adj_b_ratio < est.raw_b_ratio

    def test_all_wins_no_crash(self, estimator):
        """All-wins input (edge case): no division by zero."""
        r = np.abs(_returns(200, win_rate=0.99, avg_win=0.010, avg_loss=0.005))
        # No assertion on value, just must not raise
        est = estimator.estimate("TEST", r)
        assert est is not None

    def test_all_losses_no_edge(self, estimator):
        """All-losses input → has_edge = False."""
        r = -np.abs(_returns(200, win_rate=0.01, avg_win=0.005, avg_loss=0.010))
        est = estimator.estimate("TEST", r)
        assert not est.has_edge


# -----------------------------------------------------------------------
# Sizer tests
# -----------------------------------------------------------------------

class TestPositionSizer:

    def test_no_edge_returns_zero_shares(self, estimator, sizer):
        r = _returns(200, win_rate=0.50, avg_win=0.010, avg_loss=0.010)
        est = estimator.estimate("X", r)
        result = sizer.size(est, nav=100_000, price=100.0)
        assert result.shares == 0

    def test_shares_positive_for_clear_edge(self, estimator, sizer):
        r = _returns(200, win_rate=0.62, avg_win=0.022, avg_loss=0.010)
        est = estimator.estimate("X", r)
        result = sizer.size(est, nav=100_000, price=100.0)
        if est.has_edge:
            assert result.shares > 0

    def test_hard_cap_respected(self, estimator, sizer):
        """Nav fraction must never exceed max_position_fraction."""
        r = _returns(200, win_rate=0.70, avg_win=0.040, avg_loss=0.005)
        est = estimator.estimate("X", r)
        result = sizer.size(est, nav=100_000, price=10.0)
        assert result.nav_fraction <= sizer._max_frac + 1e-9

    def test_correlation_haircut_reduces_allocation(self, estimator):
        sizer_with = PositionSizer(kelly_fraction=0.5, correlation_haircut=True)
        sizer_without = PositionSizer(kelly_fraction=0.5, correlation_haircut=False)

        r = _returns(200, win_rate=0.58, avg_win=0.020, avg_loss=0.012, seed=1)
        portfolio_r = {"SPY": _returns(200, win_rate=0.55, avg_win=0.015, avg_loss=0.010, seed=2)}

        est = estimator.estimate("X", r)
        with_haircut = sizer_with.size(est, 100_000, 100.0, portfolio_r, r)
        without_haircut = sizer_without.size(est, 100_000, 100.0)

        if est.has_edge:
            assert with_haircut.shares <= without_haircut.shares

    def test_invalid_kelly_fraction_raises(self):
        with pytest.raises(ValueError):
            PositionSizer(kelly_fraction=0.0)

    def test_price_sensitivity(self, estimator, sizer):
        """Higher price → fewer shares (same dollar allocation)."""
        r = _returns(200, win_rate=0.60, avg_win=0.020, avg_loss=0.010)
        est = estimator.estimate("X", r)
        low_price = sizer.size(est, 100_000, price=50.0)
        high_price = sizer.size(est, 100_000, price=500.0)
        if est.has_edge:
            assert low_price.shares >= high_price.shares
