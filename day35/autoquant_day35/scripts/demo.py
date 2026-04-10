#!/usr/bin/env python3
"""
AutoQuant-Alpha | Day 35 — Demo Script

Connects to Alpaca Paper Trading, submits 3 limit orders,
and logs resulting TradeRecords via the dual-sink pipeline.

Usage:
    python scripts/demo.py

Prerequisites:
    - .env file with ALPACA_API_KEY and ALPACA_SECRET_KEY
    - pip install -r requirements.txt

Environment (optional):
    ALPACA_DEMO_MAX_WAIT_S   — seconds to poll each order (default 25; short poll interval)
    ALPACA_DEMO_FORCE_ORDERS — set to 1 to submit even when the equity session is closed
"""
from __future__ import annotations

import os
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from autoquant.trade_record import TradeRecord
from autoquant.logging_pipeline import build_logging_pipeline


def run_demo_with_alpaca() -> None:
    """Submit real orders to Alpaca Paper Trading and log TradeRecords."""
    from autoquant.alpaca_bridge import (
        aggressive_limit_price,
        load_alpaca_client,
        load_stock_data_client,
        submit_limit_order_and_record,
    )

    log_dir = Path(__file__).parents[1] / "data" / "logs"
    logger, listener = build_logging_pipeline(log_dir)

    try:
        print("\n[AutoQuant-Alpha | Day 35] Connecting to Alpaca Paper Trading...\n")
        client = load_alpaca_client()
        data_client = load_stock_data_client()

        clock = client.get_clock()
        if not clock.is_open and os.environ.get("ALPACA_DEMO_FORCE_ORDERS") != "1":
            print(
                "US equity session is closed — paper limit orders typically stay ACCEPTED "
                "until the next open (fills are unlikely now).\n"
                "Skipping live submits. Options: run during RTH; "
                "ALPACA_DEMO_FORCE_ORDERS=1 to submit anyway; or "
                "`python scripts/demo.py` for synthetic logs.\n"
            )
            print(f"Log file (unchanged this run): {log_dir / 'trades.jsonl'}\n")
            return

        max_wait = float(os.environ.get("ALPACA_DEMO_MAX_WAIT_S", "25"))

        orders = [
            ("AAPL", "buy", 1),
            ("MSFT", "buy", 1),
            ("SPY", "sell", 1),
        ]

        for symbol, side, qty in orders:
            limit_price = aggressive_limit_price(data_client, symbol, side)
            print(
                f"\nSubmitting {side.upper()} {qty} {symbol} @ {limit_price} "
                f"(marketable limit from tight NBBO or last trade)..."
            )
            record = submit_limit_order_and_record(
                client, symbol, side, qty, limit_price, max_wait_s=max_wait
            )
            if record:
                logger.info(record)
                print(f"  repr(): {record!r}")
            else:
                print(f"  Order for {symbol} not filled within timeout.")

            time.sleep(1.0)

        print(f"\nTrade logs written to: {log_dir / 'trades.jsonl'}")

    finally:
        listener.stop()
        print("\nLogging pipeline shut down cleanly.")


def run_demo_synthetic() -> None:
    """Demo using synthetic TradeRecords — no Alpaca credentials required."""
    import uuid
    from datetime import datetime, timezone, timedelta

    log_dir = Path(__file__).parents[1] / "data" / "logs"
    logger, listener = build_logging_pipeline(log_dir)

    print("\n[AutoQuant-Alpha | Day 35] Synthetic Demo (no Alpaca required)\n")

    scenarios = [
        ("AAPL", "buy",  "195.00", "195.02",  "100",  "100",  8.3),
        ("MSFT", "buy",  "415.00", "414.98",  "50",   "50",   12.1),
        ("SPY",  "sell", "545.00", "544.95",  "200",  "200",  6.7),
        ("NVDA", "buy",  "880.00", "880.15",  "25",   "20",   22.4),  # Partial fill
        ("TSLA", "buy",  "175.00", "175.00",  "75",   "75",   4.2),   # Zero slippage
    ]

    try:
        for symbol, side, limit, fill, req_qty, fill_qty, dur in scenarios:
            now = datetime.now(tz=timezone.utc)
            record = TradeRecord(
                order_id=str(uuid.uuid4()),
                symbol=symbol,
                side=side,  # type: ignore[arg-type]
                requested_qty=Decimal(req_qty),
                filled_qty=Decimal(fill_qty),
                limit_price=Decimal(limit),
                fill_price=Decimal(fill),
                submitted_at=now - timedelta(milliseconds=dur),
                filled_at=now,
            )
            logger.info(record)
            time.sleep(0.3)

        print(f"\nTrade logs written to: {log_dir / 'trades.jsonl'}")

    finally:
        listener.stop()
        print("\nLogging pipeline shut down cleanly.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "synthetic"
    if mode == "alpaca":
        run_demo_with_alpaca()
    else:
        run_demo_synthetic()
        print("\nTip: run with 'alpaca' argument to use real Alpaca Paper Trading:")
        print("     python scripts/demo.py alpaca")
