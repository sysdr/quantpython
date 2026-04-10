"""
AutoQuant-Alpha | Day 35
Immutable TradeRecord with pre-computed derived fields.

Design Principle:
    __repr__ is a pure O(1) formatter.
    ALL computation happens in __post_init__, exactly once.
    This makes it safe to call from any thread, including logging background threads.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Sequence


# ── Precision constants ────────────────────────────────────────────────────
_BPS_PRECISION = Decimal("0.01")
_PNL_PRECISION = Decimal("0.01")
_PCT_PRECISION = Decimal("0.1")


@dataclass(frozen=True)
class TradeRecord:
    """
    Immutable snapshot of a completed (or partial) fill.

    Parameters
    ----------
    order_id : str
        Broker-assigned order ID (e.g., Alpaca UUID).
    symbol : str
        Ticker symbol (e.g., "AAPL").
    side : Literal["buy", "sell"]
        Direction of trade.
    requested_qty : Decimal
        Original order quantity.
    filled_qty : Decimal
        Quantity actually filled in this event.
    limit_price : Decimal
        Original limit price (or mid-price for market orders).
    fill_price : Decimal
        Actual execution price from broker.
    submitted_at : datetime
        UTC timestamp when order was submitted to exchange.
    filled_at : datetime
        UTC timestamp of this fill event.

    Derived Fields (computed in __post_init__, never re-computed)
    -------------------------------------------------------------
    slippage_bps    : Signed slippage vs limit price in basis points.
                      Positive = unfavorable (paid more / received less than limit).
    realized_pnl    : Signed P&L from fill vs limit. Positive = favorable fill.
    fill_duration_ms: Milliseconds from submission to this fill.
    fill_ratio      : Percentage of requested_qty filled (0–100).
    """

    # ── Core fields ───────────────────────────────────────────────────────
    order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    requested_qty: Decimal
    filled_qty: Decimal
    limit_price: Decimal
    fill_price: Decimal
    submitted_at: datetime
    filled_at: datetime

    # ── Derived fields — DO NOT pass these in constructor ─────────────────
    slippage_bps: Decimal = field(init=False, repr=False)
    realized_pnl: Decimal = field(init=False, repr=False)
    fill_duration_ms: float = field(init=False, repr=False)
    fill_ratio: Decimal = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """
        Compute all derived fields ONCE at construction time.

        We use object.__setattr__ because frozen=True blocks normal assignment.
        This is the documented pattern for frozen dataclasses with derived fields.

        Slippage sign convention:
            buy:  fill_price > limit_price → positive (paid more = bad)
            sell: fill_price < limit_price → positive (received less = bad)
        """
        # ── Validate inputs ───────────────────────────────────────────────
        if self.requested_qty <= 0:
            raise ValueError(f"requested_qty must be positive, got {self.requested_qty}")
        if self.filled_qty < 0 or self.filled_qty > self.requested_qty:
            raise ValueError(
                f"filled_qty={self.filled_qty} out of range [0, {self.requested_qty}]"
            )
        if self.limit_price <= 0:
            raise ValueError(f"limit_price must be positive, got {self.limit_price}")
        if self.fill_price <= 0:
            raise ValueError(f"fill_price must be positive, got {self.fill_price}")
        if self.filled_at < self.submitted_at:
            raise ValueError("filled_at cannot be before submitted_at")

        # ── Slippage in basis points ──────────────────────────────────────
        # bps = (fill - limit) / limit × 10_000
        # For sells, we flip sign so positive = unfavorable in both directions
        raw = (self.fill_price - self.limit_price) / self.limit_price * Decimal("10000")
        signed = raw if self.side == "buy" else -raw
        object.__setattr__(
            self, "slippage_bps", signed.quantize(_BPS_PRECISION, rounding=ROUND_HALF_UP)
        )

        # ── Realized P&L ──────────────────────────────────────────────────
        # buy:  favorable if fill_price < limit_price → pnl = (limit - fill) × qty
        # sell: favorable if fill_price > limit_price → pnl = (fill - limit) × qty
        if self.side == "buy":
            pnl = (self.limit_price - self.fill_price) * self.filled_qty
        else:
            pnl = (self.fill_price - self.limit_price) * self.filled_qty
        object.__setattr__(
            self, "realized_pnl", pnl.quantize(_PNL_PRECISION, rounding=ROUND_HALF_UP)
        )

        # ── Fill duration ─────────────────────────────────────────────────
        delta_ms = (self.filled_at - self.submitted_at).total_seconds() * 1000.0
        object.__setattr__(self, "fill_duration_ms", round(delta_ms, 3))

        # ── Fill ratio ────────────────────────────────────────────────────
        ratio = (self.filled_qty / self.requested_qty * Decimal("100")).quantize(
            _PCT_PRECISION, rounding=ROUND_HALF_UP
        )
        object.__setattr__(self, "fill_ratio", ratio)

    def __repr__(self) -> str:
        """
        Pure O(1) string formatter. Zero computation. Thread-safe by design.

        Called by logging formatters in the QueueListener background thread.
        Must NEVER access external state, call datetime.now(), or do I/O.
        """
        slip_sign = "+" if self.slippage_bps >= 0 else ""
        pnl_sign = "+" if self.realized_pnl >= 0 else ""
        return (
            f"TradeRecord("
            f"id={self.order_id!r}, "
            f"sym={self.symbol}, "
            f"side={self.side.upper()}, "
            f"fill={self.fill_price}/{self.limit_price} "
            f"slip={slip_sign}{self.slippage_bps}bps, "
            f"pnl={pnl_sign}{self.realized_pnl}, "
            f"filled={self.fill_ratio}%, "
            f"latency={self.fill_duration_ms}ms"
            f")"
        )

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON logging."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "requested_qty": str(self.requested_qty),
            "filled_qty": str(self.filled_qty),
            "limit_price": str(self.limit_price),
            "fill_price": str(self.fill_price),
            "submitted_at": self.submitted_at.isoformat(),
            "filled_at": self.filled_at.isoformat(),
            "slippage_bps": str(self.slippage_bps),
            "realized_pnl": str(self.realized_pnl),
            "fill_duration_ms": self.fill_duration_ms,
            "fill_ratio": str(self.fill_ratio),
        }

    @classmethod
    def make_test_record(
        cls,
        symbol: str = "AAPL",
        side: Literal["buy", "sell"] = "buy",
        limit_price: str = "150.00",
        fill_price: str = "150.03",
        qty: str = "100",
        duration_ms: float = 12.5,
    ) -> "TradeRecord":
        """Factory for tests and demos — avoids datetime boilerplate."""
        from datetime import timezone, timedelta

        now = datetime.now(tz=timezone.utc)
        submitted = now - timedelta(milliseconds=duration_ms)
        return cls(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            requested_qty=Decimal(qty),
            filled_qty=Decimal(qty),
            limit_price=Decimal(limit_price),
            fill_price=Decimal(fill_price),
            submitted_at=submitted,
            filled_at=now,
        )


@dataclass(frozen=True)
class AggregatedTradeRecord:
    """
    Aggregates multiple partial-fill TradeRecords for the same order.

    Computes VWAP fill price and aggregate slippage across all tranches.
    Used when a single order is filled in multiple events (common for large orders).
    """

    order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    requested_qty: Decimal
    tranches: tuple[TradeRecord, ...]  # Immutable sequence of partial fills

    # Derived aggregate fields
    total_filled_qty: Decimal = field(init=False, repr=False)
    vwap_fill_price: Decimal = field(init=False, repr=False)
    vwap_slippage_bps: Decimal = field(init=False, repr=False)
    total_pnl: Decimal = field(init=False, repr=False)
    total_duration_ms: float = field(init=False, repr=False)
    aggregate_fill_ratio: Decimal = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.tranches:
            raise ValueError("AggregatedTradeRecord requires at least one tranche")

        limit_price = self.tranches[0].limit_price  # Use first tranche limit as reference

        total_qty = sum(t.filled_qty for t in self.tranches)
        object.__setattr__(self, "total_filled_qty", total_qty)

        # VWAP: sum(fill_price × qty) / sum(qty)
        vwap_num = sum(t.fill_price * t.filled_qty for t in self.tranches)
        vwap = (vwap_num / total_qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "vwap_fill_price", vwap)

        # Aggregate slippage using VWAP
        raw = (vwap - limit_price) / limit_price * Decimal("10000")
        signed = raw if self.side == "buy" else -raw
        object.__setattr__(
            self, "vwap_slippage_bps", signed.quantize(_BPS_PRECISION, rounding=ROUND_HALF_UP)
        )

        total_pnl = sum(t.realized_pnl for t in self.tranches)
        object.__setattr__(
            self, "total_pnl", total_pnl.quantize(_PNL_PRECISION, rounding=ROUND_HALF_UP)
        )

        # Duration: from first submit to last fill
        first_submit = min(t.submitted_at for t in self.tranches)
        last_fill = max(t.filled_at for t in self.tranches)
        object.__setattr__(
            self,
            "total_duration_ms",
            round((last_fill - first_submit).total_seconds() * 1000.0, 3),
        )

        ratio = (total_qty / self.requested_qty * Decimal("100")).quantize(
            _PCT_PRECISION, rounding=ROUND_HALF_UP
        )
        object.__setattr__(self, "aggregate_fill_ratio", ratio)

    def __repr__(self) -> str:
        lines = [
            f"AggregatedTradeRecord(",
            f"  order_id={self.order_id!r},",
            f"  sym={self.symbol} side={self.side.upper()},",
            f"  tranches={len(self.tranches)},",
            f"  vwap_fill={self.vwap_fill_price},",
            f"  vwap_slip={'+' if self.vwap_slippage_bps >= 0 else ''}{self.vwap_slippage_bps}bps,",
            f"  total_pnl={'+' if self.total_pnl >= 0 else ''}{self.total_pnl},",
            f"  filled={self.aggregate_fill_ratio}%,",
            f"  duration={self.total_duration_ms}ms",
            f")",
        ]
        tranche_lines = [
            f"  ├─ [{i+1}/{len(self.tranches)}] {t!r}"
            for i, t in enumerate(self.tranches)
        ]
        return "\n".join(lines[:3] + tranche_lines + lines[3:])
