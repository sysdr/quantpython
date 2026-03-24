"""
src/dashboard/visualizer.py
Rich live CLI dashboard for real-time Greeks visualization.
"""
from __future__ import annotations

import math
import time
import random
from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.console import Console
from rich import box


def _sparkline(values: list[float], width: int = 20) -> str:
    """Render a unicode sparkline for a series of values."""
    blocks = " ▁▂▃▄▅▆▇█"
    if not values:
        return " " * width
    mn, mx = min(values), max(values)
    rng = mx - mn or 1.0
    return "".join(blocks[min(8, int((v - mn) / rng * 8))] for v in values[-width:])


def make_greeks_table(positions_data: list[dict]) -> Table:
    t = Table(
        title="[bold cyan]Options Book — Live Greeks[/bold cyan]",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold magenta",
        min_width=90,
    )
    t.add_column("Symbol",   style="cyan",    width=12)
    t.add_column("Type",     style="white",   width=6)
    t.add_column("Strike",   style="white",   width=8,  justify="right")
    t.add_column("Qty",      style="white",   width=6,  justify="right")
    t.add_column("IV %",     style="yellow",  width=8,  justify="right")
    t.add_column("Δ Delta",  style="green",   width=10, justify="right")
    t.add_column("Γ Gamma",  style="blue",    width=10, justify="right")
    t.add_column("State",    style="white",   width=12)

    for p in positions_data:
        delta_str = f"{p['delta']:+.4f}"
        gamma_str = f"{p['gamma']:.6f}"
        state_style = {
            "ACTIVE": "green", "HEDGING": "yellow",
            "NEAR_EXPIRY": "red", "CLOSED": "dim",
        }.get(p["state"], "white")

        t.add_row(
            p["symbol"],
            p["type"],
            f"{p['strike']:.1f}",
            str(p["qty"]),
            f"{p['iv']*100:.1f}%",
            delta_str,
            gamma_str,
            f"[{state_style}]{p['state']}[/{state_style}]",
        )
    return t


def run_live_dashboard(duration_s: int = 60) -> None:
    """
    Simulates a live Greeks dashboard with synthetic market data.
    Shows vectorized BSM output updating in real-time.
    """
    from src.greeks.engine import bsm_delta_scalar, bsm_gamma_scalar
    from src.greeks.vol_surface import VolSurface

    console = Console()
    vol_surface = VolSurface.build_synthetic(spot=500.0)

    contracts = [
        {"symbol": "SPY", "K": 495, "T": 1/52,  "type": "put",  "qty": -10},
        {"symbol": "SPY", "K": 500, "T": 1/52,  "type": "call", "qty":  10},
        {"symbol": "SPY", "K": 505, "T": 1/12,  "type": "call", "qty":   5},
        {"symbol": "SPY", "K": 490, "T": 1/12,  "type": "put",  "qty":  -5},
        {"symbol": "SPY", "K": 510, "T": 3/12,  "type": "call", "qty":   3},
        {"symbol": "SPY", "K": 480, "T": 6/12,  "type": "put",  "qty":  -3},
    ]

    delta_history: list[float] = []
    gamma_history: list[float] = []
    spot_history:  list[float] = []
    spot = 500.0
    r = 0.053
    hedge_count = 0
    start = time.time()

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=6),
    )

    with Live(layout, console=console, refresh_per_second=4, screen=True):
        while time.time() - start < duration_s:
            spot += random.gauss(0, 0.5)   # simulate Brownian tick
            spot = max(460.0, min(540.0, spot))

            positions_data = []
            net_delta = 0.0
            net_gamma = 0.0

            for c in contracts:
                iv = vol_surface.get_iv(K=c["K"], S=spot, T=c["T"])
                d = bsm_delta_scalar(spot, c["K"], r, c["T"], iv, c["type"] == "call")
                g = bsm_gamma_scalar(spot, c["K"], r, c["T"], iv)
                pos_delta = d * c["qty"] * 100
                pos_gamma = g * c["qty"] * 100
                net_delta += pos_delta
                net_gamma += pos_gamma

                dte_days = c["T"] * 365
                state = "NEAR_EXPIRY" if dte_days < 5 else "ACTIVE"
                if abs(pos_delta) > 200:
                    state = "HEDGING"

                positions_data.append({
                    "symbol": c["symbol"],
                    "type":   c["type"].upper(),
                    "strike": c["K"],
                    "qty":    c["qty"],
                    "iv":     iv,
                    "delta":  pos_delta,
                    "gamma":  pos_gamma,
                    "state":  state,
                })

            delta_history.append(net_delta)
            gamma_history.append(net_gamma)
            spot_history.append(spot)

            if abs(net_delta) > 500:
                hedge_count += 1

            # Header
            elapsed = time.time() - start
            layout["header"].update(Panel(
                f"[bold]AutoQuant-Alpha[/bold] · Day 25 · Greeks Dashboard   "
                f"[dim]Spot:[/dim] [cyan]{spot:.2f}[/cyan]   "
                f"[dim]Elapsed:[/dim] {elapsed:.0f}s",
                style="bold white on dark_blue",
            ))

            # Main table
            layout["main"].update(make_greeks_table(positions_data))

            # Footer with sparklines and net metrics
            delta_color = "green" if net_delta >= 0 else "red"
            gamma_color = "green" if net_gamma >= 0 else "red"
            footer_text = Text()
            footer_text.append(f"\n  Net Δ: ", style="dim")
            footer_text.append(f"{net_delta:+.2f}  ", style=delta_color + " bold")
            footer_text.append(_sparkline(delta_history), style="cyan")
            footer_text.append(f"\n  Net Γ: ", style="dim")
            footer_text.append(f"{net_gamma:+.4f}  ", style=gamma_color + " bold")
            footer_text.append(_sparkline(gamma_history), style="blue")
            footer_text.append(f"\n  Hedge fires: {hedge_count}   Spot: ", style="dim")
            footer_text.append(_sparkline(spot_history), style="yellow")
            layout["footer"].update(Panel(footer_text, title="[dim]Portfolio Summary[/dim]"))

            time.sleep(0.25)

    console.print("\n[bold green]Dashboard session complete.[/bold green]")
    console.print(f"Total simulated hedge triggers: {hedge_count}")
