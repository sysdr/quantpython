"""
Core arrival-price fill engine.
Principle: BUY fills at ask, SELL fills at bid. Slippage = (fill - mid) / mid * 10000.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum


class Side(str, Enum):
    """str+Enum works on Python 3.10+ (StrEnum is 3.11+)."""
    BUY = "buy"
    SELL = "sell"


_TICK = Decimal("0.0001")  # 4dp rounding for USD prices


@dataclass(frozen=True, slots=True)
class Quote:
    """Immutable NBBO snapshot. Prices stored as Decimal to avoid IEEE-754 drift."""
    bid: Decimal
    ask: Decimal
    timestamp_ns: int

    @property
    def mid(self) -> Decimal:
        return ((self.bid + self.ask) / 2).quantize(_TICK, rounding=ROUND_HALF_UP)

    @property
    def spread_bps(self) -> float:
        if self.mid == 0:
            return 0.0
        return float((self.ask - self.bid) / self.mid * 10_000)

    @classmethod
    def from_floats(cls, bid: float, ask: float) -> "Quote":
        """Safe constructor from broker float responses."""
        return cls(
            bid=Decimal(str(bid)),
            ask=Decimal(str(ask)),
            timestamp_ns=time.time_ns(),
        )


@dataclass(slots=True)
class FillResult:
    """Result of a matched order including realized slippage."""
    order_id: str
    symbol: str
    side: Side
    qty: Decimal
    arrival_mid: Decimal    # Mid-price at order construction time
    arrival_price: Decimal  # Expected fill (ask for buy, bid for sell)
    fill_price: Decimal
    fill_timestamp_ns: int
    slippage_bps: float = field(init=False)

    def __post_init__(self) -> None:
        if self.arrival_mid > 0:
            raw = float(
                (self.fill_price - self.arrival_mid) / self.arrival_mid * 10_000
            )
            # For sells: filling above mid is good → invert sign convention
            self.slippage_bps = raw if self.side == Side.BUY else -raw
        else:
            self.slippage_bps = 0.0

    @property
    def latency_ms(self) -> float:
        return (self.fill_timestamp_ns - self.arrival_mid) / 1_000_000

    def summary(self) -> str:
        return (
            f"[{self.order_id[:8]}] {self.side.upper()} {self.qty} {self.symbol} | "
            f"mid={self.arrival_mid:.4f} fill={self.fill_price:.4f} | "
            f"slippage={self.slippage_bps:+.2f}bps"
        )


def compute_arrival_price(quote: Quote, side: Side) -> Decimal:
    """
    The single source of truth for expected fill price.
    BUY crosses the spread upward → pays the ask.
    SELL crosses the spread downward → receives the bid.
    No averaging, no weighting. Atomic and testable.
    """
    return quote.ask if side == Side.BUY else quote.bid


def estimate_market_impact_bps(qty: Decimal, adv: Decimal) -> float:
    """
    Simple square-root market impact model.
    impact ≈ participation_rate^0.5 * 10 bps (rough calibration for equities).
    adv = average daily volume in shares.
    """
    if adv <= 0:
        return 0.0
    participation = float(qty / adv)
    return (participation ** 0.5) * 10.0
