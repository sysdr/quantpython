"""
dashboard/cli.py
Rich TUI dashboard showing live margin state.
"""
from __future__ import annotations

import queue
import time
from decimal import Decimal

from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..margin.account import MarginAccount, MarginHealth, MarginSnapshot
from ..margin.monitor import HealthTransition


_HEALTH_COLORS = {
    MarginHealth.HEALTHY:     "bright_green",
    MarginHealth.AT_RISK:     "yellow",
    MarginHealth.MARGIN_CALL: "bright_red",
    MarginHealth.LIQUIDATING: "red on white",
}


def _fmt_decimal(d: Decimal, prefix: str = "$") -> str:
    return f"{prefix}{d:,.2f}"


def _health_bar(ratio: Decimal) -> str:
    pct = float(ratio * 100)
    filled = int(pct / 5)
    bar = "█" * filled + "░" * (20 - filled)
    return f"[{'bright_green' if pct >= 35 else 'yellow' if pct >= 25 else 'bright_red'}]{bar}[/] {pct:.1f}%"


def build_account_panel(snap: MarginSnapshot) -> Panel:
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim", no_wrap=True)
    t.add_column(justify="right")

    color = _HEALTH_COLORS[snap.health]
    t.add_row("Health",       f"[bold {color}]{snap.health.value.upper()}[/]")
    t.add_row("Margin Ratio", _health_bar(snap.margin_ratio))
    t.add_row("Equity",       f"[bold]{_fmt_decimal(snap.equity)}[/]")
    t.add_row("Cash",         _fmt_decimal(snap.cash))
    t.add_row("Reserved",     _fmt_decimal(snap.reserved))
    t.add_row("Mode",         f"[cyan]{snap.mode.name}[/]")
    return Panel(t, title="[bold white]Account[/]", border_style="blue")


def build_bp_panel(snap: MarginSnapshot) -> Panel:
    bp = snap.buying_power
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim")
    t.add_column(justify="right")
    t.add_row("Day-Trade BP (4x)", f"[bold green]{_fmt_decimal(bp.day_trade_bp)}[/]")
    t.add_row("Overnight BP (2x)", _fmt_decimal(bp.overnight_bp))
    t.add_row("Cash BP (1x)",      _fmt_decimal(bp.cash_bp))
    return Panel(t, title="[bold white]Buying Power[/]", border_style="green")


def build_positions_panel(snap: MarginSnapshot, positions: dict) -> Panel:
    t = Table("Symbol", "Qty", "Avg Cost", "Mark", "PnL", show_header=True,
              header_style="bold white", border_style="dim")
    for sym, pos in positions.items():
        pnl = pos.unrealized_pnl
        color = "green" if pnl >= 0 else "red"
        t.add_row(
            sym,
            str(pos.quantity),
            _fmt_decimal(pos.avg_cost),
            _fmt_decimal(pos.current_price),
            f"[{color}]{_fmt_decimal(pnl)}[/]",
        )
    if not positions:
        t.add_row("[dim]no positions[/]", "", "", "", "")
    return Panel(t, title="[bold white]Positions[/]", border_style="yellow")


def build_events_panel(events: list[str]) -> Panel:
    body = "\n".join(events[-8:]) if events else "[dim]No events yet[/]"
    return Panel(body, title="[bold white]Margin Events[/]", border_style="magenta")


def run_dashboard(
    account: MarginAccount,
    event_queue: queue.Queue,
    refresh_rate: float = 2.0,
) -> None:
    console = Console()
    events: list[str] = []

    with Live(console=console, refresh_per_second=refresh_rate) as live:
        while True:
            # Drain event queue
            while True:
                try:
                    evt: HealthTransition = event_queue.get_nowait()
                    events.append(
                        f"[dim]{time.strftime('%H:%M:%S')}[/] "
                        f"{evt.from_health.value} → [bold]{evt.to_health.value}[/] "
                        f"ratio={float(evt.margin_ratio)*100:.1f}%"
                    )
                except queue.Empty:
                    break

            snap = account.snapshot()
            positions = account.positions

            layout = Layout()
            layout.split_column(
                Layout(
                    Columns([build_account_panel(snap), build_bp_panel(snap)]),
                    name="top", size=10
                ),
                Layout(build_positions_panel(snap, positions), name="mid", size=12),
                Layout(build_events_panel(events), name="bot"),
            )
            live.update(layout)
            time.sleep(1.0 / refresh_rate)
