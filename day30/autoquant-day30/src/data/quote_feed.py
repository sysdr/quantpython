"""
QuoteFeed
---------
Fetches live bid/ask from Alpaca.  Applies a staleness guard: if the
quote timestamp is older than `max_age_ms` milliseconds, raises
QuoteStaleError so the caller can decide whether to abort.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest


def _quote_feed_from_env() -> DataFeed:
    """Default IEX — included with paper accounts; SIP needs a paid data subscription."""
    raw = os.environ.get("ALPACA_QUOTE_FEED", "iex").strip().lower()
    for f in DataFeed:
        if f.value == raw:
            return f
    return DataFeed.IEX


class QuoteStaleError(RuntimeError):
    pass


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid_price: Decimal
    ask_price: Decimal
    timestamp: datetime

    @property
    def mid_price(self) -> Decimal:
        return (self.bid_price + self.ask_price) / Decimal("2")

    @property
    def spread_bps(self) -> Decimal:
        return (self.ask_price - self.bid_price) / self.mid_price * Decimal("10000")


class QuoteFeed:
    """Thin wrapper around Alpaca's latest quote endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        max_age_ms: float | None = None,
        data_feed: DataFeed | None = None,
    ) -> None:
        self._client = StockHistoricalDataClient(
            api_key=api_key or os.environ["ALPACA_API_KEY"],
            secret_key=secret_key or os.environ["ALPACA_SECRET_KEY"],
        )
        default_age = float(os.environ.get("ALPACA_QUOTE_MAX_AGE_MS", "5000"))
        self._max_age_ms = default_age if max_age_ms is None else max_age_ms
        self._data_feed = data_feed if data_feed is not None else _quote_feed_from_env()

    def get_latest_quote(self, symbol: str) -> Quote:
        req = StockLatestQuoteRequest(
            symbol_or_symbols=symbol,
            feed=self._data_feed,
        )
        response = self._client.get_stock_latest_quote(req)
        raw = response[symbol]

        quote = Quote(
            symbol=symbol,
            bid_price=Decimal(str(raw.bid_price)),
            ask_price=Decimal(str(raw.ask_price)),
            timestamp=raw.timestamp,
        )

        now_utc = datetime.now(tz=timezone.utc)
        age_ms = (now_utc - quote.timestamp).total_seconds() * 1000
        if age_ms > self._max_age_ms:
            raise QuoteStaleError(
                f"{symbol} quote is {age_ms:.0f}ms old (limit={self._max_age_ms}ms)"
            )

        return quote
