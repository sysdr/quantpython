"""
Alpaca WebSocket bridge with exponential-backoff reconnection.

The reconnection pattern is not optional. In production:
- Market-open surges saturate Alpaca's IEX feed → stream drops.
- Cloud VM network interfaces have occasional flaps.
- A naive implementation that raises on disconnect loses the session.

This bridge implements:
1. Automatic reconnection up to MAX_RECONNECT_ATTEMPTS.
2. Exponential backoff with jitter to avoid thundering herd.
3. strategy.reset() call on each reconnect to flush stale indicators.
"""
from __future__ import annotations
import asyncio
import logging
import random
from typing import Callable, Optional

from ..core.types import MarketSnapshot
from ..core.interface import OnTickInterface

logger = logging.getLogger(__name__)


class AlpacaDataBridge:
    MAX_RECONNECT_ATTEMPTS = 10
    BASE_BACKOFF_S         = 1.0

    def __init__(
        self,
        api_key:    str,
        api_secret: str,
        symbols:    list[str],
        strategy:   OnTickInterface,
        on_signal:  Callable,
        feed:       str = "iex",
    ) -> None:
        self._api_key   = api_key
        self._api_secret = api_secret
        self._symbols   = symbols
        self._strategy  = strategy
        self._on_signal = on_signal
        self._feed      = feed
        self._stream: Optional[object] = None
        self._reconnect_count: int = 0

    async def start(self) -> None:
        """
        Start streaming with reconnection loop.

        On each reconnect, strategy.reset() is called to prevent
        stale EMA values from the previous session contaminating
        the fresh price buffer.
        """
        from alpaca.data.live import StockDataStream
        from alpaca.data.models import Quote

        async def handle_quote(quote: Quote) -> None:
            snapshot = MarketSnapshot(
                symbol       = quote.symbol,
                bid          = float(quote.bid_price or 0.0),
                ask          = float(quote.ask_price or 0.0),
                last         = float(quote.ask_price or 0.0),
                volume       = int(quote.bid_size or 0),
                timestamp_ns = int(quote.timestamp.timestamp() * 1e9),
            )
            signal = self._strategy.on_tick(snapshot)
            if signal is not None:
                await self._on_signal(signal)

        while self._reconnect_count < self.MAX_RECONNECT_ATTEMPTS:
            try:
                logger.info(
                    "[Bridge] Connecting feed=%s symbols=%s (attempt %d)",
                    self._feed, self._symbols, self._reconnect_count + 1,
                )
                self._strategy.reset()
                self._stream = StockDataStream(
                    self._api_key, self._api_secret, feed=self._feed
                )
                self._stream.subscribe_quotes(handle_quote, *self._symbols)
                self._reconnect_count = 0   # Reset counter on clean connect
                await self._stream._run_forever()

            except Exception as exc:
                self._reconnect_count += 1
                # Exponential backoff with ±20% jitter
                backoff = self.BASE_BACKOFF_S * (2 ** self._reconnect_count)
                jitter  = backoff * random.uniform(-0.2, 0.2)
                wait    = max(0.5, backoff + jitter)
                logger.warning(
                    "[Bridge] Stream error: %s. Retry in %.1fs (%d/%d)",
                    exc, wait, self._reconnect_count, self.MAX_RECONNECT_ATTEMPTS,
                )
                await asyncio.sleep(wait)

        raise RuntimeError(
            f"[Bridge] Exhausted {self.MAX_RECONNECT_ATTEMPTS} reconnection attempts."
        )

    async def stop(self) -> None:
        if self._stream:
            try:
                await self._stream.stop()
            except Exception:
                pass
