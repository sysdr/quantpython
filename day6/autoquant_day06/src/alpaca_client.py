"""
Thin wrapper around alpaca-py that surfaces HTTP status codes
as typed APIError exceptions for the RetryWrapper.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.common.exceptions import APIError as AlpacaAPIError

from retry_wrapper import APIError


def _make_client() -> TradingClient:
    return TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET_KEY"],
        paper=True,
    )


def submit_market_order(symbol: str, qty: int, side: str = "buy") -> dict[str, Any]:
    """
    Synchronous order submission — intended to be called via RetryWrapper.call().
    Returns a dict with order metadata including client_order_id.
    """
    client = _make_client()
    client_order_id = str(uuid.uuid4())

    order_data = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        client_order_id=client_order_id,
    )

    try:
        order = client.submit_order(order_data)
        return {
            "order_id": str(order.id),
            "client_order_id": client_order_id,
            "symbol": symbol,
            "qty": qty,
            "status": str(order.status),
        }
    except AlpacaAPIError as exc:
        # Normalize to our typed exception so RetryWrapper can inspect status_code
        status = getattr(exc, "status_code", 500)
        raise APIError(str(exc), status_code=int(status)) from exc


def check_duplicate_order(client_order_id: str) -> dict[str, Any] | None:
    """Query Alpaca to check if a client_order_id was already accepted."""
    client = _make_client()
    try:
        orders = client.get_orders()
        for order in orders:
            if str(order.client_order_id) == client_order_id:
                return {"order_id": str(order.id), "status": str(order.status)}
    except AlpacaAPIError:
        pass
    return None
