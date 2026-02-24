"""
Alpaca Bridge: Fetch ETF prices as fixed income proxies.
AGG (iShares Core U.S. Aggregate Bond) — broad investment grade
TLT (iShares 20+ Year Treasury) — long duration Treasury proxy
IEF (iShares 7-10 Year Treasury) — intermediate Treasury proxy

We use these to validate our YTM/duration calculations against live market data.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()


def get_alpaca_client():
    """Return Alpaca StockHistoricalDataClient if credentials available."""
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        api_key = os.getenv("ALPACA_API_KEY", "")
        secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        if not api_key or api_key == "your_paper_api_key_here":
            return None
        return StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
    except ImportError:
        return None


def fetch_etf_price(ticker: str) -> float | None:
    """Fetch latest price for a bond ETF from Alpaca. Returns None if unavailable."""
    client = get_alpaca_client()
    if client is None:
        return None

    try:
        from alpaca.data.requests import StockLatestQuoteRequest
        request = StockLatestQuoteRequest(symbol_or_symbols=ticker)
        quote = client.get_stock_latest_quote(request)
        if ticker in quote:
            q = quote[ticker]
            return float((q.ask_price + q.bid_price) / 2.0)
    except Exception as e:
        print(f"[alpaca_bridge] Could not fetch {ticker}: {e}")
    return None


def fetch_benchmark_prices() -> dict[str, float | None]:
    """Fetch all benchmark ETF prices for validation."""
    return {
        "AGG": fetch_etf_price("AGG"),
        "TLT": fetch_etf_price("TLT"),
        "IEF": fetch_etf_price("IEF"),
    }
