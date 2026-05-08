#!/usr/bin/env python3.11
"""
Rich CLI Dashboard — ATR Slippage Demo
Simulates a synthetic tick stream and visualizes ATR + slippage in real-time.

Usage:
    python scripts/demo.py --symbol AAPL --ticks 300 --period 14
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from src.atr_engine import ATREngine, OHLCTick
from src.slippage_model import OrderSide, SlippageModel


console = Console()


def _generate_tick(prev_close: float, base_vol: float, regime: str) -> OHLCTick:
    """Synthetic OHLC tick generator with regime switching."""
    vol_mult = {"LOW": 0.4, "NORMAL": 1.0, "HIGH": 2.5}[regime]
    sigma = base_vol * vol_mult

    open_ = prev_close * (1 + random.gauss(0, sigma * 0.3))
    close = open_ * (1 + random.gauss(0, sigma))
    high = max(open_, close) * (1 + abs(random.gauss(0, sigma * 0.5)))
    low = min(open_, close) * (1 - abs(random.gauss(0, sigma * 0.5)))

    return OHLCTick(high=high, low=low, close=close)


def _build_table(
    history: list[tuple[int, float, float, str]],
    symbol: str,
) -> Table:
    table = Table(
        title=f"[bold cyan]{symbol}[/] — ATR Slippage Monitor",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
    )
    table.add_column("Tick#", justify="right", style="dim", width=7)
    table.add_column("Close", justify="right", style="white", width=10)
    table.add_column("ATR", justify="right", style="yellow", width=10)
    table.add_column("ATR/Price%", justify="right", style="magenta", width=12)
    table.add_column("Pred Slip (bps)", justify="right", width=16)
    table.add_column("Regime", justify="center", width=10)

    for tick_n, close, atr, regime in history[-20:]:
        ratio_pct = (atr / close) * 100.0
        model = SlippageModel()
        est = model.estimate("X", OrderSide.BUY, close, atr)
        bps_color = "green" if est.predicted_bps < 8 else ("yellow" if est.predicted_bps < 20 else "red")
        reg_color = "green" if regime == "LOW" else ("yellow" if regime == "NORMAL" else "red bold")
        table.add_row(
            str(tick_n),
            f"{close:.2f}",
            f"{atr:.4f}",
            f"{ratio_pct:.3f}%",
            f"[{bps_color}]{est.predicted_bps:.2f}[/]",
            f"[{reg_color}]{regime}[/]",
        )
    return table


def _build_header(symbol: str, latest_atr: float | None, regime: str) -> Panel:
    atr_str = f"{latest_atr:.4f}" if latest_atr else "warming up…"
    reg_color = {"LOW": "green", "NORMAL": "yellow", "HIGH": "red bold"}[regime]
    content = Text.assemble(
        ("ATR: ", "dim"),
        (atr_str + "  ", "yellow bold"),
        ("Regime: ", "dim"),
        (regime, reg_color),
        ("  |  Model: ", "dim"),
        ("BASE=3bps  SCALAR=0.35  MAX=50bps", "cyan"),
    )
    return Panel(content, title="[bold]AutoQuant-Alpha | Day 60[/]", border_style="blue")


def run_demo(symbol: str, n_ticks: int, period: int) -> None:
    engine = ATREngine(period=period)
    model = SlippageModel()
    history: list[tuple[int, float, float, str]] = []

    close = 150.0
    base_vol = 0.005
    regime = "NORMAL"
    regime_counter = 0

    with Live(console=console, refresh_per_second=10, screen=False) as live:
        for i in range(n_ticks):
            # Regime switching every ~80 ticks
            regime_counter += 1
            if regime_counter >= random.randint(60, 100):
                regime = random.choice(["LOW", "NORMAL", "NORMAL", "HIGH"])
                regime_counter = 0

            tick = _generate_tick(close, base_vol, regime)
            close = tick.close
            atr_val = engine.update(tick)

            if atr_val is not None:
                history.append((i + 1, close, atr_val, regime))

            table = _build_table(history, symbol)
            header = _build_header(symbol, atr_val, regime)
            live.update(Columns([Panel(table)]))
            time.sleep(0.05)

    console.print(
        f"\n[bold green]Demo complete.[/] {n_ticks} ticks processed. "
        f"Final ATR: {engine.value:.4f}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATR Slippage CLI Demo")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--ticks", type=int, default=300)
    parser.add_argument("--period", type=int, default=14)
    args = parser.parse_args()
    run_demo(args.symbol, args.ticks, args.period)
