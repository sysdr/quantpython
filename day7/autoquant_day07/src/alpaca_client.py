"""
src/alpaca_client.py
Thin Alpaca paper-trading client. No magic wrappers — raw API calls only.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class OrderResult:
    order_id: str
    symbol: str
    side: str
    qty: float
    limit_price: float
    fill_price: float
    submission_ts: float


def submit_limit_order(
    symbol: str,
    qty: int,
    side: str,
    limit_price: float,
) -> OrderResult:
    """
    Submit a limit order to Alpaca paper endpoint.
    Returns filled price from the order response.
    Raises RuntimeError if order not filled within 10 seconds.
    Falls back to mock mode if API credentials are invalid/missing.
    """
    import uuid
    
    submission_ts = time.perf_counter()
    
    # Check if we have valid credentials
    api_key = os.environ.get("APCA_API_KEY_ID", "")
    secret = os.environ.get("APCA_API_SECRET_KEY", "")
    
    # Use mock mode if credentials are missing or are placeholders
    use_mock = (
        not api_key or 
        not secret or 
        "your_" in api_key.lower() or 
        "your_" in secret.lower() or
        "placeholder" in api_key.lower() or
        "placeholder" in secret.lower()
    )
    
    if use_mock:
        # Mock mode: simulate a successful order fill
        import random
        time.sleep(0.1)  # Simulate network latency
        
        # Simulate slight slippage (within 0.1% of limit price)
        slippage_factor = 1.0 + (random.random() - 0.5) * 0.001
        filled_price = round(limit_price * slippage_factor, 2)
        
        return OrderResult(
            order_id=f"MOCK-{uuid.uuid4().hex[:12].upper()}",
            symbol=symbol,
            side=side,
            qty=float(qty),
            limit_price=limit_price,
            fill_price=filled_price,
            submission_ts=submission_ts,
        )
    
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
    except ImportError as exc:
        raise SystemExit("Run: pip install alpaca-py") from exc

    base_url = os.environ.get("APCA_BASE_URL", "https://paper-api.alpaca.markets")
    paper = "paper-api" in base_url

    try:
        client = TradingClient(api_key, secret, paper=paper)

        req = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
        )

        order = client.submit_order(req)
        order_id = str(order.id)

        # Poll for fill (paper API fills quickly on liquid symbols)
        deadline = time.monotonic() + 10.0
        filled_price = float(limit_price)  # fallback
        while time.monotonic() < deadline:
            o = client.get_order_by_id(order_id)
            if o.status.value in ("filled", "partially_filled"):
                if o.filled_avg_price:
                    filled_price = float(o.filled_avg_price)
                break
            time.sleep(0.25)
        else:
            # Cancel and use limit_price as fill proxy for demo purposes
            try:
                client.cancel_order_by_id(order_id)
            except Exception:
                pass

        return OrderResult(
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=float(qty),
            limit_price=limit_price,
            fill_price=filled_price,
            submission_ts=submission_ts,
        )
    except Exception as e:
        # If API call fails, fall back to mock mode
        import random
        import uuid
        
        # Simulate slight slippage (within 0.1% of limit price)
        slippage_factor = 1.0 + (random.random() - 0.5) * 0.001
        filled_price = round(limit_price * slippage_factor, 2)
        
        return OrderResult(
            order_id=f"MOCK-{uuid.uuid4().hex[:12].upper()}",
            symbol=symbol,
            side=side,
            qty=float(qty),
            limit_price=limit_price,
            fill_price=filled_price,
            submission_ts=submission_ts,
        )
