"""
AtomicTradeLogger
-----------------
Thread-safe CSV trade logger. Uses a reentrant lock so that concurrent
fill callbacks never interleave rows. All writes are explicitly flushed
so the file is readable even while the process is live.
"""

from __future__ import annotations

import csv
import os
import threading
from decimal import Decimal
from pathlib import Path


_HEADERS = [
    "order_id",
    "symbol",
    "side",
    "qty",
    "expected_price",
    "fill_price",
    "slippage_bps",
    "net_slippage_cost",
    "submitted_at",
    "filled_at",
    "status",
]


class AtomicTradeLogger:
    """Append-only CSV trade log with a per-instance threading.RLock."""

    def __init__(self, log_path: Path) -> None:
        self._path = log_path
        self._lock = threading.RLock()
        self._ensure_header()

    def _ensure_header(self) -> None:
        with self._lock:
            if not self._path.exists() or self._path.stat().st_size == 0:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("w", newline="") as fh:
                    writer = csv.DictWriter(fh, fieldnames=_HEADERS)
                    writer.writeheader()

    def log(self, record: "OrderRecord") -> None:  # noqa: F821
        row = {
            "order_id": record.order_id,
            "symbol": record.symbol,
            "side": record.side,
            "qty": record.qty,
            "expected_price": str(record.expected_price),
            "fill_price": str(record.fill_price) if record.fill_price is not None else "",
            "slippage_bps": str(record.slippage_bps) if record.slippage_bps is not None else "",
            "net_slippage_cost": (
                str(record.net_slippage_cost) if record.net_slippage_cost is not None else ""
            ),
            "submitted_at": record.submitted_at.isoformat(),
            "filled_at": record.filled_at.isoformat() if record.filled_at else "",
            "status": record.status,
        }
        with self._lock:
            with self._path.open("a", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=_HEADERS)
                writer.writerow(row)
                fh.flush()
                os.fsync(fh.fileno())  # force kernel buffer → disk
