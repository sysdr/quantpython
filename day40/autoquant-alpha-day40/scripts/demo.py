#!/usr/bin/env python3
"""
Day 40 Demo — submit a paper order and watch the lifecycle unfold.

With credentials: submits a real Alpaca paper market order + streams fills.
Without credentials: runs an offline simulation of 5 orders with partial fills.

Usage:
    ALPACA_KEY=<key> ALPACA_SECRET=<secret> python scripts/demo.py
    python scripts/demo.py   # offline simulation
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.order_lifecycle import FillEvent, OrderLifecycle
from src.tracking.lifecycle_tracker import LifecycleTracker
from src.dashboard.cli_dashboard import LiveDashboard
from src.models.order_lifecycle import OrderState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)-8s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("demo")

def _load_dotenv_if_present(dotenv_path: Path = Path(".env")) -> None:
    """
    Minimal .env loader (no external deps).
    Loads KEY=VALUE pairs into os.environ if not already set.
    """
    try:
        if not dotenv_path.exists():
            return
        for raw in dotenv_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        # If .env is malformed, fall back to existing env vars.
        return


_load_dotenv_if_present()

# Support both this project's naming and Alpaca's common env var naming.
API_KEY = (
    os.getenv("ALPACA_KEY")
    or os.getenv("APCA_API_KEY_ID")
    or os.getenv("ALPACA_API_KEY")
    or ""
)
API_SECRET = (
    os.getenv("ALPACA_SECRET")
    or os.getenv("APCA_API_SECRET_KEY")
    or os.getenv("ALPACA_API_SECRET")
    or ""
)
LOG_PATH   = Path("data/lifecycle_log.jsonl")


async def log_to_file(lc: OrderLifecycle) -> None:
    """Callback: append terminal lifecycle records to JSONL log."""
    if lc.is_terminal:
        LOG_PATH.parent.mkdir(exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(lc.to_dict()) + "\n")
        log.info("Logged terminal order %s → %s", lc.order_id[-12:], LOG_PATH)


async def simulate_fills(tracker: LifecycleTracker) -> None:
    """Offline simulation of 5 orders with realistic partial-fill behaviour."""
    symbols = ["AAPL", "SPY", "MSFT", "NVDA", "TSLA"]
    base_prices = {"AAPL": 182.0, "SPY": 510.0, "MSFT": 415.0, "NVDA": 875.0, "TSLA": 198.0}

    for i, sym in enumerate(symbols):
        oid = f"SIM-{uuid.uuid4().hex[:10].upper()}"
        qty = float(random.choice([10, 25, 50, 100]))
        lc = OrderLifecycle(
            order_id=oid, symbol=sym, qty=qty,
            side=random.choice(["buy", "sell"]),
            order_type="limit",
            limit_price=round(base_prices[sym] * random.uniform(0.998, 1.002), 2),
        )
        lc.mark_submitted()
        await tracker.register_order(lc)

        # ACCEPTED after ~20ms broker latency
        await asyncio.sleep(random.uniform(0.015, 0.045))
        lc.mark_accepted(
            datetime.now(timezone.utc) - timedelta(milliseconds=random.uniform(15, 40))
        )

        # 1–3 partial fills
        n_fills = random.randint(1, 3)
        fill_qty = round(qty / n_fills, 4)
        for j in range(n_fills):
            await asyncio.sleep(random.uniform(0.05, 0.25))
            last = (j == n_fills - 1)
            fq = round(qty - lc.filled_qty, 4) if last else fill_qty
            broker_ts   = datetime.now(timezone.utc)
            local_ts    = broker_ts + timedelta(milliseconds=random.uniform(1.5, 12.0))
            fill_price  = base_prices[sym] * random.uniform(0.9995, 1.0005)
            await tracker.on_fill_event(
                oid,
                FillEvent(
                    fill_id=str(uuid.uuid4()),
                    qty=fq,
                    price=round(fill_price, 4),
                    broker_timestamp=broker_ts,
                    local_receipt_at=local_ts,
                ),
            )

        log.info("Simulated order %s %s %s x %.0f complete", sym, lc.side, oid[-10:], qty)

    log.info("Simulation complete — %d orders tracked", tracker.stats["total_tracked"])


async def live_run(tracker: LifecycleTracker) -> None:
    """Submit a real paper order and listen for fill events via WebSocket."""
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest
    from src.stream.fill_handler import FillStreamHandler

    client = TradingClient(API_KEY, API_SECRET, paper=True)
    req = MarketOrderRequest(
        symbol="AAPL", qty=1,
        side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
    )
    order = client.submit_order(req)
    log.info("Paper order submitted: id=%s", order.id)

    lc = OrderLifecycle(
        order_id=str(order.id), symbol="AAPL",
        qty=1, side="buy", order_type="market",
    )
    lc.mark_submitted()
    await tracker.register_order(lc)

    handler = FillStreamHandler(tracker, API_KEY, API_SECRET, paper=True)
    await handler.run()


async def seed_mock_orders(tracker: LifecycleTracker, target: int = 5) -> None:
    """
    Seed the tracker with a handful of realistic mock orders so the dashboard
    isn't empty while waiting on live broker events.
    """
    if tracker.stats["total_tracked"] >= target:
        return

    now = datetime.now(timezone.utc)
    mocks: list[OrderLifecycle] = [
        # pending_submit (no fills)
        OrderLifecycle(order_id=f"MOCK-{uuid.uuid4().hex[:8].upper()}", symbol="AAPL", qty=10, side="buy", order_type="market"),
        # accepted (no fills yet)
        OrderLifecycle(order_id=f"MOCK-{uuid.uuid4().hex[:8].upper()}", symbol="MSFT", qty=5, side="sell", order_type="limit", limit_price=415.20),
        # partially_filled (1 fill)
        OrderLifecycle(order_id=f"MOCK-{uuid.uuid4().hex[:8].upper()}", symbol="GOOGL", qty=8, side="buy", order_type="limit", limit_price=152.35),
        # filled (1 fill)
        OrderLifecycle(order_id=f"MOCK-{uuid.uuid4().hex[:8].upper()}", symbol="TSLA", qty=3, side="sell", order_type="market"),
        # filled (2 fills)
        OrderLifecycle(order_id=f"MOCK-{uuid.uuid4().hex[:8].upper()}", symbol="AMZN", qty=2, side="buy", order_type="limit", limit_price=189.10),
        # cancelled
        OrderLifecycle(order_id=f"MOCK-{uuid.uuid4().hex[:8].upper()}", symbol="NVDA", qty=1, side="sell", order_type="limit", limit_price=874.50),
        # rejected
        OrderLifecycle(order_id=f"MOCK-{uuid.uuid4().hex[:8].upper()}", symbol="META", qty=4, side="buy", order_type="market"),
    ]

    # 1) Register all
    for lc in mocks:
        lc.mark_submitted()
        lc.submitted_at = now - timedelta(milliseconds=random.uniform(80, 600))
        await tracker.register_order(lc)

    # 2) Accepted
    mocks[1].mark_accepted(now - timedelta(milliseconds=40))

    # 3) Partially filled (one partial)
    mocks[2].mark_accepted(now - timedelta(milliseconds=55))
    b = now - timedelta(milliseconds=25)
    await tracker.on_fill_event(
        mocks[2].order_id,
        FillEvent(
            fill_id=str(uuid.uuid4()),
            qty=3,
            price=152.41,
            broker_timestamp=b,
            local_receipt_at=b + timedelta(milliseconds=6),
        ),
    )

    # 4) Filled TSLA (single fill)
    mocks[3].mark_accepted(now - timedelta(milliseconds=120))
    b2 = now - timedelta(milliseconds=180)
    await tracker.on_fill_event(
        mocks[3].order_id,
        FillEvent(
            fill_id=str(uuid.uuid4()),
            qty=3,
            price=198.30,
            broker_timestamp=b2,
            local_receipt_at=b2 + timedelta(milliseconds=5),
        ),
    )

    # 5) Filled AMZN (two fills)
    mocks[4].mark_accepted(now - timedelta(milliseconds=140))
    b3 = now - timedelta(milliseconds=200)
    await tracker.on_fill_event(
        mocks[4].order_id,
        FillEvent(
            fill_id=str(uuid.uuid4()),
            qty=1,
            price=189.30,
            broker_timestamp=b3,
            local_receipt_at=b3 + timedelta(milliseconds=7),
        ),
    )
    b4 = now - timedelta(milliseconds=180)
    await tracker.on_fill_event(
        mocks[4].order_id,
        FillEvent(
            fill_id=str(uuid.uuid4()),
            qty=1,
            price=189.10,
            broker_timestamp=b4,
            local_receipt_at=b4 + timedelta(milliseconds=6),
        ),
    )

    # 6) Cancelled after acceptance
    mocks[5].mark_accepted(now - timedelta(milliseconds=70))
    await tracker.mark_cancelled(mocks[5].order_id)

    # 7) Rejected
    mocks[6].state = OrderState.REJECTED


async def main() -> None:
    tracker = LifecycleTracker(max_orders=1_000)
    tracker.register_callback(log_to_file)
    headless = os.getenv("AUTOQUANT_DEMO_NO_DASHBOARD", "").strip().lower() in (
        "1", "true", "yes",
    )

    if headless:
        log.info("AUTOQUANT_DEMO_NO_DASHBOARD set — skipping Rich live dashboard")
        if API_KEY and API_SECRET:
            await live_run(tracker)
        else:
            log.info("No credentials found — running offline simulation")
            await simulate_fills(tracker)
        return

    # Seed the dashboard with mock orders so it's informative immediately.
    await seed_mock_orders(tracker, target=5)

    dashboard = LiveDashboard(tracker, refresh_hz=4.0)
    if API_KEY and API_SECRET:
        await asyncio.gather(live_run(tracker), dashboard.run())
    else:
        log.info("No credentials found — running offline simulation")
        await asyncio.gather(simulate_fills(tracker), dashboard.run())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
