"""
Async Order Manager.

Architecture:
─────────────
┌─────────────────────────────┐
│   on_tick() [sync producer] │
│   signal → queue.put_nowait │
└──────────────┬──────────────┘
               │  asyncio.Queue (bounded, backpressure)
┌──────────────▼──────────────┐
│  OrderManager.run() [async] │
│  consumer coroutine         │
│  → HTTP submit to Alpaca    │
│  → on_fill callback         │
└─────────────────────────────┘

The queue size is intentionally limited (default 100).
If the consumer can't keep up (rate limit / network), new signals are
DROPPED rather than queued indefinitely. This is a deliberate risk
management decision: a 200ms-old signal is worse than no signal.
"""
from __future__ import annotations
import asyncio
import time
import logging
from typing import Optional, Callable

from ..core.types import Signal, SignalDirection, SignalState, OrderResult

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(
        self,
        alpaca_client,
        queue_size: int = 100,
        on_fill: Optional[Callable[[Signal, OrderResult], None]] = None,
    ) -> None:
        self._client   = alpaca_client
        self._queue: asyncio.Queue[Signal] = asyncio.Queue(maxsize=queue_size)
        self._on_fill  = on_fill
        self._running  = False

    async def submit(self, signal: Signal) -> None:
        """
        Non-blocking enqueue. Returns immediately.
        Drops signal (with warning) if queue is at capacity.
        """
        try:
            self._queue.put_nowait(signal)
            signal.state = SignalState.QUEUED
        except asyncio.QueueFull:
            signal.state = SignalState.CANCELLED
            logger.warning(
                "[OrderManager] Queue full. Dropped %s %s @ %.4f",
                signal.symbol, signal.direction.name, signal.reference_price,
            )

    async def run(self) -> None:
        """
        Main consumer loop. Run as an asyncio.create_task().

        Uses wait_for(timeout=1.0) so the loop can detect shutdown
        even when the queue is idle (avoids a hung task on teardown).
        """
        self._running = True
        logger.info("[OrderManager] Consumer loop started.")
        while self._running:
            try:
                signal = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._process(signal)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                logger.error("[OrderManager] Unhandled consumer error: %s", exc)

    async def _process(self, signal: Signal) -> None:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums   import OrderSide, TimeInForce

        signal.state = SignalState.VALIDATED
        t0   = time.perf_counter()
        side = OrderSide.BUY if signal.direction == SignalDirection.LONG else OrderSide.SELL

        req = MarketOrderRequest(
            symbol        = signal.symbol,
            qty           = signal.quantity,
            side          = side,
            time_in_force = TimeInForce.DAY,
        )

        try:
            signal.state = SignalState.SUBMITTED
            order        = self._client.submit_order(req)
            latency_ms   = (time.perf_counter() - t0) * 1_000

            fill_px = float(order.filled_avg_price or signal.reference_price)
            result  = OrderResult(
                order_id   = str(order.id),
                symbol     = signal.symbol,
                fill_price = fill_px,
                filled_qty = int(order.filled_qty or signal.quantity),
                status     = str(order.status),
                latency_ms = round(latency_ms, 2),
            )

            signal.state      = SignalState.FILLED
            signal.order_id   = result.order_id
            signal.fill_price = result.fill_price

            logger.info(
                "[FILL] %s %s qty=%d fill=%.4f ref=%.4f slip=%.2fbps lat=%.1fms id=%s",
                signal.symbol, signal.direction.name, result.filled_qty,
                result.fill_price, signal.reference_price,
                signal.slippage_bps or 0.0,
                result.latency_ms, result.order_id,
            )

            if self._on_fill:
                self._on_fill(signal, result)

        except Exception as exc:
            signal.state = SignalState.REJECTED
            logger.error("[OrderManager] Order rejected for %s: %s", signal.symbol, exc)

    def stop(self) -> None:
        self._running = False
