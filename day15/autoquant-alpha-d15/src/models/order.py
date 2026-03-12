from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from uuid import uuid4


class OrderState(Enum):
    PENDING   = auto()
    QUEUED    = auto()
    SUBMITTED = auto()
    FILLED    = auto()
    PARTIAL   = auto()
    REJECTED  = auto()
    EXPIRED   = auto()
    DLQ       = auto()


class OrderSide(Enum):
    BUY  = "buy"
    SELL = "sell"


@dataclass
class TradeOrder:
    """Immutable-by-convention order record. State transitions are explicit."""

    symbol:   str
    qty:      float
    side:     OrderSide
    limit_px: float | None = None  # None → market order

    # System-managed fields — do NOT set manually
    order_id:     str        = field(default_factory=lambda: str(uuid4()))
    state:        OrderState = field(default=OrderState.PENDING)
    created_ns:   int        = field(default_factory=time.monotonic_ns)
    submitted_ns: int | None = field(default=None)
    filled_ns:    int | None = field(default=None)
    filled_px:    float | None = field(default=None)
    retries:      int        = field(default=0)
    error:        str | None = field(default=None)
    alpaca_id:    str | None = field(default=None)

    def queue_latency_ms(self) -> float | None:
        """Monotonic ns delta: creation → submission, in milliseconds."""
        if self.submitted_ns is None:
            return None
        return (self.submitted_ns - self.created_ns) / 1_000_000

    def fill_latency_ms(self) -> float | None:
        """Monotonic ns delta: submission → fill confirmation."""
        if self.submitted_ns is None or self.filled_ns is None:
            return None
        return (self.filled_ns - self.submitted_ns) / 1_000_000

    def slippage_bps(self) -> float | None:
        """
        Slippage in basis points relative to limit price.
        Returns None for market orders or unfilled orders.
        """
        if self.limit_px is None or self.filled_px is None:
            return None
        return abs(self.filled_px - self.limit_px) / self.limit_px * 10_000
