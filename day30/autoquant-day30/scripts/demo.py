"""
Live Demo: Slippage-Aware Market Order
---------------------------------------
Submits one paper market order and displays a Rich live dashboard.

Usage:
    python scripts/demo.py --symbol AAPL --qty 5 --side buy
    python scripts/demo.py --symbol SPY  --qty 2 --side sell
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure src is importable when run from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich import box

load_dotenv()

from decimal import Decimal, ROUND_HALF_UP

from src.execution.market_order import build_engine, OrderRecord
from src.data.quote_feed import QuoteFeed
from src.utils.logger import AtomicTradeLogger
from alpaca.trading.enums import OrderSide


console = Console()


def _make_synthetic_quote_panel(symbol: str) -> Panel:
    bid = Decimal("150.00")
    ask = Decimal("150.05")
    mid = (bid + ask) / Decimal("2")
    spread_bps = (ask - bid) / mid * Decimal("10000")
    table = Table(box=box.SIMPLE_HEAVY, show_header=False)
    table.add_column("Key", style="cyan", width=20)
    table.add_column("Value", style="bright_white")
    table.add_row("Symbol", symbol)
    table.add_row("Bid", f"${bid}")
    table.add_row("Ask", f"${ask}")
    table.add_row("Mid", f"${mid}")
    table.add_row("Spread", f"{spread_bps:.2f} bps")
    table.add_row("Mode", "[dim]dry-run (no API)[/dim]")
    return Panel(table, title="[bold green]Live Quote[/bold green]", border_style="green")


def _synthetic_order_record(symbol: str, qty: int, side: str) -> OrderRecord:
    import uuid

    now = datetime.now(tz=timezone.utc)
    if side == "buy":
        expected = Decimal("150.05")
        fill = Decimal("150.08")
        raw_slip = (fill - expected) / expected * Decimal("10000")
    else:
        expected = Decimal("150.00")
        fill = Decimal("149.97")
        raw_slip = -(fill - expected) / expected * Decimal("10000")
    slip = raw_slip.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return OrderRecord(
        symbol=symbol,
        side=side,
        qty=qty,
        expected_price=expected,
        submitted_at=now,
        order_id=str(uuid.uuid4()),
        fill_price=fill,
        filled_at=now,
        slippage_bps=slip,
        status="FILLED",
    )


def _make_quote_panel(symbol: str) -> Panel:
    feed = QuoteFeed()
    try:
        q = feed.get_latest_quote(symbol)
        table = Table(box=box.SIMPLE_HEAVY, show_header=False)
        table.add_column("Key", style="cyan", width=20)
        table.add_column("Value", style="bright_white")
        table.add_row("Symbol", q.symbol)
        table.add_row("Bid", f"${q.bid_price}")
        table.add_row("Ask", f"${q.ask_price}")
        table.add_row("Mid", f"${q.mid_price}")
        table.add_row("Spread", f"{q.spread_bps:.2f} bps")
        table.add_row("Quote Age", f"{(datetime.now(tz=timezone.utc) - q.timestamp).total_seconds() * 1000:.0f} ms")
        return Panel(table, title="[bold green]Live Quote[/bold green]", border_style="green")
    except Exception as exc:
        return Panel(f"[red]Quote error: {exc}[/red]", title="Quote Feed")


def _make_record_panel(record: OrderRecord) -> Panel:
    table = Table(box=box.SIMPLE_HEAVY, show_header=False)
    table.add_column("Field", style="cyan", width=22)
    table.add_column("Value", style="bright_white")

    slip_color = (
        "green" if record.slippage_bps is not None and float(record.slippage_bps) < 3.0
        else "yellow" if record.slippage_bps is not None and float(record.slippage_bps) < 8.0
        else "red"
    )

    table.add_row("Order ID", str(record.order_id))
    table.add_row("Symbol", record.symbol)
    table.add_row("Side", record.side.upper())
    table.add_row("Qty", str(record.qty))
    table.add_row("Expected Price", f"${record.expected_price}")
    table.add_row("Fill Price", f"${record.fill_price}" if record.fill_price else "—")
    table.add_row(
        "Slippage",
        f"[{slip_color}]{record.slippage_bps:.2f} bps[/{slip_color}]"
        if record.slippage_bps is not None else "—",
    )
    table.add_row(
        "Net Slippage Cost",
        f"${record.net_slippage_cost}" if record.net_slippage_cost else "—",
    )
    table.add_row("Status", f"[green]{record.status}[/green]" if record.status == "FILLED" else f"[red]{record.status}[/red]")
    table.add_row("Fill Latency", (
        f"{(record.filled_at - record.submitted_at).total_seconds() * 1000:.0f} ms"
        if record.filled_at else "—"
    ))

    return Panel(table, title="[bold blue]Order Record[/bold blue]", border_style="blue")


async def main(symbol: str, qty: int, side: str, dry_run: bool) -> None:
    order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL

    title = "[bold]AutoQuant-Alpha · Day 30 · Slippage-Aware Market Order[/bold]"
    if dry_run:
        title += " [dim](dry-run)[/dim]"
    console.rule(title)

    with Live(console=console, refresh_per_second=4) as live:
        live.update(
            Panel(
                f"[yellow]Fetching quote for [bold]{symbol}[/bold]...[/yellow]",
                title="Status"
            )
        )
        await asyncio.sleep(0.5)

        quote_panel = (
            _make_synthetic_quote_panel(symbol)
            if dry_run
            else _make_quote_panel(symbol)
        )
        live.update(quote_panel)
        await asyncio.sleep(1.5)

        live.update(
            Panel(
                f"[yellow]Submitting [bold]{side.upper()} {qty} {symbol}[/bold] market order...[/yellow]",
                title="Status"
            )
        )
        await asyncio.sleep(0.3)

        if dry_run:
            record = _synthetic_order_record(symbol, qty, side)
            log_path = Path("data/trade_log.csv")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            AtomicTradeLogger(log_path).log(record)
            live.update(_make_record_panel(record))
        else:
            engine = build_engine(log_path="data/trade_log.csv")
            try:
                record = await engine.submit(symbol=symbol, side=order_side, qty=qty)
                live.update(_make_record_panel(record))
            except Exception as exc:
                live.update(Panel(f"[red bold]Error: {exc}[/red bold]", title="Order Failed"))
                raise

    console.print()
    console.print(f"[dim]Trade log appended → data/trade_log.csv[/dim]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutoQuant Day 30 Demo")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--qty", type=int, default=5)
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Offline UI smoke test: synthetic quote/order, append CSV (no Alpaca)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.symbol, args.qty, args.side, args.dry_run))
