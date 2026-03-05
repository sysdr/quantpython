"""
broker/alpaca_client.py

Thin async wrapper around alpaca-py TradingClient.
Handles 429 rate limiting with exponential backoff + jitter.
Uses paper-trading endpoint by default.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.common.exceptions import APIError


@dataclass(slots=True)
class OrderResult:
    order_id: str
    symbol: str
    qty: int
    side: str
    submitted_at: str
    fill_price: Optional[float]
    status: str
    latency_ms: float


class AlpacaBroker:
    """
    Async-friendly Alpaca paper-trading client.

    Note: alpaca-py TradingClient is synchronous internally.
    We run blocking calls in an executor to avoid event-loop stalls.
    """

    MAX_RETRIES = 3
    BASE_BACKOFF = 1.0   # seconds

    def __init__(self, api_key: str, secret_key: str, paper: bool = True) -> None:
        self._client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper,
        )

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    async def get_nav(self) -> float:
        """Return current portfolio equity (NAV) in USD."""
        acct = await asyncio.get_event_loop().run_in_executor(
            None, self._client.get_account
        )
        return float(acct.equity)

    async def get_open_positions(self) -> dict[str, float]:
        """Return {symbol: market_value_fraction_of_equity}."""
        loop = asyncio.get_event_loop()
        acct = await loop.run_in_executor(None, self._client.get_account)
        equity = float(acct.equity)
        positions = await loop.run_in_executor(None, self._client.get_all_positions)
        return {
            p.symbol: float(p.market_value) / equity
            for p in positions
        }

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def market_buy(self, symbol: str, qty: int) -> OrderResult:
        return await self._submit_with_retry(symbol, qty, OrderSide.BUY)

    async def market_sell(self, symbol: str, qty: int) -> OrderResult:
        return await self._submit_with_retry(symbol, qty, OrderSide.SELL)

    async def _submit_with_retry(
        self, symbol: str, qty: int, side: OrderSide
    ) -> OrderResult:
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        )

        loop = asyncio.get_event_loop()
        last_exc: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            t0 = time.perf_counter()
            try:
                order = await loop.run_in_executor(
                    None, self._client.submit_order, request
                )
                latency_ms = (time.perf_counter() - t0) * 1000
                return OrderResult(
                    order_id=str(order.id),
                    symbol=symbol,
                    qty=qty,
                    side=side.value,
                    submitted_at=str(order.submitted_at),
                    fill_price=float(order.filled_avg_price) if order.filled_avg_price else None,
                    status=str(order.status),
                    latency_ms=latency_ms,
                )
            except APIError as e:
                last_exc = e
                if getattr(e, "status_code", None) == 429:
                    wait = (self.BASE_BACKOFF * (2 ** attempt)) + random.uniform(0, 0.5)
                    await asyncio.sleep(wait)
                else:
                    raise   # Non-retryable API errors propagate immediately

        raise RuntimeError(f"Order failed after {self.MAX_RETRIES} retries") from last_exc

    async def get_latest_quote(self, symbol: str) -> tuple[float, float]:
        """Return (bid, ask) for symbol."""
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestQuoteRequest
        # Re-use credentials from trading client internals
        data_client = StockHistoricalDataClient(
            self._client._api_key, self._client._secret_key
        )
        loop = asyncio.get_event_loop()
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quote_resp = await loop.run_in_executor(None, data_client.get_stock_latest_quote, req)
        quote = quote_resp[symbol]
        return float(quote.bid_price), float(quote.ask_price)
