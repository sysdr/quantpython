"""
broker/mock_broker.py
MockBroker wiring MarginAccount into an order execution loop.
"""
from __future__ import annotations

import queue
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto
from typing import Optional

from ..margin.account import MarginAccount, ReservationResult


class OrderSide(Enum):
    BUY  = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    PENDING    = auto()
    RESERVED   = auto()
    SUBMITTED  = auto()
    FILLED     = auto()
    REJECTED   = auto()
    CANCELLED  = auto()


@dataclass
class Order:
    symbol: str
    side: OrderSide
    quantity: Decimal
    limit_price: Optional[Decimal]  # None = market
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: OrderStatus = OrderStatus.PENDING
    fill_price: Optional[Decimal] = None
    rejection_reason: str = ""
    submitted_ns: int = 0
    filled_ns: int = 0
    slippage_bps: Optional[Decimal] = None


@dataclass
class FillSimulator:
    """
    Simulates fills with configurable slippage for paper trading.
    Uses a uniform random model: slippage ~ U(0, max_slippage_bps).
    """
    max_slippage_bps: Decimal = Decimal("5")
    fill_delay_ms: float = 10.0

    def simulate_fill(self, order: Order) -> Decimal:
        import random
        base = order.limit_price or Decimal("0")
        slip_bps = Decimal(str(random.uniform(0, float(self.max_slippage_bps))))
        slippage = (base * slip_bps / Decimal("10000")).quantize(Decimal("0.01"))
        if order.side == OrderSide.BUY:
            return base + slippage
        return base - slippage


class MockBroker:
    """
    Executes orders against MarginAccount using the reserve→confirm/release pattern.
    Maintains an order log and emits fills to a queue for downstream consumption.
    """

    def __init__(
        self,
        account: MarginAccount,
        fill_simulator: Optional[FillSimulator] = None,
    ) -> None:
        self._account = account
        self._fill_sim = fill_simulator or FillSimulator()
        self._orders: dict[str, Order] = {}
        self._fill_queue: queue.Queue[Order] = queue.Queue()

    @property
    def fill_queue(self) -> queue.Queue:
        return self._fill_queue

    def submit(self, order: Order) -> Order:
        """
        Synchronous order submission:
        1. Reserve buying power (atomic)
        2. Simulate fill
        3. Confirm or release reservation
        """
        order.submitted_ns = time.perf_counter_ns()
        self._orders[order.order_id] = order

        if order.limit_price is None:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "MARKET_ORDERS_REQUIRE_PRICE_IN_MOCK"
            return order

        cost = (order.quantity * order.limit_price).quantize(Decimal("0.01"))
        result: ReservationResult = self._account.reserve(order.order_id, cost)

        if not result.success:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = result.reason
            return order

        order.status = OrderStatus.RESERVED

        # Simulate network + exchange latency
        time.sleep(self._fill_sim.fill_delay_ms / 1000.0)

        fill_price = self._fill_sim.simulate_fill(order)
        actual_cost = (order.quantity * fill_price).quantize(Decimal("0.01"))

        slippage_bps = abs(fill_price - order.limit_price) / order.limit_price * 10000
        order.slippage_bps = slippage_bps.quantize(Decimal("0.01"))

        self._account.confirm(
            order_id=order.order_id,
            actual_cost=actual_cost,
            symbol=order.symbol,
            quantity=order.quantity,
            fill_price=fill_price,
            side="long" if order.side == OrderSide.BUY else "short",
        )

        order.fill_price = fill_price
        order.status = OrderStatus.FILLED
        order.filled_ns = time.perf_counter_ns()

        latency_ms = (order.filled_ns - order.submitted_ns) / 1_000_000
        self._fill_queue.put_nowait(order)
        return order

    def cancel(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if not order or order.status != OrderStatus.RESERVED:
            return False
        self._account.release(order_id)
        order.status = OrderStatus.CANCELLED
        return True

    def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    def order_log(self) -> list[Order]:
        return list(self._orders.values())
