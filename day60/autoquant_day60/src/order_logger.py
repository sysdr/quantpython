"""
Non-blocking atomic order logger.

Architecture: trading thread writes to SimpleQueue, daemon thread drains to JSONL.
Never block the execution path on I/O.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

_SENTINEL: Final[object] = object()


@dataclass(slots=True)
class OrderRecord:
    symbol: str
    side: str
    quantity: int
    mid_price: float
    atr: float
    predicted_slippage_bps: float
    adjusted_price: float
    alpaca_order_id: str | None
    fill_price: float | None
    realized_slippage_bps: float | None
    model_error_bps: float | None
    status: str                    # PENDING | SUBMITTED | FILLED | FAILED
    timestamp_utc: str
    latency_ms: float | None = None


class OrderLogger:
    """
    Thread-safe non-blocking order logger.

    Usage:
        logger = OrderLogger(Path("data/orders.jsonl"))
        logger.start()
        logger.log(record)
        logger.stop()
    """

    def __init__(self, log_path: Path) -> None:
        self._path = log_path
        self._q: queue.SimpleQueue[OrderRecord | object] = queue.SimpleQueue()
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._thread = threading.Thread(
            target=self._drain_loop,
            daemon=True,
            name="order-logger",
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        if not self._running:
            return
        self._q.put(_SENTINEL)
        if self._thread:
            self._thread.join(timeout=timeout)
        self._running = False

    def log(self, record: OrderRecord) -> None:
        """Non-blocking. Returns immediately."""
        self._q.put(record)

    def _drain_loop(self) -> None:
        with self._path.open("a", encoding="utf-8", buffering=1) as fh:
            while True:
                item = self._q.get()
                if item is _SENTINEL:
                    break
                # Flush each record atomically (line-buffered)
                fh.write(json.dumps(asdict(item)) + "\n")
