"""
Core FIFO Trade Queue.

Design choices:
- asyncio.Queue provides O(1) enqueue/dequeue via internal deque.
- maxsize acts as a hard circuit breaker: prevents OOM during event storms.
- Single-consumer pattern: one OrderExecutor drains this queue.
  Multi-consumer would break FIFO semantics across strategies.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from src.models.order import OrderState, TradeOrder

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QueueStats:
    depth:    int
    enqueued: int
    dequeued: int
    dropped:  int   # circuit breaker activations


class TradeQueue:
    """
    Production-grade async FIFO queue with circuit breaker.

    Thread safety: asyncio primitives are NOT thread-safe.
    Use from a single asyncio event loop only. If you need
    cross-thread enqueueing, use asyncio.Queue.put_nowait()
    from loop.call_soon_threadsafe().
    """

    def __init__(self, maxsize: int = 512) -> None:
        if maxsize < 1:
            raise ValueError(f"maxsize must be >= 1, got {maxsize}")
        self._q: asyncio.Queue[TradeOrder] = asyncio.Queue(maxsize=maxsize)
        self._enqueued = 0
        self._dequeued = 0
        self._dropped  = 0

    async def enqueue(self, order: TradeOrder) -> bool:
        """
        Attempt to enqueue an order. Returns False if circuit breaker triggered.
        Callers must handle False — route to DLQ, log, alert.
        """
        if self._q.full():
            self._dropped += 1
            order.state = OrderState.DLQ
            order.error = f"Circuit breaker: queue at capacity ({self._q.maxsize})"
            if self._dropped == 1 or self._dropped % 1000 == 0:
                log.warning(
                    "CIRCUIT BREAKER | dropped=%d | order=%s",
                    self._dropped, order.order_id[:8],
                )
            return False

        order.state = OrderState.QUEUED
        # put_nowait: we already checked full(), so this won't block.
        # Avoids a race condition between the check and the put.
        self._q.put_nowait(order)
        self._enqueued += 1
        log.debug("enqueue | id=%s | depth=%d", order.order_id[:8], self._q.qsize())
        return True

    async def dequeue(self) -> TradeOrder:
        """
        Block until an order is available. FIFO is guaranteed by asyncio.Queue
        which uses collections.deque internally (O(1) popleft).
        """
        order = await self._q.get()
        self._dequeued += 1
        self._q.task_done()
        return order

    async def drain(self) -> AsyncIterator[TradeOrder]:
        """Async generator: yields orders indefinitely. Use in executor loop."""
        while True:
            yield await self.dequeue()

    def stats(self) -> QueueStats:
        return QueueStats(
            depth    = self._q.qsize(),
            enqueued = self._enqueued,
            dequeued = self._dequeued,
            dropped  = self._dropped,
        )

    @property
    def depth(self) -> int:
        return self._q.qsize()

    @property
    def maxsize(self) -> int:
        return self._q.maxsize
