"""
Demo: 20-order live session against Alpaca Paper Trading.
Requires ALPACA_API_KEY and ALPACA_SECRET_KEY in .env
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
from pathlib import Path

# Allow running from project root: python scripts/demo.py
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from alpaca.trading.client import TradingClient

from src.dashboard.cli_dashboard import start_dashboard
from src.models.order import OrderSide, TradeOrder
from src.queue_engine.dead_letter import DeadLetterQueue
from src.queue_engine.order_executor import OrderExecutor
from src.queue_engine.rate_limiter import TokenBucketRateLimiter
from src.queue_engine.trade_queue import TradeQueue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

log     = logging.getLogger("demo")
SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA"]


async def signal_feed(queue: TradeQueue, n: int = 20) -> None:
    """Simulates a signal engine emitting orders at stochastic intervals."""
    for i in range(n):
        order = TradeOrder(
            symbol   = random.choice(SYMBOLS),
            qty      = float(random.randint(1, 5)),
            side     = random.choice(list(OrderSide)),
            limit_px = round(random.uniform(100.0, 500.0), 2),
        )
        ok = await queue.enqueue(order)
        log.info(
            "SIGNAL | %s %s x%.0f @ $%.2f | %s",
            order.side.value.upper(), order.symbol, order.qty,
            order.limit_px, "QUEUED" if ok else "[red]DROPPED[/red]",
        )
        await asyncio.sleep(random.uniform(0.05, 0.25))


async def main() -> None:
    api_key = os.getenv("ALPACA_API_KEY", "")
    secret  = os.getenv("ALPACA_SECRET_KEY", "")
    if not api_key or not secret:
        print("ERROR: ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")
        sys.exit(1)

    client   = TradingClient(api_key, secret, paper=True)
    queue    = TradeQueue(maxsize=64)
    dlq      = DeadLetterQueue(Path("data/dlq"))
    rl       = TokenBucketRateLimiter(rate=3.0, capacity=10.0)
    executor = OrderExecutor(queue, dlq, client, rl)

    exec_task  = asyncio.create_task(executor.run())
    feed_task  = asyncio.create_task(signal_feed(queue, n=20))
    dash_task  = asyncio.create_task(
        start_dashboard(queue, dlq, lambda: executor.stats)
    )

    await feed_task
    # Drain remaining queue with timeout
    try:
        await asyncio.wait_for(queue._q.join(), timeout=30.0)
    except asyncio.TimeoutError:
        log.warning("Queue drain timeout (30s) — shutting down. Check API keys if orders are stuck.")

    exec_task.cancel()
    dash_task.cancel()
    await asyncio.gather(exec_task, dash_task, return_exceptions=True)

    stats = executor.stats
    print(f"\n{'='*50}")
    print("Demo Complete")
    print(f"{'='*50}")
    print(f"  Submitted : {stats['submitted']}")
    print(f"  Filled    : {stats['filled']}")
    print(f"  DLQ count : {len(dlq)}")
    print(f"{'='*50}")
    if len(dlq) == 0:
        print("\n✓ PASS: Zero DLQ entries.")
    else:
        print("\n  DLQ entries present (expected if API keys are placeholder). Run scripts/verify.py for details.")
    # Only fail when we expect success: real keys and still got DLQ
    if len(dlq) > 0 and api_key != "REPLACE_ME" and secret != "REPLACE_ME":
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
