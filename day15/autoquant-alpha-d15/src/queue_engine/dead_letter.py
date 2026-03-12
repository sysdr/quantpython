"""
Dead Letter Queue (DLQ).

Invariants:
1. Every failed order MUST be persisted to disk before this function returns.
   A crash after push() but before _persist() would lose the audit record.
   We persist synchronously — DLQ is the cold path, latency here is acceptable.
2. In-memory ring buffer (deque with maxlen) for dashboard display.
   We do NOT keep all DLQ entries in memory — that defeats the OOM protection.
3. CSV is append-only. Never truncate or overwrite. Compliance requires this.
"""

from __future__ import annotations

import csv
import logging
from collections import deque
from dataclasses import asdict
from pathlib import Path

from src.models.order import OrderState, TradeOrder

log = logging.getLogger(__name__)


class DeadLetterQueue:

    def __init__(self, output_dir: Path, maxlen: int = 1_000) -> None:
        self._buf: deque[TradeOrder] = deque(maxlen=maxlen)
        self._dir = output_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._csv = output_dir / "dead_letters.csv"
        self._count = 0

    def push(self, order: TradeOrder, reason: str) -> None:
        """Route a failed order to the DLQ. Synchronous disk write."""
        order.state = OrderState.DLQ
        order.error = reason
        self._buf.append(order)
        self._persist(order)
        self._count += 1
        log.error(
            "DLQ[%d] | %s | %s | reason=%s",
            self._count, order.order_id[:8], order.symbol, reason,
        )

    def recent(self, n: int = 10) -> list[TradeOrder]:
        return list(self._buf)[-n:]

    def __len__(self) -> int:
        return self._count

    def _persist(self, order: TradeOrder) -> None:
        row = asdict(order)
        row["state"] = order.state.name
        row["side"]  = order.side.value

        write_header = not self._csv.exists()
        # Open in append mode. If process crashes after this line, the file
        # is already created; next push() will skip the header.
        with self._csv.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(row)
            fh.flush()
