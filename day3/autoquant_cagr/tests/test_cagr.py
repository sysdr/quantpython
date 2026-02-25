"""
Unit tests for the CAGR engine.
Financial math must be exact to 4 decimal places.
"""
from __future__ import annotations

import numpy as np
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cagr import (
    compute_log_returns,
    cagr_from_log_returns,
    build_cagr_surface,
    CAGRSurface,
)
from src.data_feed import generate_synthetic_prices
from src.config import TRADING_DAYS_PER_YEAR


class TestLogReturns:

    def test_basic_computation(self):
        """Simple doubling: ln(200/100) = ln(2)"""
        prices = np.array([100.0, 200.0], dtype=np.float64)
        series = compute_log_returns(prices)
        assert len(series.values) == 1
        assert np.isclose(series.values[0], np.log(2.0))

    def test_zero_price_zero_fills(self):
        """Zero price → log(0) = -inf → must be zero-filled, not propagated."""
        prices = np.array([100.0, 0.0, 100.0], dtype=np.float64)
        series = compute_log_returns(prices)
        assert series.nan_count == 2   # 0/100 and 100/0
        assert np.all(np.isfinite(series.values))
        assert series.values[0] == 0.0  # log(0) → zero-filled
        assert series.values[1] == 0.0  # log(inf) → zero-filled

    def test_empty_prices(self):
        prices = np.array([100.0], dtype=np.float64)
        series = compute_log_returns(prices)
        assert len(series.values) == 0

    def test_nan_ratio_is_zero_for_clean_data(self):
        prices = generate_synthetic_prices(n_days=252)
        series = compute_log_returns(prices)
        assert series.nan_count == 0


class TestCAGR:

    def test_exact_doubling_1y(self):
        """
        Price doubles over exactly 252 trading days → CAGR must equal 100%.
        Construct prices backward from the formula.
        """
        # 252 equal daily log returns that sum to ln(2)
        total_log_return = np.log(2.0)
        per_day = total_log_return / 252
        log_rets = np.full(252, per_day)
        result = cagr_from_log_returns(log_rets, window=252)
        assert np.isclose(result, 1.0, atol=1e-10), f"Expected 100%, got {result:.6%}"

    def test_flat_prices_zero_cagr(self):
        """Constant price series → zero log returns → 0% CAGR."""
        log_rets = np.zeros(252)
        assert cagr_from_log_returns(log_rets, window=252) == pytest.approx(0.0, abs=1e-12)

    def test_insufficient_data_returns_nan(self):
        log_rets = np.zeros(10)
        result = cagr_from_log_returns(log_rets, window=252)
        assert np.isnan(result)

    def test_252_vs_365_convention_divergence(self):
        """
        Demonstrate why 252 ≠ 365 matters.
        Same log return series → different annualization → different CAGR.
        """
        log_rets = np.full(252, 0.001)  # 0.1% per day
        cagr_252 = float(np.exp(log_rets.sum() / (252 / 252)) - 1)
        cagr_365 = float(np.exp(log_rets.sum() / (252 / 365)) - 1)
        # 252-day convention is LOWER (fewer assumed non-trading days)
        assert cagr_365 > cagr_252, "365-day convention should yield higher annualized return"

    def test_geometric_less_than_arithmetic(self):
        """Jensen's inequality: arithmetic mean ≥ geometric mean."""
        rng = np.random.default_rng(0)
        log_rets = rng.normal(0.0005, 0.01, 252)
        geometric_cagr = cagr_from_log_returns(log_rets, window=252)
        # Arithmetic mean of simple returns (not log returns)
        simple_rets = np.exp(log_rets) - 1
        arithmetic_mean_return = simple_rets.mean()
        arithmetic_cagr = arithmetic_mean_return * 252
        # Geometric should be slightly lower due to volatility drag
        assert geometric_cagr <= arithmetic_cagr + 1e-9


class TestCAGRSurface:

    def test_surface_has_all_tenors(self):
        prices = generate_synthetic_prices(n_days=1512)
        surf = build_cagr_surface("TEST", prices)
        from src.config import TENORS
        for tenor in TENORS:
            assert tenor in surf.cagr_by_tenor

    def test_short_tenors_nan_for_short_series(self):
        """Only 10 bars → all tenors except 1W should be NaN."""
        prices = generate_synthetic_prices(n_days=10)
        surf = build_cagr_surface("SHORT", prices)
        assert not np.isnan(surf.cagr_by_tenor.get("1W", float("nan")))
        assert np.isnan(surf.cagr_by_tenor.get("1M", float("nan")))

    def test_nan_ratio_tracked(self):
        prices = generate_synthetic_prices(n_days=252)
        surf = build_cagr_surface("CLEAN", prices)
        assert surf.nan_ratio == 0.0


class TestInversionDetection:

    def _make_inverted_surface(self) -> CAGRSurface:
        """Synthetic surface where 1W >> 5Y → clear inversion."""
        return CAGRSurface(
            symbol="INV",
            cagr_by_tenor={
                "1W": 0.80,   # +80% annualized — extreme short-term spike
                "1M": 0.50,
                "3M": 0.30,
                "6M": 0.20,
                "1Y": 0.15,
                "2Y": 0.12,
                "3Y": 0.10,
                "5Y": 0.08,   # normal long-term
            },
            nan_ratio=0.0,
        )

    def test_detects_inversion(self):
        surf = self._make_inverted_surface()
        inversions = surf.detect_inversions(threshold_bps=500)
        assert len(inversions) > 0, "Should detect inversions in extreme surface"

    def test_inversion_spread_correct(self):
        surf = self._make_inverted_surface()
        inversions = surf.detect_inversions(threshold_bps=500)
        # 1W vs 5Y: (0.80 - 0.08) * 10000 = 7200 bps
        spreads = [inv[2] for inv in inversions if inv[0] == "1W" and inv[1] == "5Y"]
        assert spreads, "1W vs 5Y inversion must be in results"
        assert np.isclose(spreads[0], 7200.0, atol=0.1)

    def test_no_false_positives_normal_curve(self):
        """Normal upward-sloping curve → no inversions."""
        surf = CAGRSurface(
            symbol="NORM",
            cagr_by_tenor={
                "1W": 0.05, "1M": 0.08, "3M": 0.10,
                "6M": 0.12, "1Y": 0.14, "2Y": 0.15,
                "3Y": 0.16, "5Y": 0.17,
            },
            nan_ratio=0.0,
        )
        assert surf.detect_inversions(threshold_bps=500) == []
