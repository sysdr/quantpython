"""
scripts/demo.py
Interactive Rich dashboard demo with simulated margin events.
"""
from __future__ import annotations

import os
import queue
import random
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_root = str(ROOT)
if _root not in sys.path:
    sys.path.insert(0, _root)
os.chdir(ROOT)

from src.margin.account import AccountMode, MarginAccount
from src.margin.monitor import MarginMonitor
from src.broker.mock_broker import FillSimulator, MockBroker, Order, OrderSide
from src.dashboard.cli import run_dashboard


SYMBOLS = ["AAPL", "NVDA", "TSLA", "SPY", "MSFT"]


def simulate_market(account: MarginAccount, broker: MockBroker) -> None:
    """Background thread: submit random orders and update prices."""
    i = 0
    while True:
        time.sleep(random.uniform(1.5, 3.5))
        sym    = random.choice(SYMBOLS)
        price  = Decimal(str(random.uniform(100, 500))).quantize(Decimal("0.01"))
        qty    = Decimal(str(random.randint(1, 10)))
        side   = random.choice([OrderSide.BUY, OrderSide.BUY, OrderSide.SELL])
        order  = Order(symbol=sym, side=side, quantity=qty, limit_price=price)
        broker.submit(order)

        # Simulate price moves (some adverse)
        positions = account.positions
        new_prices = {
            s: (p.current_price * Decimal(str(random.uniform(0.97, 1.03)))).quantize(
                Decimal("0.01")
            )
            for s, p in positions.items()
        }
        if new_prices:
            account.update_prices(new_prices)
        i += 1


def main() -> None:
    account = MarginAccount(Decimal("100000.00"), mode=AccountMode.DAY_TRADE)
    broker  = MockBroker(account, FillSimulator(max_slippage_bps=Decimal("3")))
    eq      = queue.Queue()
    monitor = MarginMonitor(account, eq, interval_ms=500)

    monitor.start()
    market_thread = threading.Thread(target=simulate_market, args=(account, broker),
                                     daemon=True, name="MarketSimulator")
    market_thread.start()

    try:
        run_dashboard(account, eq, refresh_rate=4.0)
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        monitor.stop()


if __name__ == "__main__":
    main()
