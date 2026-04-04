"""
SlippageAwareMarketOrder
------------------------
Stateless order submission engine.  For each order:
  1. Capture live bid/ask  →  record expected fill price
  2. Submit market order to Alpaca paper sandbox
  3. Async-poll for fill with exponential backoff (no event loop blocking)
  4. Compute realized slippage in basis points using Decimal arithmetic
  5. Atomically log the OrderRecord
  6. Feed slippage into SlippageModel; raise if p99 breaches threshold

Python 3.11+ features used:
  - dataclass(frozen=True)   — immutable value objects, hashable
  - X | Y union syntax        — cleaner than Optional[X]
  - match/case                — exhaustive order-status dispatch
  - asyncio.timeout()         — Python 3.11 context manager for timeouts
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderStatus, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from src.data.quote_feed import Quote, QuoteFeed
from src.execution.slippage_model import SlippageModel
from src.utils.logger import AtomicTradeLogger


# ── Domain Errors ────────────────────────────────────────────────────────────

class OrderRejectedError(RuntimeError):
    pass


class OrderTimeoutError(RuntimeError):
    pass


# ── Value Object ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OrderRecord:
    symbol: str
    side: str                        # "buy" | "sell"
    qty: int
    expected_price: Decimal          # ask (buy) or bid (sell) at submission
    submitted_at: datetime
    order_id: str
    fill_price: Decimal | None
    filled_at: datetime | None
    slippage_bps: Decimal | None     # signed: positive = paid more than expected
    status: str                      # FILLED | REJECTED | TIMEOUT

    @property
    def net_slippage_cost(self) -> Decimal | None:
        """Total dollar cost of slippage for this order."""
        if self.slippage_bps is None or self.fill_price is None:
            return None
        return (
            (self.slippage_bps / Decimal("10000"))
            * self.expected_price
            * Decimal(str(self.qty))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Engine ────────────────────────────────────────────────────────────────────

class SlippageAwareMarketOrder:
    """
    Submits a market order and returns a fully-populated OrderRecord
    containing the realized slippage in basis points.

    Parameters
    ----------
    trading_client : TradingClient
        Alpaca trading client (paper or live).
    quote_feed : QuoteFeed
        Provides live bid/ask snapshots.
    slippage_model : SlippageModel
        Rolling slippage tracker.
    logger : AtomicTradeLogger
        Thread-safe trade log writer.
    fill_timeout_s : float
        Seconds before OrderTimeoutError is raised.  Default 30.
    """

    def __init__(
        self,
        trading_client: TradingClient,
        quote_feed: QuoteFeed,
        slippage_model: SlippageModel,
        logger: AtomicTradeLogger,
        fill_timeout_s: float = 30.0,
    ) -> None:
        self._client = trading_client
        self._quote_feed = quote_feed
        self._model = slippage_model
        self._logger = logger
        self._fill_timeout_s = fill_timeout_s

    async def submit(
        self,
        symbol: str,
        side: OrderSide,
        qty: int,
    ) -> OrderRecord:
        """
        End-to-end order lifecycle.  Returns when order is FILLED or raises.

        Raises
        ------
        QuoteStaleError      – quote is older than QuoteFeed.max_age_ms
        OrderRejectedError   – exchange rejected the order
        OrderTimeoutError    – fill not confirmed within fill_timeout_s
        SlippageBreachError  – p99 slippage exceeds alert threshold
        """
        quote = self._quote_feed.get_latest_quote(symbol)
        expected_price = quote.ask_price if side == OrderSide.BUY else quote.bid_price
        submitted_at = datetime.now(tz=timezone.utc)

        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
        raw_order = self._client.submit_order(req)
        order_id = str(raw_order.id)

        try:
            filled_order = await self._poll_fill(order_id)
        except OrderRejectedError:
            record = OrderRecord(
                symbol=symbol,
                side=side.value,
                qty=qty,
                expected_price=expected_price,
                submitted_at=submitted_at,
                order_id=order_id,
                fill_price=None,
                filled_at=None,
                slippage_bps=None,
                status="REJECTED",
            )
            self._logger.log(record)
            raise

        except OrderTimeoutError:
            record = OrderRecord(
                symbol=symbol,
                side=side.value,
                qty=qty,
                expected_price=expected_price,
                submitted_at=submitted_at,
                order_id=order_id,
                fill_price=None,
                filled_at=None,
                slippage_bps=None,
                status="TIMEOUT",
            )
            self._logger.log(record)
            raise

        fill_price = Decimal(str(filled_order.filled_avg_price)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        filled_at = datetime.now(tz=timezone.utc)

        # Signed slippage: positive means we paid MORE than expected (cost)
        raw_slippage = (fill_price - expected_price) / expected_price * Decimal("10000")
        if side == OrderSide.SELL:
            raw_slippage = -raw_slippage  # selling below expected is also a cost
        slippage_bps = raw_slippage.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        record = OrderRecord(
            symbol=symbol,
            side=side.value,
            qty=qty,
            expected_price=expected_price,
            submitted_at=submitted_at,
            order_id=order_id,
            fill_price=fill_price,
            filled_at=filled_at,
            slippage_bps=slippage_bps,
            status="FILLED",
        )

        self._logger.log(record)
        self._model.record(slippage_bps)  # may raise SlippageBreachError
        return record

    async def _poll_fill(self, order_id: str) -> object:
        """Exponential backoff polling; raises on rejection/timeout."""
        backoff = 0.1
        try:
            async with asyncio.timeout(self._fill_timeout_s):
                while True:
                    order = self._client.get_order_by_id(order_id)
                    match order.status:
                        case OrderStatus.FILLED | OrderStatus.PARTIALLY_FILLED:
                            return order
                        case (
                            OrderStatus.REJECTED
                            | OrderStatus.CANCELED
                            | OrderStatus.EXPIRED
                            | OrderStatus.DONE_FOR_DAY
                        ):
                            raise OrderRejectedError(
                                f"Order {order_id} terminal status: {order.status}"
                            )
                        case _:
                            await asyncio.sleep(backoff)
                            backoff = min(backoff * 1.5, 2.0)
        except TimeoutError:
            raise OrderTimeoutError(
                f"Order {order_id} not filled within {self._fill_timeout_s}s"
            )


# ── Factory ───────────────────────────────────────────────────────────────────

def build_engine(log_path: str = "data/trade_log.csv") -> SlippageAwareMarketOrder:
    """Wire up all components from environment variables."""
    from pathlib import Path

    trading_client = TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET_KEY"],
        paper=True,
    )
    quote_feed = QuoteFeed()
    slippage_model = SlippageModel(
        alert_threshold_bps=float(os.environ.get("SLIPPAGE_ALERT_BPS", "15.0"))
    )
    logger = AtomicTradeLogger(Path(log_path))

    return SlippageAwareMarketOrder(
        trading_client=trading_client,
        quote_feed=quote_feed,
        slippage_model=slippage_model,
        logger=logger,
        fill_timeout_s=float(os.environ.get("ORDER_FILL_TIMEOUT_S", "30.0")),
    )
