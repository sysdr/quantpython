"""
Rich CLI dashboard for real-time fill monitoring.
Displays live order table + rolling slippage stats.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
import time

if TYPE_CHECKING:
    from src.engine.fill_engine import FillResult
    from src.engine.slippage_tracker import SlippageTracker

console = Console()


def _slippage_color(bps: float) -> str:
    if bps < 0:
        return "green"
    elif bps < 3:
        return "yellow"
    elif bps < 8:
        return "orange3"
    return "red"


def render_fill_table(fills: list["FillResult"]) -> Table:
    table = Table(
        title="Fill Log",
        show_header=True,
        header_style="bold cyan",
        border_style="blue",
        min_width=90,
    )
    table.add_column("Order ID", style="dim", width=10)
    table.add_column("Symbol", justify="center")
    table.add_column("Side", justify="center")
    table.add_column("Qty", justify="right")
    table.add_column("Arrival Mid", justify="right")
    table.add_column("Fill Price", justify="right")
    table.add_column("Slippage (bps)", justify="right")

    for f in fills[-20:]:  # Show last 20
        slip_str = f"{f.slippage_bps:+.2f}"
        slip_color = _slippage_color(f.slippage_bps)
        table.add_row(
            f.order_id[:8],
            f.symbol,
            Text(f.side.upper(), style="green" if f.side == "buy" else "red"),
            str(f.qty),
            f"{f.arrival_mid:.4f}",
            f"{f.fill_price:.4f}",
            Text(slip_str, style=slip_color),
        )
    return table


def render_stats_panel(tracker: "SlippageTracker") -> Panel:
    s = tracker.stats()
    alarm = tracker.is_alarming()
    color = "red" if alarm else "green"

    lines = [
        f"[bold]Fills recorded:[/bold] {s.count}",
        f"[bold]Mean slippage:[/bold]  [{color}]{s.mean_bps:+.2f} bps[/{color}]",
        f"[bold]Std dev:[/bold]        {s.std_bps:.2f} bps",
        f"[bold]P50:[/bold]            {s.p50_bps:+.2f} bps",
        f"[bold]P95:[/bold]            [{_slippage_color(s.p95_bps)}]{s.p95_bps:+.2f} bps[/{_slippage_color(s.p95_bps)}]",
        f"[bold]P99:[/bold]            [{_slippage_color(s.p99_bps)}]{s.p99_bps:+.2f} bps[/{_slippage_color(s.p99_bps)}]",
        f"[bold]Worst:[/bold]          [{_slippage_color(s.worst_bps)}]{s.worst_bps:+.2f} bps[/{_slippage_color(s.worst_bps)}]",
    ]
    if alarm:
        lines.append("")
        lines.append("[bold red]⚠  SLIPPAGE ALARM: Mean > 5bps threshold[/bold red]")

    return Panel(
        "\n".join(lines),
        title="[bold]Rolling Slippage Stats (window=500)[/bold]",
        border_style=color,
        width=50,
    )


def print_fill_report(fills: list["FillResult"], tracker: "SlippageTracker") -> None:
    """Static one-shot report (no Live context needed)."""
    console.print()
    console.print(render_fill_table(fills))
    console.print()
    console.print(render_stats_panel(tracker))
    console.print()


class LiveDashboard:
    """Context manager for a live-updating Rich dashboard."""

    def __init__(self, refresh_rate: float = 4.0) -> None:
        self.fills: list["FillResult"] = []
        self.tracker: "SlippageTracker | None" = None
        self._refresh = refresh_rate

    def attach_tracker(self, tracker: "SlippageTracker") -> None:
        self.tracker = tracker

    def add_fill(self, fill: "FillResult") -> None:
        self.fills.append(fill)

    def _build_layout(self) -> Table:
        if self.tracker:
            return render_fill_table(self.fills)
        return Table(title="Waiting for fills...")

    def run_once(self) -> None:
        if self.tracker:
            print_fill_report(self.fills, self.tracker)
