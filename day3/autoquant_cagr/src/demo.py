"""
Demo entry point.
Attempts live Alpaca fetch; falls back to GBM synthetic data if unconfigured.
Run: python -m src.demo
"""
from __future__ import annotations

import numpy as np
from rich.console import Console

from .config import ALPACA_CFG
from .cagr import build_cagr_surface
from .data_feed import fetch_adjusted_closes, generate_synthetic_prices
from .dashboard import run_live_dashboard

console = Console()

DEMO_SYMBOLS = ["SPY", "QQQ", "IWM", "GLD", "TLT"]


def main() -> None:
    surfaces = []

    for symbol in DEMO_SYMBOLS:
        prices: np.ndarray | None = None

        if ALPACA_CFG.is_configured():
            console.log(f"[cyan]Fetching live data:[/] {symbol}")
            prices = fetch_adjusted_closes(symbol, lookback_years=5)

        if prices is None:
            console.log(f"[yellow]Using synthetic GBM data for:[/] {symbol}")
            rng = hash(symbol) % 1000  # deterministic seed per symbol
            prices = generate_synthetic_prices(
                n_days=1260,
                annual_return=0.08 + (rng % 10) * 0.01,
                annual_vol=0.15 + (rng % 8) * 0.01,
                seed=rng,
            )

        surf = build_cagr_surface(symbol, prices)
        surfaces.append(surf)

    run_live_dashboard(surfaces, refresh_seconds=2.0, iterations=5)


if __name__ == "__main__":
    main()
