"""
AutoQuant-Alpha | src/dashboard.py
Rich CLI dashboard: live environment status and Alpaca account snapshot.

Usage:
    python src/dashboard.py
"""
from __future__ import annotations

import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from alpaca.trading.client import TradingClient
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.config import AlpacaConfig
from src.logger import get_logger

log = get_logger(__name__)
console = Console()


def _env_panel() -> Panel:
    """Render system/environment info panel."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan")
    table.add_column()

    table.add_row("Python", sys.version.split()[0])
    table.add_row("Platform", platform.platform(terse=True))
    table.add_row(
        "UTC Time",
        datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )
    table.add_row("Container", "Docker ✓" if _in_docker() else "Host")

    return Panel(table, title="[bold]Environment[/bold]", border_style="blue")


def _in_docker() -> bool:
    return Path("/.dockerenv").exists()


def _account_panel(config: AlpacaConfig) -> Panel:
    """Fetch and render Alpaca account snapshot."""
    t0 = time.monotonic()
    try:
        client = TradingClient(
            api_key=config.api_key,
            secret_key=config.secret_key,
            paper=True,
        )
        acct = client.get_account()
        latency_ms = round((time.monotonic() - t0) * 1000, 1)

        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold green")
        table.add_column()

        table.add_row("Account ID", str(acct.id)[:8] + "…")
        table.add_row("Status", str(acct.status))
        table.add_row("Equity", f"${float(acct.equity):,.2f}")          # type: ignore
        table.add_row("Cash", f"${float(acct.cash):,.2f}")              # type: ignore
        table.add_row("Buying Power", f"${float(acct.buying_power):,.2f}")  # type: ignore
        table.add_row("Latency", f"{latency_ms} ms")

        color = "green" if float(acct.equity) > 0 else "red"           # type: ignore
        return Panel(
            table,
            title=f"[bold]Alpaca Paper Trading[/bold] [{color}]● LIVE[/{color}]",
            border_style=color,
        )
    except Exception as exc:
        err_text = Text(f"Connection failed: {exc}", style="bold red")
        return Panel(err_text, title="[bold]Alpaca Paper Trading[/bold] [red]● DOWN[/red]", border_style="red")


def _status_bar(refresh_count: int) -> Text:
    t = Text()
    t.append("AutoQuant-Alpha ", style="bold white")
    t.append("Day 1: Dev Environment", style="dim")
    t.append(f"  │  Refresh #{refresh_count}", style="dim cyan")
    return t


def run_dashboard(config: AlpacaConfig, refresh_interval: float = 5.0) -> None:
    console.print(
        Panel(
            "[bold yellow]AutoQuant-Alpha — Day 1 Dashboard[/bold yellow]\n"
            "[dim]Press Ctrl+C to exit[/dim]",
            border_style="yellow",
        )
    )
    count = 0
    try:
        with Live(console=console, refresh_per_second=4) as live:
            while True:
                count += 1
                layout = Columns(
                    [_env_panel(), _account_panel(config)],
                    equal=True,
                )
                live.update(layout)
                time.sleep(refresh_interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard stopped.[/dim]")


def main() -> None:
    try:
        config = AlpacaConfig.from_env()
    except EnvironmentError as exc:
        console.print(f"[bold red]Config error:[/bold red] {exc}")
        sys.exit(1)
    run_dashboard(config)


if __name__ == "__main__":
    main()
