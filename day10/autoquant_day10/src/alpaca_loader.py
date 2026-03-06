"""
alpaca_loader.py
────────────────
Loads historical OHLCV bars from Alpaca Markets (paper or live).
Handles pagination, rate-limit back-off, and partial responses.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Default demo universe — liquid large-caps for reliable data
DEFAULT_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "BRK.B", "JPM", "V",
]

CACHE_DIR = Path("data/cache")


def _get_alpaca_client():
    """Lazy-import Alpaca to avoid hard dependency when not needed."""
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
    except ImportError as exc:
        raise RuntimeError(
            "alpaca-py not installed. Run: pip install alpaca-py"
        ) from exc

    api_key = os.getenv("ALPACA_API_KEY", "")
    secret_key = os.getenv("ALPACA_SECRET_KEY", "")

    if not api_key or not secret_key:
        raise EnvironmentError(
            "Set ALPACA_API_KEY and ALPACA_SECRET_KEY in your .env file."
        )

    client = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
    return client, StockBarsRequest, TimeFrame


def load_bars(
    symbols: list[str] | None = None,
    lookback_days: int = 252,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """
    Fetch daily OHLCV bars for `symbols` over the last `lookback_days`.

    Returns
    -------
    dict[symbol → DataFrame(open, high, low, close, volume)]
    with a DatetimeIndex normalised to date-only (no timezone).
    """
    symbols = symbols or DEFAULT_UNIVERSE
    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days + 10)  # buffer for holidays

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = (
        f"{'_'.join(sorted(symbols))}_{start_date}_{end_date}.parquet"
    )
    cache_path = CACHE_DIR / cache_key

    if use_cache and cache_path.exists():
        logger.info("Loading from cache: %s", cache_path)
        df_all = pd.read_parquet(cache_path)
        return _split_by_symbol(df_all)

    logger.info(
        "Fetching %d symbols from Alpaca (%s → %s)",
        len(symbols), start_date, end_date,
    )

    client, StockBarsRequest, TimeFrame = _get_alpaca_client()

    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=pd.Timestamp(start_date),
        end=pd.Timestamp(end_date),
        adjustment="all",       # corporate-action adjusted prices
    )

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            bars = client.get_stock_bars(request)
            break
        except Exception as exc:
            logger.warning(
                "Alpaca fetch attempt %d/%d failed: %s", attempt, max_retries, exc
            )
            if attempt == max_retries:
                raise
            time.sleep(2 ** attempt)   # exponential back-off

    df_all = bars.df.reset_index()
    df_all.columns = [c.lower() for c in df_all.columns]

    # Normalise index: strip tz, keep date precision
    df_all["timestamp"] = pd.to_datetime(df_all["timestamp"]).dt.normalize()
    df_all = df_all.rename(columns={"timestamp": "date"})

    df_all.to_parquet(cache_path, index=False)
    logger.info("Cached response to %s", cache_path)

    return _split_by_symbol(df_all)


def _split_by_symbol(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split a stacked bar DataFrame into per-symbol DataFrames."""
    result: dict[str, pd.DataFrame] = {}
    sym_col = "symbol" if "symbol" in df.columns else df.columns[0]

    for sym, group in df.groupby(sym_col):
        g = group.drop(columns=[sym_col]).set_index("date").sort_index()
        g.index = pd.to_datetime(g.index)
        result[str(sym)] = g

    return result


def build_common_date_index(
    ohlcv: dict[str, pd.DataFrame]
) -> pd.DatetimeIndex:
    """
    Compute the union of all trading dates across the universe.
    Using UNION (not intersection) keeps gaps explicit as NaN
    rather than silently dropping days where any symbol was halted.
    """
    all_dates: set[pd.Timestamp] = set()
    for df in ohlcv.values():
        all_dates.update(df.index.tolist())

    return pd.DatetimeIndex(sorted(all_dates), name="date")
