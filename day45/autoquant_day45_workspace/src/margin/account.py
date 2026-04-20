"""
margin/account.py
Core MarginAccount — atomic reserve/confirm/release with Decimal arithmetic.
"""
from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum, auto
from typing import Optional


PENNY = Decimal("0.01")
INITIAL_MARGIN_RATE   = Decimal("0.50")   # Reg T: 50%
MAINTENANCE_MARGIN_RATE = Decimal("0.25") # Reg T: 25%
DAY_TRADE_LEVERAGE    = Decimal("4")
OVERNIGHT_LEVERAGE    = Decimal("2")
PDT_EQUITY_THRESHOLD  = Decimal("25000.00")
PDT_TRADE_LIMIT       = 4


class AccountMode(Enum):
    CASH       = auto()
    MARGIN     = auto()   # Reg T, overnight 2x
    DAY_TRADE  = auto()   # PDT-eligible, intraday 4x


class MarginHealth(Enum):
    HEALTHY     = "healthy"       # ratio >= 35%
    AT_RISK     = "at_risk"       # 25% <= ratio < 35%
    MARGIN_CALL = "margin_call"   # 10% <= ratio < 25%
    LIQUIDATING = "liquidating"   # ratio < 10%


@dataclass
class Position:
    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    current_price: Decimal
    side: str = "long"   # "long" | "short"

    @property
    def market_value(self) -> Decimal:
        return (self.quantity * self.current_price).quantize(PENNY, ROUND_HALF_UP)

    @property
    def unrealized_pnl(self) -> Decimal:
        cost = (self.quantity * self.avg_cost).quantize(PENNY, ROUND_HALF_UP)
        return self.market_value - cost


@dataclass
class ReservationResult:
    success: bool
    order_id: str
    reason: str = ""
    available_before: Decimal = Decimal("0")
    requested: Decimal = Decimal("0")
    available_after: Decimal = Decimal("0")


@dataclass
class BuyingPower:
    day_trade_bp: Decimal
    overnight_bp: Decimal
    cash_bp: Decimal
    mode: AccountMode


@dataclass
class MarginSnapshot:
    cash: Decimal
    reserved: Decimal
    equity: Decimal
    total_long_exposure: Decimal
    total_short_exposure: Decimal
    margin_ratio: Decimal
    health: MarginHealth
    mode: AccountMode
    buying_power: BuyingPower


def _business_days_ago(n: int) -> date:
    """Return date n business days before today (simplified: skips weekends)."""
    result = date.today()
    count = 0
    while count < n:
        result -= timedelta(days=1)
        if result.weekday() < 5:  # Mon–Fri
            count += 1
    return result


class MarginAccount:
    """
    Thread-safe margin account with atomic reserve/confirm/release.

    All monetary values use Decimal for exact arithmetic.
    Supports CASH, MARGIN (Reg T), and DAY_TRADE (PDT 4x) modes.
    """

    def __init__(
        self,
        initial_cash: Decimal,
        mode: AccountMode = AccountMode.DAY_TRADE,
        account_id: Optional[str] = None,
    ) -> None:
        if not isinstance(initial_cash, Decimal):
            raise TypeError(f"initial_cash must be Decimal, got {type(initial_cash)}")

        self._lock   = threading.RLock()
        self._cash   = initial_cash
        self._mode   = mode
        self._account_id = account_id or str(uuid.uuid4())

        # order_id → reserved Decimal
        self._reservations: dict[str, Decimal] = {}
        self._reserved = Decimal("0")

        # Confirmed positions
        self._positions: dict[str, Position] = {}

        # PDT day-trade tracker: stores dates of round-trip closes
        self._day_trades: deque[date] = deque(maxlen=50)

    # ── Public Read Properties (lock-free snapshots are fine for monitoring) ──

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def cash(self) -> Decimal:
        with self._lock:
            return self._cash

    @property
    def reserved(self) -> Decimal:
        with self._lock:
            return self._reserved

    @property
    def positions(self) -> dict[str, Position]:
        with self._lock:
            return dict(self._positions)

    # ── Margin Calculations ───────────────────────────────────────────────────

    def _equity(self) -> Decimal:
        """Cash + unrealized P&L across all positions."""
        pos_pnl = sum(p.unrealized_pnl for p in self._positions.values())
        return (self._cash + pos_pnl).quantize(PENNY, ROUND_HALF_UP)

    def _total_long_exposure(self) -> Decimal:
        return sum(
            p.market_value for p in self._positions.values() if p.side == "long"
        ).quantize(PENNY, ROUND_HALF_UP) if self._positions else Decimal("0")

    def _compute_margin_ratio(self) -> Decimal:
        exposure = self._total_long_exposure()
        if exposure == Decimal("0"):
            return Decimal("1")
        return (self._equity() / exposure).quantize(
            Decimal("0.0001"), ROUND_HALF_UP
        )

    def _compute_health(self, ratio: Decimal) -> MarginHealth:
        if ratio >= Decimal("0.35"):
            return MarginHealth.HEALTHY
        elif ratio >= Decimal("0.25"):
            return MarginHealth.AT_RISK
        elif ratio >= Decimal("0.10"):
            return MarginHealth.MARGIN_CALL
        return MarginHealth.LIQUIDATING

    def _is_pdt_restricted(self) -> bool:
        """True if account has < $25k equity AND >= 4 day trades in 5 business days."""
        cutoff = _business_days_ago(5)
        recent = sum(1 for d in self._day_trades if d >= cutoff)
        return self._equity() < PDT_EQUITY_THRESHOLD and recent >= PDT_TRADE_LIMIT

    def _compute_buying_power(self) -> BuyingPower:
        equity = self._equity()
        available_cash = (self._cash - self._reserved).quantize(PENNY, ROUND_HALF_UP)

        if self._mode == AccountMode.CASH or self._is_pdt_restricted():
            return BuyingPower(
                day_trade_bp=available_cash,
                overnight_bp=available_cash,
                cash_bp=available_cash,
                mode=AccountMode.CASH,
            )
        elif self._mode == AccountMode.MARGIN:
            overnight_bp = (equity * OVERNIGHT_LEVERAGE - self._reserved).quantize(
                PENNY, ROUND_HALF_UP
            )
            return BuyingPower(
                day_trade_bp=overnight_bp,
                overnight_bp=max(overnight_bp, Decimal("0")),
                cash_bp=available_cash,
                mode=AccountMode.MARGIN,
            )
        else:  # DAY_TRADE
            dt_bp = (equity * DAY_TRADE_LEVERAGE - self._reserved).quantize(
                PENNY, ROUND_HALF_UP
            )
            on_bp = (equity * OVERNIGHT_LEVERAGE - self._reserved).quantize(
                PENNY, ROUND_HALF_UP
            )
            return BuyingPower(
                day_trade_bp=max(dt_bp, Decimal("0")),
                overnight_bp=max(on_bp, Decimal("0")),
                cash_bp=max(available_cash, Decimal("0")),
                mode=AccountMode.DAY_TRADE,
            )

    # ── Atomic Reserve / Confirm / Release ───────────────────────────────────

    def reserve(
        self, order_id: str, cost: Decimal, intraday: bool = True
    ) -> ReservationResult:
        """
        Atomically check and reserve buying power for an order.
        Must call confirm() on fill or release() on rejection/timeout.
        """
        if not isinstance(cost, Decimal):
            raise TypeError(f"cost must be Decimal, got {type(cost)}")
        if cost <= Decimal("0"):
            raise ValueError(f"cost must be positive, got {cost}")

        with self._lock:
            bp = self._compute_buying_power()
            available = bp.day_trade_bp if intraday else bp.overnight_bp
            available_before = available

            if order_id in self._reservations:
                return ReservationResult(
                    success=False,
                    order_id=order_id,
                    reason="DUPLICATE_ORDER_ID",
                    available_before=available_before,
                    requested=cost,
                    available_after=available_before,
                )

            # PDT hard gate
            if self._is_pdt_restricted() and intraday:
                return ReservationResult(
                    success=False,
                    order_id=order_id,
                    reason="PDT_RESTRICTED",
                    available_before=available_before,
                    requested=cost,
                    available_after=available_before,
                )

            if cost > available:
                return ReservationResult(
                    success=False,
                    order_id=order_id,
                    reason="INSUFFICIENT_BUYING_POWER",
                    available_before=available_before,
                    requested=cost,
                    available_after=available_before,
                )

            # Commit reservation
            self._reservations[order_id] = cost
            self._reserved += cost
            new_bp = self._compute_buying_power()
            available_after = new_bp.day_trade_bp if intraday else new_bp.overnight_bp

            return ReservationResult(
                success=True,
                order_id=order_id,
                available_before=available_before,
                requested=cost,
                available_after=available_after,
            )

    def confirm(
        self, order_id: str, actual_cost: Decimal, symbol: str,
        quantity: Decimal, fill_price: Decimal, side: str = "long"
    ) -> None:
        """
        Called on order fill. Converts reservation to actual position.
        Adjusts cash by actual_cost (may differ from reserved due to slippage).
        """
        with self._lock:
            reserved_cost = self._reservations.pop(order_id, None)
            if reserved_cost is None:
                raise KeyError(f"No reservation for order_id={order_id}")

            self._reserved -= reserved_cost
            self._cash -= actual_cost

            if symbol in self._positions:
                pos = self._positions[symbol]
                total_qty = pos.quantity + quantity
                total_cost = pos.quantity * pos.avg_cost + quantity * fill_price
                self._positions[symbol] = Position(
                    symbol=symbol,
                    quantity=total_qty,
                    avg_cost=(total_cost / total_qty).quantize(PENNY, ROUND_HALF_UP),
                    current_price=fill_price,
                    side=side,
                )
            else:
                self._positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity,
                    avg_cost=fill_price,
                    current_price=fill_price,
                    side=side,
                )

    def release(self, order_id: str) -> None:
        """Called on order rejection or timeout. Frees reservation."""
        with self._lock:
            cost = self._reservations.pop(order_id, None)
            if cost is not None:
                self._reserved -= cost

    def record_day_trade(self) -> None:
        """Record a day-trade round-trip for PDT tracking."""
        with self._lock:
            self._day_trades.append(date.today())

    def update_prices(self, prices: dict[str, Decimal]) -> None:
        """Update mark-to-market prices for all held positions."""
        with self._lock:
            for symbol, price in prices.items():
                if symbol in self._positions:
                    pos = self._positions[symbol]
                    self._positions[symbol] = Position(
                        symbol=pos.symbol,
                        quantity=pos.quantity,
                        avg_cost=pos.avg_cost,
                        current_price=price,
                        side=pos.side,
                    )

    def sync_from_alpaca_flat(self, broker_equity: Decimal) -> None:
        """
        When there are no open positions, set local cash to Alpaca equity so
        local buying power / equity track the broker for reconciliation UIs.
        Skips updates if the account already has simulated positions.
        """
        if not isinstance(broker_equity, Decimal):
            raise TypeError(f"broker_equity must be Decimal, got {type(broker_equity)}")
        with self._lock:
            if self._positions:
                return
            self._cash = broker_equity.quantize(PENNY, ROUND_HALF_UP)

    def snapshot(self) -> MarginSnapshot:
        """Return a consistent point-in-time snapshot of account state."""
        with self._lock:
            equity = self._equity()
            long_exp = self._total_long_exposure()
            ratio = self._compute_margin_ratio()
            return MarginSnapshot(
                cash=self._cash,
                reserved=self._reserved,
                equity=equity,
                total_long_exposure=long_exp,
                total_short_exposure=Decimal("0"),
                margin_ratio=ratio,
                health=self._compute_health(ratio),
                mode=self._mode,
                buying_power=self._compute_buying_power(),
            )
