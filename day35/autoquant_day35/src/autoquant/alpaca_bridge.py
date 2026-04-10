"""
AutoQuant-Alpha | Day 35
Alpaca Paper Trading bridge — submits orders and converts fills to TradeRecords.

No magic wrappers. Direct alpaca-py SDK usage with explicit error handling.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path
from typing import Literal

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus
from dotenv import load_dotenv

from .trade_record import TradeRecord


def load_alpaca_client() -> TradingClient:
    """Load credentials from .env and return a paper trading client."""
    env_path = Path(__file__).parents[2] / ".env"
    load_dotenv(env_path)

    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or api_key == "your_paper_api_key_here":
        raise EnvironmentError(
            "ALPACA_API_KEY not set. Create a .env in the project root with "
            "ALPACA_API_KEY and ALPACA_SECRET_KEY (paper trading)."
        )

    return TradingClient(api_key, secret_key, paper=True)


def load_stock_data_client() -> StockHistoricalDataClient:
    """Same credentials as trading; used for latest quote/trade pricing."""
    env_path = Path(__file__).parents[2] / ".env"
    load_dotenv(env_path)

    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or api_key == "your_paper_api_key_here":
        raise EnvironmentError(
            "ALPACA_API_KEY not set. Create a .env in the project root with "
            "ALPACA_API_KEY and ALPACA_SECRET_KEY (paper trading)."
        )

    return StockHistoricalDataClient(api_key, secret_key)


def _latest_trade_price(data_client: StockHistoricalDataClient, symbol: str) -> Decimal:
    tmap = data_client.get_stock_latest_trade(
        StockLatestTradeRequest(symbol_or_symbols=symbol)
    )
    return Decimal(str(tmap[symbol].price))


def aggressive_limit_price(
    data_client: StockHistoricalDataClient,
    symbol: str,
    side: Literal["buy", "sell"],
    cushion_bps: Decimal = Decimal("50"),
    max_quote_spread_bps: Decimal = Decimal("80"),
) -> Decimal:
    """
    Build a marketable limit for paper trading.

    Uses NBBO when the quoted spread is tight; otherwise falls back to the
    latest trade (delayed quotes often show huge synthetic spreads that never
    match the paper fill engine).
    """
    cushion = cushion_bps / Decimal("10000")

    qmap = data_client.get_stock_latest_quote(
        StockLatestQuoteRequest(symbol_or_symbols=symbol)
    )
    q = qmap[symbol]
    bid = Decimal(str(q.bid_price)) if q.bid_price is not None else Decimal("0")
    ask = Decimal(str(q.ask_price)) if q.ask_price is not None else Decimal("0")

    use_quote = (
        bid > 0
        and ask > 0
        and ask > bid
        and ((ask - bid) / ((ask + bid) / Decimal("2"))) * Decimal("10000") <= max_quote_spread_bps
    )

    if use_quote:
        if side == "buy":
            raw = ask * (Decimal("1") + cushion)
            return raw.quantize(Decimal("0.01"), rounding=ROUND_UP)
        raw = bid * (Decimal("1") - cushion)
        return raw.quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    last = _latest_trade_price(data_client, symbol)
    if side == "buy":
        raw = last * (Decimal("1") + cushion)
        return raw.quantize(Decimal("0.01"), rounding=ROUND_UP)
    raw = last * (Decimal("1") - cushion)
    return raw.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def submit_limit_order_and_record(
    client: TradingClient,
    symbol: str,
    side: Literal["buy", "sell"],
    qty: int,
    limit_price: Decimal,
    initial_pause_s: float = 0.08,
    poll_interval_s: float = 0.1,
    max_wait_s: float = 25.0,
) -> TradeRecord | None:
    """
    Submit a limit order to Alpaca Paper Trading and poll for fill.

    Returns a TradeRecord on successful fill, None if not filled within timeout.

    Parameters
    ----------
    client : TradingClient
        Authenticated Alpaca paper trading client.
    symbol : str
        Ticker symbol.
    side : "buy" | "sell"
        Order direction.
    qty : int
        Number of shares.
    limit_price : Decimal
        Order limit price. Use ``aggressive_limit_price`` for quick paper fills.
    initial_pause_s : float
        Short delay before the first status poll (order propagation).
    poll_interval_s : float
        Seconds between polls — keep small so fills are detected quickly.
    max_wait_s : float
        Wall-clock cap before cancel. Uses fast polling throughout (no long
        sleeps between checks).
    """
    alpaca_side = OrderSide.BUY if side == "buy" else OrderSide.SELL

    req = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=alpaca_side,
        time_in_force=TimeInForce.DAY,
        limit_price=float(limit_price),
    )

    submitted_at = datetime.now(tz=timezone.utc)

    try:
        order = client.submit_order(req)
    except Exception as exc:
        raise RuntimeError(f"Order submission failed: {exc}") from exc

    order_id = str(order.id)
    print(f"  Submitted order {order_id[:8]}… | symbol={symbol} side={side} qty={qty} limit={limit_price}")

    deadline = time.monotonic() + max_wait_s
    first_poll = True
    last_status: OrderStatus | None = None

    while time.monotonic() < deadline:
        time.sleep(initial_pause_s if first_poll else poll_interval_s)
        first_poll = False

        try:
            order = client.get_order_by_id(order_id)
        except Exception as exc:
            print(f"  get_order failed: {exc}")
            continue

        status = order.status
        if status != last_status:
            elapsed = max_wait_s - (deadline - time.monotonic())
            print(f"  [{elapsed:5.1f}s / {max_wait_s:.0f}s] status={status}")
            last_status = status

        if status == OrderStatus.FILLED:
            filled_at = order.filled_at or datetime.now(tz=timezone.utc)
            # Ensure timezone-aware
            if filled_at.tzinfo is None:
                filled_at = filled_at.replace(tzinfo=timezone.utc)

            fill_price = Decimal(str(order.filled_avg_price or limit_price))
            filled_qty = Decimal(str(order.filled_qty or qty))

            return TradeRecord(
                order_id=order_id,
                symbol=symbol,
                side=side,
                requested_qty=Decimal(str(qty)),
                filled_qty=filled_qty,
                limit_price=limit_price,
                fill_price=fill_price,
                submitted_at=submitted_at,
                filled_at=filled_at,
            )

        if status in (OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.REJECTED):
            print(f"  Order terminal status: {status}")
            return None

    # Cancel unfilled order to avoid leaking positions
    try:
        client.cancel_order_by_id(order_id)
        print(f"  Order {order_id[:8]}… cancelled after {max_wait_s:.0f}s without fill")
    except Exception:
        pass

    return None
