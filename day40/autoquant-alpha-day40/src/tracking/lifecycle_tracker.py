from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Awaitable, Callable

from src.models.order_lifecycle import FillEvent, OrderLifecycle

log = logging.getLogger(__name__)


class LifecycleTracker:
    """
    Async-safe order lifecycle store with LRU eviction.

    Design contract
    ---------------
    All mutations serialized under asyncio.Lock — no TOCTOU races.
    Callbacks fire OUTSIDE the lock — prevent re-entrant deadlocks.
    LRU via OrderedDict.move_to_end() / popitem(last=False) — O(1).
    Memory bound: max_orders × ~1.2 KB ≈ 12 MB at 10_000 orders.
    """

    def __init__(self, max_orders: int = 10_000) -> None:
        self._orders: OrderedDict[str, OrderLifecycle] = OrderedDict()
        self._lock = asyncio.Lock()
        self._max_orders = max_orders
        self._callbacks: list[Callable[[OrderLifecycle], Awaitable[None]]] = []
        self._orphan_count: int = 0
        self._eviction_count: int = 0

    # ── Lifecycle mutations (all under lock) ─────────────────────────────────

    async def register_order(self, lifecycle: OrderLifecycle) -> None:
        async with self._lock:
            if len(self._orders) >= self._max_orders:
                evicted_id, _ = self._orders.popitem(last=False)
                self._eviction_count += 1
                log.warning("LRU eviction: order %s removed before terminal state", evicted_id)
            self._orders[lifecycle.order_id] = lifecycle
            log.debug("Registered order %s (%s %s x %.2f)",
                      lifecycle.order_id, lifecycle.side, lifecycle.symbol, lifecycle.qty)

    async def mark_accepted(self, order_id: str, broker_ts) -> None:
        async with self._lock:
            if (lc := self._orders.get(order_id)) is None:
                self._orphan_count += 1
                log.warning("Orphan ACCEPTED event for unknown order_id=%s", order_id)
                return
            lc.mark_accepted(broker_ts)
            self._orders.move_to_end(order_id)

    async def on_fill_event(
        self, order_id: str, fill: FillEvent
    ) -> OrderLifecycle | None:
        """
        Apply a fill event. Returns the mutated lifecycle, or None for orphan fills.
        Callbacks fire outside lock with the (already-mutated) lifecycle snapshot.
        """
        async with self._lock:
            if (lc := self._orders.get(order_id)) is None:
                self._orphan_count += 1
                log.warning(
                    "Orphan FILL fill_id=%s for unknown order_id=%s",
                    fill.fill_id, order_id,
                )
                return None
            try:
                lc.apply_fill(fill)
            except ValueError as exc:
                log.error("Fill rejected: %s", exc)
                return None
            self._orders.move_to_end(order_id)

        # Callbacks outside lock
        for cb in self._callbacks:
            try:
                await cb(lc)
            except Exception:
                log.exception("Lifecycle callback raised for order %s", order_id)

        return lc

    async def mark_cancelled(self, order_id: str) -> None:
        async with self._lock:
            if lc := self._orders.get(order_id):
                lc.mark_cancelled()

    # ── Registration ─────────────────────────────────────────────────────────

    def register_callback(
        self, cb: Callable[[OrderLifecycle], Awaitable[None]]
    ) -> None:
        """Register an async callback invoked after every fill event."""
        self._callbacks.append(cb)

    # ── Queries (lock-free — read consistency is eventual) ───────────────────

    def get(self, order_id: str) -> OrderLifecycle | None:
        return self._orders.get(order_id)

    def all_terminal(self) -> list[OrderLifecycle]:
        return [lc for lc in self._orders.values() if lc.is_terminal]

    def active(self) -> list[OrderLifecycle]:
        return [lc for lc in self._orders.values() if not lc.is_terminal]

    @property
    def stats(self) -> dict:
        counts: dict[str, int] = {}
        for lc in self._orders.values():
            counts[lc.state.value] = counts.get(lc.state.value, 0) + 1
        return {
            "total_tracked":  len(self._orders),
            "orphan_fills":   self._orphan_count,
            "evictions":      self._eviction_count,
            "by_state":       counts,
        }
