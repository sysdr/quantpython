"""
dashboard.py
────────────
Rich CLI dashboard: live return distribution, NaN audit, CA flags.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from return_engine import ReturnEngine, ReturnTensor

console = Console()


def _make_return_table(tensor: ReturnTensor) -> Table:
    """Top-10 symbols by most recent return, colour-coded."""
    t = Table(
        title="[bold cyan]Latest Daily Log-Returns[/]",
        box=box.SIMPLE_HEAD,
        show_footer=False,
    )
    t.add_column("Symbol", style="bold white", width=8)
    t.add_column("Log-Ret %", justify="right", width=12)
    t.add_column("Arith-Ret %", justify="right", width=12)
    t.add_column("Valid?", justify="center", width=8)

    # Last available return per symbol
    arith = tensor.arithmetic_returns
    log = tensor.log_returns
    valid = tensor.validity_mask

    latest_idx = valid.shape[1] - 1
    for i, sym in enumerate(tensor.symbols):
        is_valid = bool(valid[i, latest_idx])
        lr = log[i, latest_idx]
        ar = arith[i, latest_idx]

        if not is_valid or np.isnan(lr):
            t.add_row(sym, "NaN", "NaN", "[red]✗[/]")
            continue

        lr_pct = lr * 100
        ar_pct = ar * 100
        colour = "green" if ar_pct >= 0 else "red"
        sign = "+" if ar_pct >= 0 else ""
        t.add_row(
            sym,
            f"[{colour}]{sign}{lr_pct:.4f}%[/]",
            f"[{colour}]{sign}{ar_pct:.4f}%[/]",
            "[green]✓[/]",
        )
    return t


def _make_nan_table(tensor: ReturnTensor) -> Table:
    t = Table(
        title="[bold yellow]NaN Rate by Symbol[/]",
        box=box.SIMPLE_HEAD,
    )
    t.add_column("Symbol", style="bold white", width=8)
    t.add_column("NaN Rate", justify="right", width=10)
    t.add_column("Status", justify="center", width=10)

    rates = tensor.nan_rate_per_symbol()
    for sym, rate in sorted(rates.items(), key=lambda x: -x[1]):
        colour = "green" if rate < 0.02 else ("yellow" if rate < 0.10 else "red")
        status = "OK" if rate < 0.02 else ("WARN" if rate < 0.10 else "CRITICAL")
        t.add_row(sym, f"[{colour}]{rate*100:.2f}%[/]", f"[{colour}]{status}[/]")
    return t


def _make_stats_panel(tensor: ReturnTensor) -> Panel:
    arith = tensor.arithmetic_returns
    valid_returns = arith[tensor.validity_mask]

    if len(valid_returns) == 0:
        return Panel("[red]No valid returns available[/]", title="Stats")

    mean = np.mean(valid_returns) * 100
    std = np.std(valid_returns) * 100
    skew = float(
        np.mean(((valid_returns - np.mean(valid_returns)) / np.std(valid_returns)) ** 3)
    )
    kurt = float(
        np.mean(((valid_returns - np.mean(valid_returns)) / np.std(valid_returns)) ** 4) - 3
    )
    coverage = tensor.coverage() * 100

    lines = [
        f"[cyan]Universe size:[/]     {len(tensor.symbols)} symbols",
        f"[cyan]Time periods:[/]      {tensor.validity_mask.shape[1]} days",
        f"[cyan]Coverage:[/]          {coverage:.2f}%",
        f"[cyan]Mean daily ret:[/]    {mean:+.4f}%",
        f"[cyan]Daily vol (1σ):[/]    {std:.4f}%",
        f"[cyan]Skewness:[/]          {skew:+.4f}",
        f"[cyan]Excess kurtosis:[/]   {kurt:+.4f}",
        f"[cyan]CA flags:[/]          {len(tensor.ca_flags)}",
    ]

    body = "\n".join(lines)
    return Panel(body, title="[bold]Universe Return Statistics[/]", border_style="blue")


def render_dashboard(tensor: ReturnTensor, refresh_interval: float = 0.0) -> None:
    """Render a one-shot Rich dashboard (or loop if refresh_interval > 0)."""
    while True:
        console.clear()
        console.rule("[bold blue]AutoQuant-Alpha · Day 10 · Return Engine Dashboard[/]")
        console.print()

        stats_panel = _make_stats_panel(tensor)
        ret_table = _make_return_table(tensor)
        nan_table = _make_nan_table(tensor)

        console.print(stats_panel)
        console.print()
        console.print(Columns([ret_table, nan_table], equal=True, expand=True))

        if tensor.ca_flags:
            console.print()
            console.rule("[bold red]Corporate Action Flags[/]")
            for flag in tensor.ca_flags:
                console.print(f"  [red]⚠  {flag}[/]")

        console.print()
        console.rule("[dim]Press Ctrl+C to exit[/]")

        if refresh_interval <= 0:
            break
        try:
            time.sleep(refresh_interval)
        except KeyboardInterrupt:
            break
