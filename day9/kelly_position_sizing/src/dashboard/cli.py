"""
dashboard/cli.py

Rich live dashboard for the Kelly sizing engine.
Run via: python scripts/demo.py

Displays per-symbol Kelly estimates, sizing output, and risk guard decisions
in a live-refreshing table. Simulated trade history is generated on startup
so this runs without requiring actual historical data.
"""
from __future__ import annotations

import asyncio
import math
import random
import time
from typing import Any

import numpy as np
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

# ---------------------------------------------------------------------------
# Synthetic trade history generator (no external data dependency)
# ---------------------------------------------------------------------------

def _synthetic_returns(
    n: int = 120,
    win_rate: float = 0.54,
    avg_win: float = 0.018,
    avg_loss: float = 0.012,
    seed: int | None = None,
) -> np.ndarray:
    """
    Generate plausible fractional trade returns for demo purposes.
    Real usage: replace with actual closed-trade P&L history.
    """
    rng = random.Random(seed)
    returns = []
    for _ in range(n):
        if rng.random() < win_rate:
            ret = rng.gauss(avg_win, avg_win * 0.3)
        else:
            ret = rng.gauss(-avg_loss, avg_loss * 0.3)
        returns.append(ret)
    return np.array(returns)


DEMO_UNIVERSE = {
    "AAPL":  {"win_rate": 0.54, "avg_win": 0.020, "avg_loss": 0.013, "price": 189.50},
    "NVDA":  {"win_rate": 0.56, "avg_win": 0.025, "avg_loss": 0.018, "price": 875.20},
    "SPY":   {"win_rate": 0.52, "avg_win": 0.012, "avg_loss": 0.010, "price": 524.00},
    "QQQ":   {"win_rate": 0.51, "avg_win": 0.014, "avg_loss": 0.013, "price": 450.00},
    "TSLA":  {"win_rate": 0.49, "avg_win": 0.030, "avg_loss": 0.022, "price": 245.00},
}

# ---------------------------------------------------------------------------
# Dashboard rendering
# ---------------------------------------------------------------------------

def _build_table(results: list[dict[str, Any]]) -> Table:
    t = Table(
        title="[bold cyan]AutoQuant-Alpha | Kelly Sizing Dashboard[/bold cyan]",
        box=box.ROUNDED,
        highlight=True,
        expand=True,
    )
    t.add_column("Symbol",       style="bold white",   justify="center", width=8)
    t.add_column("Win%",         style="cyan",         justify="right",  width=7)
    t.add_column("b-ratio",      style="cyan",         justify="right",  width=8)
    t.add_column("Kelly p5",     style="green",        justify="right",  width=10)
    t.add_column("Half-Kelly",   style="green bold",   justify="right",  width=11)
    t.add_column("f-final",      style="yellow",       justify="right",  width=9)
    t.add_column("Shares",       style="bold magenta", justify="right",  width=8)
    t.add_column("Est.Slip(bps)", style="orange3",     justify="right",  width=13)
    t.add_column("Status",       style="bold",         justify="center", width=14)

    for row in results:
        est = row["estimate"]
        sizing = row["sizing"]
        slip = row["slippage_bps"]

        win_pct = f"{est.raw_win_rate*100:.1f}%"
        b_ratio = f"{est.spread_adj_b_ratio:.3f}"
        kelly_p5 = f"{est.boot_kelly_p5:.4f}"
        half_k = f"{est.boot_kelly_p5 * 0.5:.4f}"
        f_final = f"{sizing.kelly_fraction:.4f}"
        shares = str(sizing.shares)
        slip_str = f"{slip:.1f}"

        if not est.has_edge:
            status = Text("NO EDGE", style="bold red")
        elif sizing.at_hard_cap:
            status = Text("CAPPED", style="bold yellow")
        elif sizing.shares == 0:
            status = Text("FLAT", style="dim")
        else:
            status = Text("SIZED ✓", style="bold green")

        t.add_row(est.symbol, win_pct, b_ratio, kelly_p5, half_k, f_final, shares, slip_str, status)

    return t


def _build_meta_panel(nav: float, elapsed: float, refresh_count: int) -> Panel:
    txt = (
        f"[bold white]NAV:[/bold white] ${nav:,.2f}  "
        f"[bold white]Bootstrap:[/bold white] 10,000 resamples  "
        f"[bold white]Spread:[/bold white] 5.0 bps  "
        f"[bold white]Refreshes:[/bold white] {refresh_count}  "
        f"[bold white]Cycle:[/bold white] {elapsed*1000:.0f} ms"
    )
    return Panel(txt, title="System State", border_style="blue")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run_dashboard(nav: float = 100_000.0, refresh_interval: float = 3.0) -> None:
    # Import here to avoid circular import at module level
    from src.kelly.estimator import KellyEstimator
    from src.kelly.sizer import PositionSizer

    estimator = KellyEstimator(n_bootstrap=10_000, spread_bps=5.0, seed=42)
    sizer = PositionSizer(kelly_fraction=0.5, max_position_fraction=0.15)

    # Pre-generate synthetic trade histories
    histories: dict[str, np.ndarray] = {
        sym: _synthetic_returns(120, **{k: v for k, v in props.items() if k != "price"}, seed=i)
        for i, (sym, props) in enumerate(DEMO_UNIVERSE.items())
    }

    refresh_count = 0

    with Live(console=console, refresh_per_second=4) as live:
        while True:
            t0 = time.perf_counter()

            results = []
            for sym, props in DEMO_UNIVERSE.items():
                rets = histories[sym]
                est = estimator.estimate(sym, rets)
                sizing = sizer.size(est, nav=nav, price=props["price"])

                # Estimate round-trip slippage (simulated)
                spread_bps = 5.0 + random.uniform(-1.0, 2.5)
                results.append({
                    "estimate": est,
                    "sizing": sizing,
                    "slippage_bps": spread_bps,
                })

            elapsed = time.perf_counter() - t0
            refresh_count += 1

            from rich.layout import Layout
            layout = Layout()
            layout.split_column(
                Layout(_build_meta_panel(nav, elapsed, refresh_count), size=3),
                Layout(_build_table(results)),
            )
            live.update(layout)

            await asyncio.sleep(refresh_interval)


if __name__ == "__main__":
    asyncio.run(run_dashboard())
