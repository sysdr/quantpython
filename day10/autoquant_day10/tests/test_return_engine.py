"""
Unit tests for ReturnEngine.
All tests use deterministic synthetic data — no network calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from return_engine import ReturnEngine, ReturnTensor


# ── fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def simple_universe() -> tuple[dict[str, pd.DataFrame], pd.DatetimeIndex]:
    """3 symbols, 10 trading days, known price series."""
    dates = pd.bdate_range("2024-01-01", periods=10)
    ohlcv = {
        "AAPL": pd.DataFrame({"close": [150.0, 152.0, 151.0, 153.0, 155.0,
                                          154.0, 156.0, 158.0, 157.0, 160.0]}, index=dates),
        "MSFT": pd.DataFrame({"close": [300.0, 303.0, 301.0, 305.0, 308.0,
                                          306.0, 310.0, 312.0, 311.0, 315.0]}, index=dates),
        "GOOG": pd.DataFrame({"close": [140.0, 141.0, 142.0, 141.5, 143.0,
                                          144.0, 143.5, 145.0, 146.0, 147.0]}, index=dates),
    }
    return ohlcv, pd.DatetimeIndex(dates)


@pytest.fixture
def universe_with_gaps(
    simple_universe,
) -> tuple[dict[str, pd.DataFrame], pd.DatetimeIndex]:
    ohlcv, dates = simple_universe
    # Inject NaN at days 3 and 4 for AAPL
    ohlcv["AAPL"].iloc[3, 0] = np.nan
    ohlcv["AAPL"].iloc[4, 0] = np.nan
    return ohlcv, dates


# ── tests ────────────────────────────────────────────────────────────────

def test_log_return_accuracy(simple_universe):
    """
    Log-return computed by engine must match manual np.log(p2/p1)
    within machine epsilon (1e-12).
    """
    ohlcv, dates = simple_universe
    engine = ReturnEngine()
    tensor = engine.compute(ohlcv, dates)

    aapl_idx = tensor.symbols.index("AAPL")
    aapl_closes = ohlcv["AAPL"]["close"].values

    for t in range(len(dates) - 1):
        expected = np.log(aapl_closes[t + 1] / aapl_closes[t])
        actual = tensor.log_returns[aapl_idx, t]
        assert abs(actual - expected) < 1e-12, (
            f"Day {t}: expected {expected}, got {actual}, diff={abs(actual-expected)}"
        )


def test_nan_propagation_guard(universe_with_gaps):
    """
    NaN in price at day t must invalidate returns at days t AND t-1.
    No silent zero-fill allowed.
    """
    ohlcv, dates = universe_with_gaps
    engine = ReturnEngine()
    tensor = engine.compute(ohlcv, dates)

    aapl_idx = tensor.symbols.index("AAPL")

    # Prices NaN at days 3 and 4 → returns NaN at days 2,3,4
    for ret_day in (2, 3, 4):
        assert not tensor.validity_mask[aapl_idx, ret_day], (
            f"Return at day {ret_day} should be invalid due to NaN in price"
        )
        assert np.isnan(tensor.log_returns[aapl_idx, ret_day]), (
            f"Return value at day {ret_day} should be NaN, not zero"
        )

    # Other symbols should be unaffected
    msft_idx = tensor.symbols.index("MSFT")
    assert tensor.validity_mask[msft_idx, :].all(), "MSFT should have no invalid returns"


def test_corporate_action_detection(simple_universe):
    """
    Inject a synthetic split: price drops 50% overnight.
    Engine must flag it as a CA without crashing.
    """
    ohlcv, dates = simple_universe
    # Simulate a 2:1 reverse split on GOOG day 5→6
    ohlcv["GOOG"].iloc[5, 0] = ohlcv["GOOG"].iloc[4, 0] * 2.0   # +100% → flagged

    engine = ReturnEngine(split_threshold=0.40)
    tensor = engine.compute(ohlcv, dates)

    goog_flags = [f for f in tensor.ca_flags if f.symbol == "GOOG"]
    assert len(goog_flags) >= 1, "Should have flagged the GOOG CA"
    assert goog_flags[0].return_pct > 40.0, "Should be >40% return"


def test_vectorised_vs_loop_parity(simple_universe):
    """
    Vectorised engine and naive loop must agree within floating-point tolerance.
    """
    ohlcv, dates = simple_universe
    engine = ReturnEngine()
    tensor = engine.compute(ohlcv, dates)

    for i, sym in enumerate(tensor.symbols):
        closes = ohlcv[sym]["close"].values.astype(np.float64)
        naive = np.log(closes[1:]) - np.log(closes[:-1])

        for t in range(len(naive)):
            if tensor.validity_mask[i, t]:
                diff = abs(tensor.log_returns[i, t] - naive[t])
                assert diff < 1e-10, f"{sym} day {t}: engine={tensor.log_returns[i,t]}, naive={naive[t]}"


def test_arithmetic_conversion(simple_universe):
    """
    arithmetic_returns property must equal expm1(log_returns),
    not exp(log_returns) - 1 for large values.
    Uses expm1 precision guarantee for small returns.
    """
    ohlcv, dates = simple_universe
    engine = ReturnEngine()
    tensor = engine.compute(ohlcv, dates)

    arith = tensor.arithmetic_returns
    expected = np.expm1(tensor.log_returns)
    valid = tensor.validity_mask

    max_diff = np.nanmax(np.abs(arith[valid] - expected[valid]))
    assert max_diff < 1e-15, f"arithmetic_returns precision error: {max_diff}"
