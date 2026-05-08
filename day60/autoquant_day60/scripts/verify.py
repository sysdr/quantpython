#!/usr/bin/env python3.11
"""Verify the workspace: check imports, run basic sanity checks."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def check(name: str, passed: bool) -> None:
    status = "[PASS]" if passed else "[FAIL]"
    color = "\033[92m" if passed else "\033[91m"
    reset = "\033[0m"
    print(f"{color}{status}{reset} {name}")
    if not passed:
        sys.exit(1)


def main() -> None:
    print("\nAutoQuant-Alpha Day 60 — Workspace Verification\n")

    # Import checks
    try:
        from src.atr_engine import ATREngine, OHLCTick, compute_atr_series
        check("src.atr_engine imports", True)
    except ImportError as e:
        check(f"src.atr_engine imports: {e}", False)

    try:
        from src.slippage_model import SlippageModel, OrderSide
        check("src.slippage_model imports", True)
    except ImportError as e:
        check(f"src.slippage_model imports: {e}", False)

    try:
        from src.order_logger import OrderLogger, OrderRecord
        check("src.order_logger imports", True)
    except ImportError as e:
        check(f"src.order_logger imports: {e}", False)

    # ATR warmup
    import numpy as np
    from src.atr_engine import ATREngine, OHLCTick

    engine = ATREngine(period=5)
    ticks = [OHLCTick(high=100+i, low=99+i, close=99.5+i) for i in range(10)]
    atr = None
    for t in ticks:
        atr = engine.update(t)
    check("ATR engine warm-start (period=5, 10 ticks)", atr is not None)

    # Slippage model
    from src.slippage_model import SlippageModel, OrderSide
    model = SlippageModel(base_bps=3.0, atr_scalar=0.35)
    est = model.estimate("AAPL", OrderSide.BUY, mid_price=150.0, atr=2.5)
    check("SlippageModel estimate computed", est.predicted_bps > 3.0)
    check("SlippageModel BUY adjusts price upward", est.adjusted_price > 150.0)

    # Vectorized ATR series
    highs = np.linspace(102, 115, 30)
    lows = np.linspace(98, 110, 30)
    closes = np.linspace(100, 112, 30)
    from src.atr_engine import compute_atr_series
    atr_series = compute_atr_series(highs, lows, closes, period=14)
    check("compute_atr_series returns correct shape", len(atr_series) == 30)
    check("compute_atr_series first 13 are NaN", np.all(np.isnan(atr_series[:13])))
    check("compute_atr_series last value is finite", np.isfinite(atr_series[-1]))

    print("\n\033[92mAll checks passed.\033[0m")


if __name__ == "__main__":
    main()
