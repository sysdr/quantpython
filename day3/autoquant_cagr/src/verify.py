"""
Verification script — confirms the module is production-ready.
Usage: python -m src.verify --symbol SPY --tenor 1Y
"""
from __future__ import annotations

import sys
import time
import argparse
import numpy as np

from .cagr import build_cagr_surface
from .data_feed import fetch_adjusted_closes, generate_synthetic_prices
from .config import ALPACA_CFG, TENORS

PASS = "[PASS]"
FAIL = "[FAIL]"


def verify(symbol: str, tenor: str) -> bool:
    if tenor not in TENORS:
        print(f"{FAIL} Unknown tenor '{tenor}'. Valid: {list(TENORS)}")
        return False

    # Fetch or synthetic
    prices = None
    if ALPACA_CFG.is_configured():
        prices = fetch_adjusted_closes(symbol, lookback_years=6)
    if prices is None:
        print(f"  Using synthetic prices for {symbol}")
        prices = generate_synthetic_prices(n_days=1512)

    start_ns = time.perf_counter_ns()
    surface = build_cagr_surface(symbol, prices)
    elapsed_ms = (time.perf_counter_ns() - start_ns) / 1e6

    value = surface.cagr_by_tenor.get(tenor, float("nan"))

    latency_ok = elapsed_ms < 5.0
    nan_ok = surface.nan_ratio < 0.001
    value_ok = np.isfinite(value)

    status = PASS if (latency_ok and nan_ok and value_ok) else FAIL
    cagr_str = f"{value * 100:+.2f}%" if np.isfinite(value) else "N/A"

    print(
        f"{status} {symbol} {tenor} CAGR: {cagr_str} | "
        f"Computation: {elapsed_ms:.2f}ms | "
        f"NaN ratio: {surface.nan_ratio * 100:.3f}%"
    )

    if not latency_ok:
        print(f"  ⚠ Latency {elapsed_ms:.2f}ms exceeds 5ms threshold")
    if not nan_ok:
        print(f"  ⚠ NaN ratio {surface.nan_ratio:.4f} exceeds 0.1% threshold")

    return latency_ok and nan_ok and value_ok


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoQuant-Alpha CAGR Verifier")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--tenor", default="1Y")
    args = parser.parse_args()
    ok = verify(args.symbol, args.tenor)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
