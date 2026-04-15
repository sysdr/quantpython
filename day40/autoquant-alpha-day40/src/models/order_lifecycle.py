from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class OrderState(Enum):
    NEW              = "new"
    PENDING_SUBMIT   = "pending_submit"
    ACCEPTED         = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED           = "filled"
    CANCELLED        = "cancelled"
    REJECTED         = "rejected"
    EXPIRED          = "expired"


TERMINAL_STATES: frozenset[OrderState] = frozenset({
    OrderState.FILLED,
    OrderState.CANCELLED,
    OrderState.REJECTED,
    OrderState.EXPIRED,
})


@dataclass(slots=True)
class FillEvent:
    """Immutable record of a single fill or partial-fill event."""
    fill_id: str
    qty: float
    price: float
    broker_timestamp: datetime    # UTC timestamp FROM Alpaca server
    local_receipt_at: datetime    # UTC timestamp captured first-line in handler

    def network_latency_ms(self) -> float:
        """
        Time between broker event timestamp and local receipt.
        Can be slightly negative due to NTP clock skew — log as warning.
        """
        return (self.local_receipt_at - self.broker_timestamp).total_seconds() * 1_000.0


@dataclass(slots=True)
class OrderLifecycle:
    """
    Canonical lifecycle record for a single order.

    Timestamp Semantics
    -------------------
    created_at             : local time we built this record
    submitted_at           : local time we called submit_order()
    accepted_at            : broker timestamp from ACCEPTED event
    first_fill_at          : broker timestamp of first (partial) fill
    last_fill_at           : broker timestamp of terminal fill
    local_first_receipt_at : local time we processed first fill event
    local_last_receipt_at  : local time we processed last fill event

    Rule: never mix broker and local timestamps in a single latency formula.
    """
    order_id: str
    symbol: str
    qty: float
    side: str                          # "buy" | "sell"
    order_type: str                    # "market" | "limit" | etc.
    limit_price: Optional[float] = None

    state: OrderState = field(default=OrderState.NEW)

    # ── Timestamp chain ──────────────────────────────────────────────────────
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    submitted_at:            Optional[datetime] = None
    accepted_at:             Optional[datetime] = None
    first_fill_at:           Optional[datetime] = None
    last_fill_at:            Optional[datetime] = None
    local_first_receipt_at:  Optional[datetime] = None
    local_last_receipt_at:   Optional[datetime] = None

    # ── Fill accumulation ────────────────────────────────────────────────────
    fills:          list[FillEvent] = field(default_factory=list)
    filled_qty:     float           = 0.0
    avg_fill_price: float           = 0.0

    # ── Computed latency metrics (ms) ────────────────────────────────────────
    submission_latency_ms:  Optional[float] = None   # submitted_at → accepted_at
    fill_latency_ms:        Optional[float] = None   # accepted_at → last_fill_at
    network_latency_ms:     Optional[float] = None   # last broker_ts → local_receipt
    e2e_broker_latency_ms:  Optional[float] = None   # submitted_at → last_fill_at

    # ── State transitions ────────────────────────────────────────────────────

    def mark_submitted(self) -> None:
        self.submitted_at = datetime.now(timezone.utc)
        self.state = OrderState.PENDING_SUBMIT

    def mark_accepted(self, broker_ts: datetime) -> None:
        self.accepted_at = broker_ts
        self.state = OrderState.ACCEPTED
        if self.submitted_at is not None:
            self.submission_latency_ms = (
                (broker_ts - self.submitted_at).total_seconds() * 1_000.0
            )

    def mark_cancelled(self) -> None:
        self.state = OrderState.CANCELLED

    def mark_rejected(self) -> None:
        self.state = OrderState.REJECTED

    def apply_fill(self, fill: FillEvent) -> None:
        """
        Apply a fill or partial-fill event.

        Updates VWAP, timestamps, and state atomically.
        Raises ValueError if called on a non-fillable state.

        VWAP: ((old_qty * old_px) + (new_qty * new_px)) / total_qty
        Float epsilon guard prevents qty from stalling below self.qty
        due to floating-point representation.
        """
        if self.state in TERMINAL_STATES and self.state is not OrderState.PARTIALLY_FILLED:
            raise ValueError(
                f"Cannot apply fill to order {self.order_id!r} "
                f"in terminal state {self.state.value!r}"
            )

        # VWAP update
        old_notional = self.filled_qty * self.avg_fill_price
        new_notional = fill.qty * fill.price
        self.filled_qty += fill.qty
        self.avg_fill_price = (old_notional + new_notional) / self.filled_qty

        self.fills.append(fill)

        # Timestamp chain
        if self.first_fill_at is None:
            self.first_fill_at          = fill.broker_timestamp
            self.local_first_receipt_at = fill.local_receipt_at
        self.last_fill_at          = fill.broker_timestamp
        self.local_last_receipt_at = fill.local_receipt_at

        # State transition — epsilon guard for floating-point residuals
        if self.filled_qty >= self.qty - 1e-9:
            self.state = OrderState.FILLED
            self._compute_terminal_latencies()
        else:
            self.state = OrderState.PARTIALLY_FILLED

    def _compute_terminal_latencies(self) -> None:
        if self.accepted_at and self.last_fill_at:
            self.fill_latency_ms = (
                (self.last_fill_at - self.accepted_at).total_seconds() * 1_000.0
            )
        if self.last_fill_at and self.local_last_receipt_at:
            self.network_latency_ms = (
                (self.local_last_receipt_at - self.last_fill_at).total_seconds() * 1_000.0
            )
        if self.submitted_at and self.last_fill_at:
            self.e2e_broker_latency_ms = (
                (self.last_fill_at - self.submitted_at).total_seconds() * 1_000.0
            )

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def to_dict(self) -> dict:
        def fmt(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return {
            "order_id":               self.order_id,
            "symbol":                 self.symbol,
            "qty":                    self.qty,
            "side":                   self.side,
            "order_type":             self.order_type,
            "limit_price":            self.limit_price,
            "state":                  self.state.value,
            "filled_qty":             round(self.filled_qty, 8),
            "avg_fill_price":         round(self.avg_fill_price, 6),
            "fill_count":             len(self.fills),
            "created_at":             fmt(self.created_at),
            "submitted_at":           fmt(self.submitted_at),
            "accepted_at":            fmt(self.accepted_at),
            "first_fill_at":          fmt(self.first_fill_at),
            "last_fill_at":           fmt(self.last_fill_at),
            "local_first_receipt_at": fmt(self.local_first_receipt_at),
            "local_last_receipt_at":  fmt(self.local_last_receipt_at),
            "submission_latency_ms":  self.submission_latency_ms,
            "fill_latency_ms":        self.fill_latency_ms,
            "network_latency_ms":     self.network_latency_ms,
            "e2e_broker_latency_ms":  self.e2e_broker_latency_ms,
        }
