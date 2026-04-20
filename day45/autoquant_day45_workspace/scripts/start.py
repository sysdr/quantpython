"""scripts/start.py — Launch margin monitor + Alpaca reconciliation loop."""
from __future__ import annotations

import os
import queue
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_root = str(ROOT)
if _root not in sys.path:
    sys.path.insert(0, _root)
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.margin.account import AccountMode, MarginAccount
from src.margin.monitor import MarginMonitor, HealthTransition
from src.broker.reconciler import AlpacaReconciler, normalize_alpaca_env


def on_margin_call(evt: HealthTransition) -> None:
    print(f"⚠️  MARGIN CALL @ {time.strftime('%H:%M:%S')} "
          f"ratio={float(evt.margin_ratio)*100:.1f}% equity={evt.equity}")


def main():
    normalize_alpaca_env()
    if not os.environ.get("ALPACA_API_KEY") or not os.environ.get("ALPACA_SECRET_KEY"):
        print("Alpaca keys not set (ALPACA_API_KEY / ALPACA_SECRET_KEY).")
        print(f"Create {ROOT / '.env'} with ALPACA_API_KEY, ALPACA_SECRET_KEY, and ALPACA_BASE_URL, then re-run.")
        raise SystemExit(0)

    account = MarginAccount(Decimal("0"), mode=AccountMode.DAY_TRADE)
    eq = queue.Queue()
    monitor = MarginMonitor(account, eq, interval_ms=500, on_margin_call=on_margin_call)
    monitor.start()

    reconciler = AlpacaReconciler(account)
    print("Live margin monitoring started. Press Ctrl+C to stop.")
    print("Reconciling against Alpaca every 10s...")
    print("(Local model cash tracks Alpaca equity while you have no simulated positions.)\n")

    try:
        while True:
            result = reconciler.reconcile()
            status = "✅" if result.within_tolerance else "⚠️"
            print(f"{status} [{time.strftime('%H:%M:%S')}] "
                  f"Eq=${result.alpaca_equity:,.2f} Cash=${result.alpaca_cash:,.2f} | "
                  f"Alpaca DT=${result.alpaca_buying_power:,.2f} "
                  f"RegT=${result.alpaca_regt_buying_power:,.2f} "
                  f"Avail=${result.alpaca_available_buying_power:,.2f} | "
                  f"Local DT=${result.local_day_trade_bp:,.2f} "
                  f"ON=${result.local_overnight_bp:,.2f} "
                  f"Δ={result.bp_delta_pct:.4f}%")
            time.sleep(10)
    except KeyboardInterrupt:
        monitor.stop()
        print("\nStopped.")


if __name__ == "__main__":
    main()
