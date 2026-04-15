from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
import re
from io import StringIO

import pytest
from rich.console import Console

from src.dashboard.cli_dashboard import build_order_table, build_stats_panel
from src.models.order_lifecycle import FillEvent, OrderLifecycle
from src.tracking.lifecycle_tracker import LifecycleTracker

_ANSI = re.compile(chr(27) + r"\[[0-9;]*m")


def _render_rich(obj: object) -> str:
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=400, color_system="truecolor")
    console.print(obj)
    return _ANSI.sub("", buf.getvalue())


async def _filled_order_tracker() -> LifecycleTracker:
    tracker = LifecycleTracker(max_orders=100)
    oid = f"SIM-{uuid.uuid4().hex[:8]}"
    lc = OrderLifecycle(
        order_id=oid,
        symbol="SPY",
        qty=100,
        side="buy",
        order_type="limit",
        limit_price=500.0,
    )
    lc.mark_submitted()
    await tracker.register_order(lc)
    lc.mark_accepted(datetime.now(timezone.utc) - timedelta(milliseconds=25))
    b = datetime.now(timezone.utc)
    await tracker.on_fill_event(
        oid,
        FillEvent(
            fill_id=str(uuid.uuid4()),
            qty=100,
            price=510.12,
            broker_timestamp=b,
            local_receipt_at=b + timedelta(milliseconds=4),
        ),
    )
    return tracker


@pytest.mark.asyncio
async def test_dashboard_table_columns_populated() -> None:
    tracker = await _filled_order_tracker()
    lc = next(iter(tracker._orders.values()))
    assert lc.side == "buy"
    assert lc.state.value == "filled"
    assert lc.submission_latency_ms is not None
    assert lc.fill_latency_ms is not None
    assert lc.network_latency_ms is not None
    table = build_order_table(tracker)
    text = _render_rich(table)
    assert "Order Lifecycle Tracker" in text
    assert "SPY" in text
    assert "100.00" in text and "/10" in text
    assert "510" in text


@pytest.mark.asyncio
async def test_stats_panel_includes_counters() -> None:
    tracker = await _filled_order_tracker()
    panel = build_stats_panel(tracker)
    text = _render_rich(panel)
    assert "Tracked" in text
    assert "filled" in text.lower()
    assert "Orphan fills" in text
