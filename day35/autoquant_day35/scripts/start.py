#!/usr/bin/env python3
"""
AutoQuant-Alpha | Day 35 — Live Trade Log Dashboard

Tails data/logs/trades.jsonl and renders a live Rich table.
Run AFTER demo.py has written some records, or alongside it.

Usage:
    python scripts/start.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from decimal import Decimal

from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich import box
from rich.text import Text


JSONL_PATH = Path(__file__).parents[1] / "data" / "logs" / "trades.jsonl"


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("type") == "TradeRecord":
                    records.append(obj)
            except json.JSONDecodeError:
                pass
    return records


def build_table(records: list[dict]) -> Table:
    table = Table(
        title="[bold cyan]AutoQuant-Alpha | Trade Log Dashboard[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white on dark_blue",
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Timestamp", style="dim", width=26)
    table.add_column("Order ID", width=14)
    table.add_column("Symbol", width=7)
    table.add_column("Side", width=6)
    table.add_column("Fill / Limit", width=18)
    table.add_column("Slippage", width=12, justify="right")
    table.add_column("P&L", width=10, justify="right")
    table.add_column("Fill%", width=8, justify="right")
    table.add_column("Latency", width=10, justify="right")

    for r in records[-30:]:  # Show last 30 records
        slip = Decimal(r.get("slippage_bps", "0"))
        pnl = Decimal(r.get("realized_pnl", "0"))
        fill_ratio = Decimal(r.get("fill_ratio", "0"))

        slip_style = "green" if slip <= 2 else ("yellow" if slip <= 5 else "red")
        pnl_style = "green" if pnl >= 0 else "red"
        fill_style = "green" if fill_ratio >= 95 else "yellow"
        side = r.get("side", "buy")
        side_style = "bold green" if side == "buy" else "bold red"

        short_id = r.get("order_id", "")[:8] + "…"
        ts = r.get("ts", "")[:19].replace("T", " ")

        table.add_row(
            ts,
            short_id,
            r.get("symbol", ""),
            Text(side.upper(), style=side_style),
            f"{r.get('fill_price','')} / {r.get('limit_price','')}",
            Text(f"{'+' if slip >= 0 else ''}{slip}bps", style=slip_style),
            Text(f"{'+' if pnl >= 0 else ''}{pnl}", style=pnl_style),
            Text(f"{fill_ratio}%", style=fill_style),
            f"{r.get('fill_duration_ms', '')}ms",
        )

    if not records:
        table.add_row(*["[dim]—[/dim]"] * 9)

    return table


def main() -> None:
    console = Console()
    console.print("\n[bold cyan]AutoQuant-Alpha | Day 35[/bold cyan] — Live Dashboard")
    console.print(f"Watching: [dim]{JSONL_PATH}[/dim]")
    console.print("Press [bold]Ctrl+C[/bold] to exit.\n")

    last_size = -1

    with Live(console=console, refresh_per_second=2, screen=False) as live:
        try:
            while True:
                current_size = JSONL_PATH.stat().st_size if JSONL_PATH.exists() else 0
                if current_size != last_size:
                    records = load_records(JSONL_PATH)
                    live.update(build_table(records))
                    last_size = current_size
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    console.print("\nDashboard closed.")


if __name__ == "__main__":
    main()
