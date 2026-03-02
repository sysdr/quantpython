#!/usr/bin/env python3
"""
Rich CLI dashboard: live view of the trade journal and log queue depth.
Run in a separate terminal while demo.py is running.
Ctrl+C to exit.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

JOURNAL = Path("logs/trade_journal.jsonl")


def read_last_n(path: Path, n: int = 10) -> list[dict]:
    if not path.exists():
        return []
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    records = []
    for line in lines[-n:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


def build_table(records: list[dict]) -> Table:
    t = Table(title="Trade Journal (last 10 records)", expand=True, border_style="blue")
    t.add_column("Timestamp", style="cyan", no_wrap=True)
    t.add_column("Level", style="magenta")
    t.add_column("Msg", style="white")
    t.add_column("Symbol")
    t.add_column("Side")
    t.add_column("Slip (bps)", justify="right")
    t.add_column("Lat (ms)", justify="right")

    for r in records:
        slip = r.get("slippage_bps")
        slip_str = f"{slip:.4f}" if slip is not None else "—"
        slip_style = "red" if slip is not None and abs(slip) > 5 else "green"

        lat = r.get("latency_ms")
        lat_str = f"{lat:.1f}" if lat is not None else "—"

        t.add_row(
            r.get("ts", "")[:23],
            r.get("level", ""),
            r.get("msg", ""),
            r.get("symbol", "—"),
            r.get("side", "—"),
            Text(slip_str, style=slip_style),
            lat_str,
        )
    return t


def main() -> None:
    console = Console()
    with Live(console=console, refresh_per_second=2, screen=False) as live:
        while True:
            records = read_last_n(JOURNAL, 10)
            journal_size = JOURNAL.stat().st_size if JOURNAL.exists() else 0
            size_kb = journal_size / 1024

            header = Panel(
                f"[bold]AutoQuant-Alpha | Day 7 Dashboard[/bold]  "
                f"| Journal: [yellow]{size_kb:.1f} KB[/yellow]  "
                f"| Records: [cyan]{len(read_last_n(JOURNAL, 100000))}[/cyan]  "
                f"| Updated: [dim]{time.strftime('%H:%M:%S')}[/dim]",
                border_style="green",
            )

            table = build_table(records)
            from rich.columns import Columns
            live.update(
                Panel(
                    Columns([header, table], equal=False),
                    title="[bold green]Log Monitor[/bold green]",
                    border_style="dim",
                )
            )
            # Simpler layout: just stack vertically
            from rich.console import Group
            live.update(Group(header, table))
            time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
