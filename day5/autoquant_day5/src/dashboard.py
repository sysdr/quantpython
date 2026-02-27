#!/usr/bin/env python3
"""
AutoQuant-Alpha Day 5 — Rich CLI Dashboard
Real-time margin monitor visualizer. Run alongside margin_monitor.py.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional
import httpx
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from dotenv import load_dotenv

load_dotenv()
console = Console()

LEVEL_STYLES = {
    "SAFE":        "bold green",
    "WARN":        "bold yellow",
    "CRITICAL":    "bold red",
    "MARGIN_CALL": "bold white on red",
    "LIQUIDATION": "bold white on dark_red",
}

THRESHOLDS = {
    "WARN":        0.90,
    "CRITICAL":    0.80,
    "MARGIN_CALL": 0.70,
    "LIQUIDATION": 0.60,
}


def compute_fsm_state(ratio: float) -> str:
    if ratio < 0.60: return "LIQUIDATION"
    if ratio < 0.70: return "MARGIN_CALL"
    if ratio < 0.80: return "CRITICAL"
    if ratio < 0.90: return "WARN"
    return "SAFE"


def build_gauge(ratio: float, width: int = 40) -> Text:
    """ASCII progress bar for equity ratio."""
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    state = compute_fsm_state(ratio)
    style = LEVEL_STYLES.get(state, "white")
    t = Text()
    t.append(f"[{bar}] {ratio*100:.2f}%", style=style)
    return t


def build_threshold_table() -> Table:
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    t.add_column("Level", style="bold")
    t.add_column("Enter Threshold", justify="right")
    t.add_column("Exit Threshold", justify="right")
    for name, enter in THRESHOLDS.items():
        exit_val = enter + 0.02
        style = LEVEL_STYLES.get(name, "white")
        t.add_row(f"[{style}]{name}[/{style}]", f"{enter:.0%}", f"{exit_val:.0%}")
    return t


async def fetch_account(api_key: str, secret: str) -> Optional[dict]:
    headers = {
        "APCA-API-KEY-ID":     api_key,
        "APCA-API-SECRET-KEY": secret,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://paper-api.alpaca.markets/v2/account",
                headers=headers,
                timeout=4.0,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        return None


async def run_dashboard(api_key: str, secret: str) -> None:
    history: list[tuple[float, str, str]] = []  # (ratio, state, timestamp)
    refresh_interval = 3.0

    with Live(console=console, refresh_per_second=2, screen=True) as live:
        while True:
            data = await fetch_account(api_key, secret)
            now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

            layout = Layout()
            layout.split_column(
                Layout(name="header", size=3),
                Layout(name="main"),
                Layout(name="footer", size=3),
            )
            layout["main"].split_row(
                Layout(name="left"),
                Layout(name="right"),
            )

            layout["header"].update(Panel(
                Text("⚡ AutoQuant-Alpha | Day 5 — Margin Monitor", justify="center", style="bold cyan"),
                box=box.DOUBLE,
            ))

            if data:
                equity       = Decimal(data.get("equity", "0"))
                last_equity  = Decimal(data.get("last_equity", "1"))
                buying_power = Decimal(data.get("buying_power", "0"))
                maint_margin = Decimal(data.get("maintenance_margin", "0"))
                portfolio    = Decimal(data.get("portfolio_value", "0"))

                ratio = float(equity / last_equity) if last_equity else 1.0
                state = compute_fsm_state(ratio)
                history.append((ratio, state, now_str))
                if len(history) > 20:
                    history.pop(0)

                style = LEVEL_STYLES.get(state, "white")

                account_table = Table(box=box.SIMPLE, show_header=False)
                account_table.add_column("Field",  style="dim", width=22)
                account_table.add_column("Value",  justify="right")
                account_table.add_row("Equity",             f"${equity:,.2f}")
                account_table.add_row("Last Equity",        f"${last_equity:,.2f}")
                account_table.add_row("Buying Power",       f"${buying_power:,.2f}")
                account_table.add_row("Maintenance Margin", f"${maint_margin:,.2f}")
                account_table.add_row("Portfolio Value",    f"${portfolio:,.2f}")

                layout["left"].update(Panel(
                    account_table,
                    title="[bold]Account State[/bold]",
                    border_style="cyan",
                ))

                right_content = Layout()
                right_content.split_column(
                    Layout(name="gauge", size=5),
                    Layout(name="state", size=5),
                    Layout(name="thresholds"),
                )

                gauge = build_gauge(ratio)
                right_content["gauge"].update(Panel(gauge, title="Equity Ratio", border_style="green"))
                right_content["state"].update(Panel(
                    Text(f"FSM State: {state}", style=style, justify="center"),
                    border_style=style.split()[-1] if "on" not in style else "red",
                ))
                right_content["thresholds"].update(Panel(
                    build_threshold_table(),
                    title="Hysteresis Thresholds",
                    border_style="blue",
                ))
                layout["right"].update(right_content)
            else:
                layout["left"].update(Panel("[yellow]Waiting for account data...[/yellow]"))
                layout["right"].update(Panel("[dim]Connecting to Alpaca...[/dim]"))

            # History table
            hist_table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
            hist_table.add_column("Time UTC", style="dim")
            hist_table.add_column("Ratio", justify="right")
            hist_table.add_column("State")
            for r, s, t in reversed(history[-5:]):
                st = LEVEL_STYLES.get(s, "white")
                hist_table.add_row(t, f"{r:.4f}", f"[{st}]{s}[/{st}]")

            layout["footer"].update(Panel(hist_table, title="Recent History", box=box.SIMPLE))
            live.update(layout)
            await asyncio.sleep(refresh_interval)


async def main() -> None:
    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret  = os.environ.get("ALPACA_SECRET_KEY", "")
    if not api_key or not secret:
        console.print("[red]ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env[/red]")
        sys.exit(1)
    await run_dashboard(api_key, secret)


if __name__ == "__main__":
    asyncio.run(main())
