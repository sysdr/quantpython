"""Unit tests for ATREngine and compute_atr_series."""

from __future__ import annotations

import math
import pytest
import numpy as np

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.atr_engine import ATREngine, OHLCTick, compute_atr_series


def make_ticks(n: int, base: float = 100.0, spread: float = 2.0) -> list[OHLCTick]:
    ticks = []
    close = base
    for i in range(n):
        high = close + spread
        low = close - spread
        ticks.append(OHLCTick(high=high, low=low, close=close))
        close += 0.1
    return ticks


class TestATREngineWarmup:
    def test_returns_none_before_period(self) -> None:
        engine = ATREngine(period=5)
        ticks = make_ticks(4)
        results = [engine.update(t) for t in ticks]
        assert all(r is None for r in results)

    def test_returns_float_after_period(self) -> None:
        engine = ATREngine(period=5)
        ticks = make_ticks(5)
        results = [engine.update(t) for t in ticks]
        assert results[-1] is not None
        assert isinstance(results[-1], float)
        assert results[-1] > 0

    def test_is_ready_flag(self) -> None:
        engine = ATREngine(period=3)
        assert not engine.is_ready
        for t in make_ticks(3):
            engine.update(t)
        assert engine.is_ready

class TestATREngineAccuracy:
    def test_constant_range_converges(self) -> None:
        """With constant H-L spread and no gap, ATR should equal spread."""
        engine = ATREngine(period=10)
        spread = 3.0
        ticks = [OHLCTick(high=100+spread, low=100-spread, close=100.0) for _ in range(50)]
        atr = None
        for t in ticks:
            atr = engine.update(t)
        # Wilder smoothing converges; allow 5% tolerance
        assert atr is not None
        assert abs(atr - 2*spread) / (2*spread) < 0.05

    def test_atr_increases_with_wider_range(self) -> None:
        engine_narrow = ATREngine(period=5)
        engine_wide = ATREngine(period=5)
        narrow = [OHLCTick(high=101.0, low=99.0, close=100.0) for _ in range(20)]
        wide = [OHLCTick(high=105.0, low=95.0, close=100.0) for _ in range(20)]
        atr_n, atr_w = None, None
        for t in narrow:
            atr_n = engine_narrow.update(t)
        for t in wide:
            atr_w = engine_wide.update(t)
        assert atr_n is not None and atr_w is not None
        assert atr_w > atr_n

    def test_reset_clears_state(self) -> None:
        engine = ATREngine(period=5)
        for t in make_ticks(10):
            engine.update(t)
        assert engine.is_ready
        engine.reset()
        assert not engine.is_ready
        assert engine.value is None

class TestATREnginePeriodValidation:
    def test_period_too_small_raises(self) -> None:
        with pytest.raises(ValueError):
            ATREngine(period=1)

class TestComputeATRSeries:
    def test_output_shape(self) -> None:
        n = 30
        h = np.linspace(102, 120, n)
        l = np.linspace(98, 110, n)
        c = np.linspace(100, 115, n)
        atr = compute_atr_series(h, l, c, period=14)
        assert atr.shape == (n,)

    def test_first_n_minus_1_are_nan(self) -> None:
        n = 30
        h = np.random.uniform(101, 110, n)
        l = np.random.uniform(90, 100, n)
        c = (h + l) / 2
        atr = compute_atr_series(h, l, c, period=14)
        assert np.all(np.isnan(atr[:13]))

    def test_values_after_warmup_are_positive(self) -> None:
        n = 30
        h = np.random.uniform(101, 110, n)
        l = np.random.uniform(90, 100, n)
        c = (h + l) / 2
        atr = compute_atr_series(h, l, c, period=14)
        assert np.all(atr[13:] > 0)

    def test_mismatched_lengths_raise(self) -> None:
        with pytest.raises(ValueError):
            compute_atr_series(np.ones(10), np.ones(9), np.ones(10))
