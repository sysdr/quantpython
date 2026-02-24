"""
Rich CLI Dashboard: Live bond pricing visualizer.
Shows DV01 sweep across YTM range with real-time pricing table.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich import box

from .bond_pricer import BondSpec, BondPricer
from .day_count import DayCount

console = Console()
pricer = BondPricer()

# ── Sample bonds for the dashboard ──────────────────────────────────────────
SAMPLE_BONDS: list[tuple[str, BondSpec, float]] = [
    (
        "UST 2Y",
        BondSpec(
            face_value=100.0,
            coupon_rate=0.0475,
            maturity_date=date.today() + timedelta(days=730),
            issue_date=date.today() - timedelta(days=30),
            frequency=2,
            day_count=DayCount.ACT_ACT_ISDA,
            cusip="912828XX1",
        ),
        0.048,  # current market YTM
    ),
    (
        "UST 10Y",
        BondSpec(
            face_value=100.0,
            coupon_rate=0.0425,
            maturity_date=date.today() + timedelta(days=3650),
            issue_date=date.today() - timedelta(days=90),
            frequency=2,
            day_count=DayCount.ACT_ACT_ISDA,
            cusip="912828YY2",
        ),
        0.044,
    ),
    (
        "UST 30Y",
        BondSpec(
            face_value=100.0,
            coupon_rate=0.0450,
            maturity_date=date.today() + timedelta(days=10950),
            issue_date=date.today() - timedelta(days=60),
            frequency=2,
            day_count=DayCount.ACT_ACT_ISDA,
            cusip="912810ZZ3",
        ),
        0.046,
    ),
]


def make_pricing_table(tick: int) -> Table:
    """Main pricing table — updates each tick with slightly varying YTMs."""
    table = Table(
        title=f"[bold cyan]Bond Pricer — Tick {tick:04d}[/bold cyan]",
        box=box.ROUNDED,
        border_style="cyan",
        show_lines=True,
    )
    table.add_column("Bond", style="bold white", width=10)
    table.add_column("YTM", justify="right", style="yellow")
    table.add_column("Clean Price", justify="right", style="green")
    table.add_column("Dirty Price", justify="right", style="green")
    table.add_column("Accrued", justify="right", style="blue")
    table.add_column("Mod. Dur", justify="right", style="magenta")
    table.add_column("DV01", justify="right", style="red")

    # Simulate minor YTM drift
    noise = np.random.normal(0, 0.0005)

    for label, spec, base_ytm in SAMPLE_BONDS:
        ytm = base_ytm + noise
        result = pricer.price(spec, ytm)
        table.add_row(
            label,
            f"{ytm:.4%}",
            f"{result.clean:>9.4f}",
            f"{result.dirty:>9.4f}",
            f"{result.accrued:>7.4f}",
            f"{result.modified_dur:>6.3f}",
            f"${result.dv01_per_face:>6.4f}",
        )

    return table


def make_dv01_bar(ytm_base: float, spec: BondSpec) -> Panel:
    """ASCII bar chart of DV01 sensitivity across YTM range."""
    ytms = np.linspace(ytm_base - 0.02, ytm_base + 0.02, 21)
    dv01s = []
    for y in ytms:
        r = pricer.price(spec, y)
        dv01s.append(r.dv01_per_face)

    max_dv01 = max(dv01s)
    bar_width = 30
    lines: list[str] = []
    for y, d in zip(ytms, dv01s):
        filled = int((d / max_dv01) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        color = "green" if y < ytm_base else "red"
        lines.append(f"[{color}]{y:.2%}[/{color}] [{color}]{bar}[/{color}] ${d:.4f}")

    content = "\n".join(lines)
    return Panel(content, title="[bold]DV01 Sensitivity — 10Y UST[/bold]", border_style="blue")


def run_dashboard(duration_seconds: int = 30) -> None:
    """Run the live dashboard for N seconds."""
    layout = Layout()
    layout.split_column(
        Layout(name="table", ratio=2),
        Layout(name="dv01", ratio=3),
    )

    _, spec_10y, ytm_10y = SAMPLE_BONDS[1]

    console.print(
        Panel(
            "[bold cyan]AutoQuant-Alpha Day 2: Bond Pricing Engine[/bold cyan]\n"
            "[dim]Press Ctrl+C to exit[/dim]",
            border_style="cyan",
        )
    )

    tick = 0
    with Live(layout, refresh_per_second=2, console=console) as live:
        start = time.time()
        while time.time() - start < duration_seconds:
            layout["table"].update(make_pricing_table(tick))
            layout["dv01"].update(make_dv01_bar(ytm_10y, spec_10y))
            time.sleep(0.5)
            tick += 1
