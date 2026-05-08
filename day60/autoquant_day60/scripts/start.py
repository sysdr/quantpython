#!/usr/bin/env python3.11
"""
Live Alpaca Paper Trading Execution with ATR Slippage.

Requires .env with ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL.

Usage:
    python scripts/start.py --symbol AAPL --quantity 1 --side buy
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.alpaca_executor import AlpacaSlippageExecutor
from src.slippage_model import OrderSide


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    args = parser.parse_args()

    missing = [k for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY") if not os.environ.get(k)]
    if missing:
        print("Missing required Alpaca env vars:", ", ".join(missing))
        print("Fix:")
        print("  cp .env.example .env  # then fill in your Alpaca paper keys")
        sys.exit(2)

    side = OrderSide.BUY if args.side == "buy" else OrderSide.SELL
    executor = AlpacaSlippageExecutor(
        symbol=args.symbol,
        quantity=args.quantity,
        side=side,
        log_path=Path("data/orders.jsonl"),
    )

    try:
        record = executor.execute()
        print("\n── Order Record ──────────────────────────────────")
        print(f"  Alpaca Order ID : {record.alpaca_order_id}")
        print(f"  Status          : {record.status}")
        print(f"  Mid Price       : {record.mid_price:.4f}")
        print(f"  ATR             : {record.atr:.4f}")
        print(f"  Predicted Slip  : {record.predicted_slippage_bps:.2f} bps")
        print(f"  Fill Price      : {record.fill_price}")
        print(f"  Realized Slip   : {record.realized_slippage_bps}")
        print(f"  Model Error     : {record.model_error_bps}")
        print(f"  Latency         : {record.latency_ms:.1f} ms")
    finally:
        executor.shutdown()


if __name__ == "__main__":
    main()
