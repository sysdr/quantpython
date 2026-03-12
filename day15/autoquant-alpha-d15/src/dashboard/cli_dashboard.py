"""
Rich Live CLI Dashboard.
Visualizes queue depth, executor stats, and DLQ in real-time.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.queue_engine.dead_letter import DeadLetterQueue
from src.queue_engine.trade_queue import TradeQueue


def _build_queue_panel(q: TradeQueue, dlq: DeadLetterQueue, exec_stats: dict) -> Panel:
    s = q.stats()
    fill_rate = (
        exec_stats.get("filled", 0) / max(exec_stats.get("submitted", 1), 1) * 100
    )

    g = Table.grid(padding=(0, 2))
    g.add_column(style="bold cyan", justify="right", min_width=20)
    g.add_column(style="white", min_width=12)

    def row(label: str, value: str) -> None:
        g.add_row(label, value)

    row("Queue Depth",     f"[yellow]{s.depth:>6}[/yellow] / {q.maxsize}")
    row("Enqueued Total",  f"{s.enqueued:>6,}")
    row("Dequeued Total",  f"{s.dequeued:>6,}")
    row("CB Drops",        f"[red]{s.dropped:>6}[/red]")
    row("─" * 18,          "─" * 10)
    row("Submitted",       f"{exec_stats.get('submitted', 0):>6,}")
    row("Filled",          f"[green]{exec_stats.get('filled', 0):>6,}[/green]")
    row("Fill Rate",       f"[green]{fill_rate:>5.1f}%[/green]")
    row("DLQ / Rejected",  f"[red]{exec_stats.get('rejected', 0):>6}[/red]")

    return Panel(g, title="[bold blue]Trade Queue Monitor[/bold blue]", border_style="blue")


def _build_dlq_panel(dlq: DeadLetterQueue) -> Panel:
    tbl = Table(show_header=True, header_style="bold red", show_lines=False)
    tbl.add_column("ID",     width=10, style="dim")
    tbl.add_column("Symbol", width=8)
    tbl.add_column("Side",   width=6)
    tbl.add_column("Retry",  width=6, justify="right")
    tbl.add_column("Error",  width=45, no_wrap=True)

    for o in dlq.recent(6):
        tbl.add_row(
            o.order_id[:8],
            o.symbol,
            o.side.value,
            str(o.retries),
            (o.error or "")[:45],
        )

    title = f"[bold red]Dead Letter Queue — {len(dlq)} total[/bold red]"
    return Panel(tbl, title=title, border_style="red")


async def start_dashboard(
    queue:         TradeQueue,
    dlq:           DeadLetterQueue,
    exec_stats_fn: Callable[[], dict],
    refresh_hz:    float = 4.0,
) -> None:
    """Run Live dashboard until CancelledError."""
    console = Console()
    layout  = Layout()
    layout.split_column(
        Layout(name="queue", size=16),
        Layout(name="dlq"),
    )

    with Live(layout, console=console, refresh_per_second=refresh_hz):
        try:
            while True:
                layout["queue"].update(_build_queue_panel(queue, dlq, exec_stats_fn()))
                layout["dlq"].update(_build_dlq_panel(dlq))
                await asyncio.sleep(1.0 / refresh_hz)
        except asyncio.CancelledError:
            pass
