"""
AutoQuant-Alpha Day 6 — Live CLI Dashboard Demo
Streams retry/circuit state to terminal via Rich.
Usage: python scripts/demo.py
"""

from __future__ import annotations

import asyncio
import sys
import os
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
import structlog

from retry_wrapper import RetryWrapper, RetryConfig, APIError, CircuitState
from fault_injector import FaultInjector

structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)

console = Console()

ORDERS: list[dict] = []


def mock_order(symbol: str, qty: int, side: str = "buy") -> dict:
    """Mock order that succeeds — wrapped by FaultInjector in demo."""
    return {
        "order_id": f"MOCK-{random.randint(10000,99999)}",
        "client_order_id": f"cid-{random.randint(1000,9999)}",
        "symbol": symbol,
        "qty": qty,
        "status": "accepted",
    }


def build_table(orders: list[dict], wrapper: RetryWrapper) -> Table:
    stats = wrapper.stats()
    state_color = {
        "CLOSED": "green",
        "OPEN": "red",
        "HALF_OPEN": "yellow",
    }.get(stats["circuit_state"], "white")

    table = Table(
        title=f"[bold]AutoQuant-Alpha | Day 6 — Retry Wrapper Demo[/bold]",
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Order #", style="dim", width=8)
    table.add_column("Symbol")
    table.add_column("Qty", justify="right")
    table.add_column("Order ID")
    table.add_column("Result")

    for i, o in enumerate(orders, 1):
        table.add_row(
            str(i),
            o.get("symbol", "—"),
            str(o.get("qty", "—")),
            o.get("order_id", "—"),
            f"[green]{o['status']}[/green]" if o.get("status") == "accepted"
            else f"[red]{o.get('status', 'FAILED')}[/red]",
        )

    footer = (
        f"  Calls: {stats['call_count']}  "
        f"Retries: {stats['retry_count']}  "
        f"Retry Rate: {stats['retry_rate']:.1%}  "
        f"Circuit: [{state_color}]{stats['circuit_state']}[/{state_color}]  "
        f"Trips: {stats['circuit_trips']}"
    )
    table.caption = footer
    return table


async def run_demo() -> None:
    config = RetryConfig(
        max_attempts=5,
        base_delay=0.2,
        cap_delay=5.0,
        circuit_open_duration=8.0,
        failure_threshold=3,
    )
    wrapper = RetryWrapper(config)

    # Inject failures: 30% random rate + burst of 3 failures starting at call 5
    injected = FaultInjector(
        mock_order,
        failure_rate=0.25,
        status_code=429,
        burst_at=5,
        burst_duration=4,
    )

    symbols = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN",
               "META", "GOOGL", "SPY", "QQQ", "IWM"]

    with Live(console=console, refresh_per_second=4) as live:
        for i, symbol in enumerate(symbols):
            try:
                result = await wrapper.call(injected, symbol, 10)
                ORDERS.append(result)
            except Exception as exc:
                ORDERS.append({
                    "symbol": symbol,
                    "qty": 10,
                    "order_id": "—",
                    "status": f"FAILED: {type(exc).__name__}",
                })
            live.update(build_table(ORDERS, wrapper))
            await asyncio.sleep(0.4)

    console.print()
    console.print(Panel.fit(
        f"[bold green]Demo complete.[/bold green]\n"
        f"Final stats: {wrapper.stats()}",
        title="Summary",
    ))


if __name__ == "__main__":
    asyncio.run(run_demo())
