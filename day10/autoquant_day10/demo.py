#!/usr/bin/env python3
"""
demo.py — Launch the Rich CLI return-engine dashboard.

If ALPACA credentials are not set, generates synthetic data for local demo.
"""

import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dashboard import render_dashboard
from data_validator import DataValidator
from return_engine import ReturnEngine

logging.basicConfig(level=logging.WARNING)


def generate_synthetic_data(
    n_symbols: int = 10, n_days: int = 252
) -> tuple[dict[str, pd.DataFrame], pd.DatetimeIndex]:
    """Generate synthetic OHLCV for offline demo/testing."""
    rng = np.random.default_rng(42)
    syms = [f"SYM{i:02d}" for i in range(n_symbols)]
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)

    ohlcv: dict[str, pd.DataFrame] = {}
    for sym in syms:
        log_returns = rng.normal(0.0003, 0.015, size=n_days)
        prices = 100.0 * np.exp(np.cumsum(log_returns))

        # Inject 5% NaN gaps (simulate halted sessions)
        nan_idx = rng.choice(n_days, size=int(n_days * 0.05), replace=False)
        prices[nan_idx] = np.nan

        ohlcv[sym] = pd.DataFrame({"close": prices}, index=dates)

    date_index = pd.DatetimeIndex(dates, name="date")
    return ohlcv, date_index


def main() -> None:
    has_creds = bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"))

    if has_creds:
        from alpaca_loader import build_common_date_index, load_bars
        from data_validator import DataValidator

        raw = load_bars(lookback_days=252)
        validator = DataValidator()
        clean, _ = validator.validate_universe(raw)
        date_index = build_common_date_index(clean)
        ohlcv = clean
    else:
        print("[demo] No Alpaca credentials found — using synthetic data.")
        ohlcv, date_index = generate_synthetic_data()

    engine = ReturnEngine()
    tensor = engine.compute(ohlcv, date_index)
    render_dashboard(tensor, refresh_interval=0)


if __name__ == "__main__":
    main()
