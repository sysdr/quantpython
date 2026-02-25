"""
Alpaca data feed: fetches adjusted daily OHLCV, returns clean NumPy arrays.
Uses alpaca-py v2 REST client. No WebSocket for this lesson (Day 3 = daily bars).
"""
from __future__ import annotations

import time
import datetime
import numpy as np
import pandas as pd
from typing import Optional

from .config import ALPACA_CFG, build_logger

logger = build_logger("data_feed")

# Lazy import — don't crash if alpaca-py not installed during unit tests
try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    logger.warning("alpaca-py not installed — live feed disabled")


def fetch_adjusted_closes(
    symbol: str,
    lookback_years: int = 5,
    max_retries: int = 3,
) -> Optional[np.ndarray]:
    """
    Fetch adjusted daily close prices from Alpaca.

    Returns:
        float64 NumPy array of adjusted closes, chronological order.
        None if fetch fails after retries.

    Rate limit handling:
        Alpaca free tier: 200 req/min. We add 0.3s backoff between retries.
        For a 100-symbol universe, batch requests with a semaphore (see stress_test.py).
    """
    if not ALPACA_AVAILABLE:
        logger.error("alpaca-py not available")
        return None

    if not ALPACA_CFG.is_configured():
        logger.error("Alpaca credentials not set — check .env file")
        return None

    client = StockHistoricalDataClient(
        api_key=ALPACA_CFG.api_key,
        secret_key=ALPACA_CFG.secret_key,
    )

    end_dt = datetime.datetime.now(datetime.timezone.utc)
    start_dt = end_dt - datetime.timedelta(days=lookback_years * 366)

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame(1, TimeFrameUnit.Day),
        start=start_dt,
        end=end_dt,
        adjustment="all",   # split + dividend adjusted
    )

    for attempt in range(1, max_retries + 1):
        try:
            bars = client.get_stock_bars(request)
            df: pd.DataFrame = bars.df

            if df.empty:
                logger.warning("Empty response for %s", symbol)
                return None

            # alpaca-py returns MultiIndex (symbol, timestamp) — flatten
            if isinstance(df.index, pd.MultiIndex):
                df = df.xs(symbol, level="symbol")

            closes = df["close"].sort_index().to_numpy(dtype=np.float64)
            logger.info(
                "Fetched %d bars for %s (attempt %d)", len(closes), symbol, attempt
            )
            return closes

        except Exception as exc:
            logger.warning(
                "Fetch attempt %d/%d failed for %s: %s",
                attempt, max_retries, symbol, exc,
            )
            if attempt < max_retries:
                time.sleep(0.3 * attempt)

    logger.error("All %d fetch attempts failed for %s", max_retries, symbol)
    return None


def generate_synthetic_prices(
    n_days: int = 1260,
    initial_price: float = 100.0,
    annual_return: float = 0.12,
    annual_vol: float = 0.20,
    seed: int = 42,
) -> np.ndarray:
    """
    Geometric Brownian Motion price series for offline testing.
    μ=12%, σ=20% annualized by default (plausible US equity).
    """
    rng = np.random.default_rng(seed)
    dt = 1.0 / 252
    drift = (annual_return - 0.5 * annual_vol ** 2) * dt
    diffusion = annual_vol * np.sqrt(dt)

    log_rets = drift + diffusion * rng.standard_normal(n_days)
    prices = initial_price * np.exp(np.cumsum(log_rets))
    return np.insert(prices, 0, initial_price)  # prepend starting price
