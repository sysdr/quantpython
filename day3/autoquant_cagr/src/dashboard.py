"""
Rich CLI dashboard: displays live CAGR term structure as a yield-curve-style table.
"""
from __future__ import annotations

import time
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich import box

from .cagr import CAGRSurface
from .config import TENOR_ORDER

console = Console()


def _color_cagr(value: float) -> Text:
    if not np.isfinite(value):
        return Text("  N/A ", style="dim")
    pct = value * 100
    label = f"{pct:+7.2f}%"
    if pct >= 15:
        return Text(label, style="bold green")
    elif pct >= 0:
        return Text(label, style="green")
    elif pct >= -10:
        return Text(label, style="yellow")
    else:
        return Text(label, style="bold red")


def render_surface_table(surfaces: list[CAGRSurface]) -> Table:
    table = Table(
        title="[bold cyan]CAGR Term Structure[/] — Return Yield Curve",
        box=box.SIMPLE_HEAVY,
        header_style="bold white on #1a1a2e",
        show_lines=True,
    )
    table.add_column("Symbol", style="bold cyan", width=10)
    for tenor in TENOR_ORDER:
        table.add_column(tenor, justify="right", width=10)
    table.add_column("NaN%", justify="right", style="dim", width=7)
    table.add_column("Inversions", style="yellow", width=14)

    for surf in surfaces:
        row: list[str | Text] = [surf.symbol]
        for tenor in TENOR_ORDER:
            v = surf.cagr_by_tenor.get(tenor, float("nan"))
            row.append(_color_cagr(v))
        row.append(f"{surf.nan_ratio * 100:.2f}%")
        inv = surf.detect_inversions(threshold_bps=500)
        row.append(str(len(inv)) + " ⚠" if inv else "—")
        table.add_row(*row)

    return table


def run_live_dashboard(
    surfaces: list[CAGRSurface],
    refresh_seconds: float = 2.0,
    iterations: int = 10,
) -> None:
    """Render the CAGR surface in a live-updating Rich panel."""
    with Live(console=console, refresh_per_second=4) as live:
        for _ in range(iterations):
            table = render_surface_table(surfaces)
            panel = Panel(
                table,
                title="[bold]AutoQuant-Alpha[/] | Day 3: CAGR Module",
                subtitle=f"252-day convention | {len(surfaces)} symbol(s)",
                border_style="blue",
            )
            live.update(panel)
            time.sleep(refresh_seconds)
