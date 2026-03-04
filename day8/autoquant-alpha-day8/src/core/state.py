"""
StrategyState: Thread-safe, atomic strategy state container.

Uses a reentrant lock (RLock) for writes. The RLock choice over a
regular Lock allows the same thread to acquire it multiple times —
important if update methods call each other internally.

The to_dict() method acquires the lock for the entire read operation,
guaranteeing a consistent snapshot even if a fill callback fires
concurrently with a dashboard poll.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import threading


@dataclass(slots=True)
class StrategyState:
    symbol:              str
    position:            int   = 0       # Net position (positive = long)
    realized_pnl:        float = 0.0
    total_signals:       int   = 0
    total_fills:         int   = 0
    last_signal_at_ns:   Optional[int] = None
    peak_pnl:            float = 0.0
    max_drawdown:        float = 0.0
    _lock: threading.RLock = field(
        default_factory=threading.RLock, repr=False, compare=False
    )

    def record_signal(self, timestamp_ns: int) -> None:
        with self._lock:
            self.total_signals += 1
            self.last_signal_at_ns = timestamp_ns

    def record_fill(self, qty_delta: int, fill_price: float, cost_basis: float) -> None:
        """
        Update position and compute realized P&L on close.

        qty_delta: positive for buys, negative for sells.
        cost_basis: average entry price of the position being closed.
        """
        with self._lock:
            if self.position != 0 and (qty_delta * self.position) < 0:
                # Closing or reversing position — realize P&L
                closed_qty = min(abs(qty_delta), abs(self.position))
                pnl_per_share = (fill_price - cost_basis) * (1 if self.position > 0 else -1)
                self.realized_pnl += pnl_per_share * closed_qty

            self.position += qty_delta
            self.total_fills += 1

            if self.realized_pnl > self.peak_pnl:
                self.peak_pnl = self.realized_pnl
            drawdown = self.peak_pnl - self.realized_pnl
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "symbol":        self.symbol,
                "position":      self.position,
                "realized_pnl":  round(self.realized_pnl, 4),
                "total_signals": self.total_signals,
                "total_fills":   self.total_fills,
                "peak_pnl":      round(self.peak_pnl, 4),
                "max_drawdown":  round(self.max_drawdown, 4),
            }
