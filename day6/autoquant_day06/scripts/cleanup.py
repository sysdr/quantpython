"""Cancel all open Alpaca paper orders."""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alpaca.trading.client import TradingClient

def cleanup():
    client = TradingClient(
        api_key=os.environ.get("ALPACA_API_KEY", ""),
        secret_key=os.environ.get("ALPACA_SECRET_KEY", ""),
        paper=True,
    )
    try:
        client.cancel_orders()
        print("✓ All open paper orders cancelled.")
    except Exception as e:
        print(f"Cleanup skipped (no live connection): {e}")

if __name__ == "__main__":
    cleanup()
