"""
Core domain types for AutoQuant-Alpha Day 8.

Design principles:
- MarketSnapshot is FROZEN (immutable after creation).
- Signal is MUTABLE (state transitions through its lifecycle).
- Use __slots__ everywhere to prevent attribute bloat and speed up attribute access.
- Avoid Optional[float] with sentinel None checks in hot paths;
  use separate state flags instead.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import time


class SignalDirection(Enum):
    LONG  = auto()
    SHORT = auto()
    FLAT  = auto()


class SignalState(Enum):
    PENDING   = auto()   # Created by on_tick()
    VALIDATED = auto()   # Passed pre-execution checks
    QUEUED    = auto()   # In asyncio.Queue
    SUBMITTED = auto()   # HTTP request sent to broker
    FILLED    = auto()   # Confirmed fill received
    REJECTED  = auto()   # Broker refused order
    CANCELLED = auto()   # Dropped (queue full / risk gate)


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """
    Immutable point-in-time market state.

    Frozen so it can be safely passed across coroutines without copying.
    The timestamp_ns field uses time.time_ns() for nanosecond precision —
    critical for accurate latency accounting.
    """
    symbol:       str
    bid:          float
    ask:          float
    last:         float
    volume:       int
    timestamp_ns: int = field(default_factory=time.time_ns)

    @property
    def mid(self) -> float:
        """Mid-price. Used as neutral reference for indicator computation."""
        return (self.bid + self.ask) * 0.5

    @property
    def spread_bps(self) -> float:
        """
        Bid-ask spread in basis points.
        Spread > 10 bps on liquid names signals either thin book or
        a data quality problem. Do not trade through wide spreads.
        """
        m = self.mid
        if m == 0.0:
            return 0.0
        return (self.ask - self.bid) / m * 10_000.0


@dataclass(slots=True)
class Signal:
    """
    Mutable signal entity. Transitions through SignalState lifecycle.

    reference_price: price used for slippage calculation.
      For LONGs  → ask price (cost to buy immediately)
      For SHORTs → bid price (proceeds from selling immediately)
    """
    symbol:          str
    direction:       SignalDirection
    confidence:      float        # [0.0, 1.0]
    reference_price: float
    quantity:        int
    state:           SignalState  = SignalState.PENDING
    generated_at_ns: int          = field(default_factory=time.time_ns)
    order_id:        Optional[str]   = None
    fill_price:      Optional[float] = None

    @property
    def slippage_bps(self) -> Optional[float]:
        """
        Signed slippage in basis points relative to reference_price.

        Positive = paid more / received less than expected.
        Both outcomes are costs to the strategy.
        Target: < 5 bps average on liquid paper-trading names.
        """
        if self.fill_price is None or self.reference_price == 0.0:
            return None
        raw = (self.fill_price - self.reference_price) / self.reference_price * 10_000.0
        return raw if self.direction == SignalDirection.LONG else -raw


@dataclass(frozen=True, slots=True)
class OrderResult:
    """Immutable record of a completed order submission."""
    order_id:   str
    symbol:     str
    fill_price: float
    filled_qty: int
    status:     str
    latency_ms: float
