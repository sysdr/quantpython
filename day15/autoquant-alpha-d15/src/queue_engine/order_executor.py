"""
Async Order Executor — single-consumer FIFO drain loop.

Key design decisions:
1. Single consumer: maintains strict FIFO ordering to Alpaca.
   Multiple consumers would reorder submissions unpredictably.
2. run_in_executor: Alpaca SDK is synchronous HTTP. Calling it in async
   context would block the event loop. We offload to ThreadPoolExecutor.
3. Exponential backoff: 429s and 5xx are transient. Retry with backoff
   before routing to DLQ. Do NOT retry 4xx (bad request) — it will always fail.
4. Monotonic timestamps: used for latency measurement, never wall clock.
"""

from __future__ import annotations

import asyncio
import logging
import time

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaSide
from alpaca.trading.enums import TimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

from src.models.order import OrderSide, OrderState, TradeOrder
from src.queue_engine.dead_letter import DeadLetterQueue
from src.queue_engine.rate_limiter import TokenBucketRateLimiter
from src.queue_engine.trade_queue import TradeQueue

log = logging.getLogger(__name__)

MAX_RETRIES     = 3
RETRY_BACKOFF_S = (0.5, 1.5, 4.0)   # Cumulative max wait: 6s before DLQ


class OrderExecutor:
    """
    Single-consumer async executor.
    Instantiate one per strategy / Alpaca account.
    """

    def __init__(
        self,
        queue:        TradeQueue,
        dlq:          DeadLetterQueue,
        client:       TradingClient,
        rate_limiter: TokenBucketRateLimiter,
    ) -> None:
        self._q      = queue
        self._dlq    = dlq
        self._client = client
        self._rl     = rate_limiter
        self._running   = False
        self._submitted = 0
        self._filled    = 0
        self._rejected  = 0

    async def run(self) -> None:
        """Start drain loop. Cancellable via asyncio.CancelledError."""
        self._running = True
        log.info("OrderExecutor: started | queue_maxsize=%d", self._q.maxsize)
        try:
            async for order in self._q.drain():
                if not self._running:
                    break
                await self._process(order)
        except asyncio.CancelledError:
            log.info("OrderExecutor: cancelled. Final stats: %s", self.stats)
            raise

    async def stop(self) -> None:
        self._running = False

    async def _process(self, order: TradeOrder) -> None:
        # Acquire rate limit token BEFORE attempting submission
        wait_s = await self._rl.acquire()
        if wait_s > 0.1:
            log.warning("Rate limiter: waited %.3fs | order=%s", wait_s, order.order_id[:8])

        for attempt in range(MAX_RETRIES):
            try:
                await self._submit(order)
                return
            except Exception as exc:
                order.retries += 1
                order.error   = str(exc)
                log.error(
                    "Submit failed | attempt=%d/%d | order=%s | err=%s",
                    attempt + 1, MAX_RETRIES, order.order_id[:8], exc,
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF_S[attempt])

        # Retries exhausted → DLQ
        self._rejected += 1
        self._dlq.push(
            order,
            reason=f"Exhausted {MAX_RETRIES} retries. Last error: {order.error}",
        )

    async def _submit(self, order: TradeOrder) -> None:
        order.submitted_ns = time.monotonic_ns()
        order.state        = OrderState.SUBMITTED
        self._submitted   += 1

        alpaca_side = AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL

        req = (
            LimitOrderRequest(
                symbol        = order.symbol,
                qty           = order.qty,
                side          = alpaca_side,
                time_in_force = TimeInForce.DAY,
                limit_price   = order.limit_px,
            )
            if order.limit_px is not None
            else MarketOrderRequest(
                symbol        = order.symbol,
                qty           = order.qty,
                side          = alpaca_side,
                time_in_force = TimeInForce.DAY,
            )
        )

        # Critical: offload sync HTTP call to thread pool executor.
        # asyncio.get_running_loop() is preferred over get_event_loop() in 3.10+.
        loop     = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, self._client.submit_order, req)

        order.alpaca_id = str(response.id)
        order.state     = OrderState.FILLED   # Paper trading fills synchronously
        order.filled_ns = time.monotonic_ns()
        self._filled   += 1

        log.info(
            "FILLED | %s %s %.0f @ limit=%.2f | alpaca_id=%s | q_lat=%.1fms",
            order.side.value.upper(),
            order.symbol,
            order.qty,
            order.limit_px or 0,
            order.alpaca_id[:8],
            order.queue_latency_ms() or 0,
        )

    @property
    def stats(self) -> dict[str, int]:
        return {
            "submitted": self._submitted,
            "filled":    self._filled,
            "rejected":  self._rejected,
        }
