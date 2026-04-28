#!/usr/bin/env python3
"""
AutoQuant-Alpha Day 50 Demo
Usage: python scripts/demo.py --symbol SPY --qty 10 --side buy --count 5
       python scripts/demo.py --sim   # synthetic quotes/fills when market is closed
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument(
    "--sim",
    action="store_true",
    help="Force simulation (synthetic quotes/fills; no Alpaca clock or orders)",
)
sys.path.insert(0, str(Path(__file__).parent.parent))
args_early, _ = _pre.parse_known_args()
if args_early.sim:
    os.environ["ALPACA_SIMULATION"] = "1"

from src.broker.alpaca_client import AlpacaPaperClient, MarketClosedError
from src.dashboard.cli_dashboard import print_fill_report
from src.engine.fill_engine import Side

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main(symbol: str, qty: int, side: str, count: int) -> None:
    client = AlpacaPaperClient()
    fills = []

    print(f"\n▶  Submitting {count}x {side.upper()} {qty} {symbol} orders...\n", flush=True)

    for i in range(count):
        fill = await client.submit_with_arrival_tracking(
            symbol=symbol,
            qty=Decimal(str(qty)),
            side=Side(side),
        )
        fills.append(fill)
        print(fill.summary())

    print_fill_report(fills, client.tracker)

    # Write CSV log
    import csv, time
    log_path = Path("data") / f"fills_{symbol}_{int(time.time())}.csv"
    log_path.parent.mkdir(exist_ok=True)
    with open(log_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "order_id", "symbol", "side", "qty",
                "arrival_mid", "fill_price", "slippage_bps",
            ],
        )
        writer.writeheader()
        for fl in fills:
            writer.writerow({
                "order_id": fl.order_id,
                "symbol": fl.symbol,
                "side": fl.side,
                "qty": str(fl.qty),
                "arrival_mid": str(fl.arrival_mid),
                "fill_price": str(fl.fill_price),
                "slippage_bps": f"{fl.slippage_bps:.4f}",
            })
    print(f"\n✓  Fill log saved: {log_path}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AutoQuant Day 50 Demo",
        parents=[_pre],
    )
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--qty", type=int, default=10)
    parser.add_argument("--side", default="buy", choices=["buy", "sell"])
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.symbol, args.qty, args.side, args.count))
    except MarketClosedError as e:
        print(f"\n{e}\n", file=sys.stderr)
        sys.exit(2)
