"""
stress_test.py
──────────────
Performance and memory benchmarks for the ReturnEngine.
These tests validate that the implementation scales to production universe sizes.
"""

from __future__ import annotations

import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from return_engine import ReturnEngine


def make_large_universe(
    n_symbols: int = 500, n_days: int = 252
) -> tuple[dict[str, pd.DataFrame], pd.DatetimeIndex]:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range(end="2024-12-31", periods=n_days)
    ohlcv: dict[str, pd.DataFrame] = {}

    for i in range(n_symbols):
        sym = f"SYM{i:04d}"
        log_rets = rng.normal(0.0, 0.015, size=n_days)
        prices = 50.0 * np.exp(np.cumsum(log_rets))
        # 2% NaN rate per symbol
        nan_idx = rng.choice(n_days, size=max(1, int(n_days * 0.02)), replace=False)
        prices[nan_idx] = np.nan
        ohlcv[sym] = pd.DataFrame({"close": prices}, index=dates)

    return ohlcv, pd.DatetimeIndex(dates)


def test_500_symbols_timing():
    """
    ReturnEngine.compute() for 500 symbols × 252 days must complete in < 200ms.
    Production target: < 50ms. Test budget: 200ms to allow for CI overhead.
    """
    ohlcv, dates = make_large_universe(n_symbols=500, n_days=252)
    engine = ReturnEngine()

    # Warm-up (JIT / import effects)
    engine.compute({k: v for k, v in list(ohlcv.items())[:5]}, dates)

    start = time.perf_counter()
    tensor = engine.compute(ohlcv, dates)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert tensor.log_returns.shape == (500, 251), "Shape mismatch"
    assert elapsed_ms < 200, (
        f"compute() took {elapsed_ms:.1f}ms — exceeds 200ms budget. "
        f"Check for hidden Python loops."
    )
    print(f"\n  [timing] 500 symbols × 252 days: {elapsed_ms:.1f}ms")


def test_memory_footprint():
    """
    ReturnEngine.compute() for 500 symbols × 252 days must not
    allocate more than 100MB of peak heap memory.

    float64: 500 × 252 × 8 bytes = ~1MB for the matrix itself.
    Overhead (pandas reindex, temp arrays) should stay under 100MB.
    """
    ohlcv, dates = make_large_universe(n_symbols=500, n_days=252)
    engine = ReturnEngine()

    tracemalloc.start()
    tensor = engine.compute(ohlcv, dates)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak_bytes / (1024 ** 2)
    assert peak_mb < 100, (
        f"Peak memory {peak_mb:.1f}MB exceeds 100MB budget. "
        f"Check for unnecessary DataFrame copies."
    )
    print(f"\n  [memory] Peak allocation: {peak_mb:.2f}MB")
