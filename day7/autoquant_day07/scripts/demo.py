#!/usr/bin/env python3
"""
Demo: place a paper limit order and log the fill to the trade journal.
Watch: tail -f logs/trade_journal.jsonl | python -m json.tool
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.journal import FillRecord, LoggingSubsystem, log_fill
from src.alpaca_client import submit_limit_order

LOG_DIR = Path("logs")


def main() -> None:
    subsystem = LoggingSubsystem(LOG_DIR)
    trade_log, sys_log = subsystem.start()

    sys_log.info("Demo session starting")

    # Use a very wide limit so paper API fills immediately
    symbol = "SPY"
    qty = 1
    side = "buy"

    try:
        import yfinance as yf  # optional: get current price
        ticker = yf.Ticker(symbol)
        hist = ticker.fast_info
        last_price = float(hist.last_price)
    except Exception:
        last_price = 500.0  # Fallback if yfinance not installed

    # Set limit 0.5% above market to guarantee fill in paper trading
    limit_price = round(last_price * 1.005, 2)

    sys_log.info(f"Submitting {side.upper()} {qty} {symbol} @ {limit_price}")

    try:
        result = submit_limit_order(symbol, qty, side, limit_price)
        if result.order_id.startswith("MOCK-"):
            sys_log.info("Using mock mode (API credentials not configured)")
            print("\n[INFO] Running in MOCK mode - using simulated order fill")
            print("  To use real Alpaca API: Update .env with valid credentials")
    except Exception as e:
        sys_log.error(f"API call failed: {e}")
        print(f"\n[ERROR] API call failed: {e}")
        subsystem.stop()
        sys.exit(1)

    fill = FillRecord(
        order_id=result.order_id,
        symbol=result.symbol,
        side=result.side,
        qty=result.qty,
        limit_price=result.limit_price,
        fill_price=result.fill_price,
        submission_ts=result.submission_ts,
    )

    log_fill(trade_log, fill)

    sys_log.info(
        f"Fill logged | order_id={fill.order_id} "
        f"slippage={fill.slippage_bps:.2f}bps latency={fill.latency_ms:.1f}ms"
    )

    # Let listener thread drain
    time.sleep(0.5)
    subsystem.stop()

    print(f"\n[DEMO COMPLETE]")
    print(f"  Order ID   : {fill.order_id}")
    print(f"  Fill Price : {fill.fill_price}")
    print(f"  Slippage   : {fill.slippage_bps:.4f} bps")
    print(f"  Latency    : {fill.latency_ms:.1f} ms")
    print(f"\nCheck logs/trade_journal.jsonl for the structured record.")


if __name__ == "__main__":
    main()
