"""
AutoQuant Day 4 — Rich CLI Dashboard
Demonstrates AssetRegistry with a live Alpaca paper trading connection.

Usage: python -m src.demo
"""
from __future__ import annotations

import os
import time
import random
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich import box

from src.asset_registry import AssetRegistry
from src.asset_metadata import AssetMetadata

console = Console()

DEMO_SYMBOLS = [
    "AAPL", "MSFT", "TSLA", "AMZN", "NVDA",
    "META", "GOOGL", "JPM", "SPY", "QQQ",
]

def _build_mock_metadata(symbol: str) -> AssetMetadata:
    """Build a plausible mock entry (used when Alpaca creds are absent)."""
    exchanges = ["NASDAQ", "NYSE", "ARCA"]
    return AssetMetadata(
        symbol=symbol,
        exchange=random.choice(exchanges),
        asset_class="us_equity",
        tradable=random.random() > 0.05,
        fractionable=random.random() > 0.3,
        min_order_size=1.0,
        price_increment=0.01,
        fetched_at=time.monotonic() - random.uniform(0, 3000),
        ttl_seconds=3600.0,
    )

def _make_table(registry: AssetRegistry, symbols: list[str]) -> Table:
    table = Table(
        title="[bold cyan]Asset Registry State[/bold cyan]",
        box=box.SIMPLE_HEAVY,
        show_lines=True,
    )
    table.add_column("Symbol", style="bold white", width=8)
    table.add_column("Exchange", width=10)
    table.add_column("Class", width=12)
    table.add_column("Tradable", width=10)
    table.add_column("Fractionable", width=13)
    table.add_column("Min Size", width=10)
    table.add_column("Age (s)", width=10)
    table.add_column("Status", width=10)

    for sym in symbols:
        meta = registry._store.get(sym)
        if meta is None:
            table.add_row(sym, "-", "-", "-", "-", "-", "-", "[dim]UNCACHED[/dim]")
            continue
        age = f"{meta.age_seconds:.0f}"
        status = "[green]VALID[/green]" if meta.is_valid else "[red]EXPIRED[/red]"
        table.add_row(
            meta.symbol,
            meta.exchange,
            meta.asset_class,
            "[green]✓[/green]" if meta.tradable else "[red]✗[/red]",
            "[blue]✓[/blue]" if meta.fractionable else "[dim]✗[/dim]",
            str(meta.min_order_size),
            age,
            status,
        )
    return table

def run_demo() -> None:
    api_key = os.getenv("ALPACA_API_KEY", "")
    secret_key = os.getenv("ALPACA_SECRET_KEY", "")

    alpaca_client = None
    mode = "MOCK"
    if api_key and secret_key:
        try:
            from alpaca.trading.client import TradingClient
            alpaca_client = TradingClient(api_key, secret_key, paper=True)
            mode = "LIVE (Paper)"
        except Exception as e:
            console.print(f"[yellow]Alpaca init failed ({e}), running in mock mode.[/yellow]")

    registry = AssetRegistry(ttl_seconds=3600.0, alpaca_client=alpaca_client)

    # Populate registry
    console.print(f"\n[bold]Mode: {mode}[/bold] — populating registry for {len(DEMO_SYMBOLS)} symbols...\n")
    t0 = time.monotonic()

    if alpaca_client:
        registry.prefetch(DEMO_SYMBOLS)
    else:
        for sym in DEMO_SYMBOLS:
            registry._store[sym] = _build_mock_metadata(sym)

    elapsed = time.monotonic() - t0
    console.print(f"Registry loaded in [bold green]{elapsed*1000:.1f}ms[/bold green]\n")

    # Simulate 1000 lookups (warm cache)
    hit_times = []
    for _ in range(1000):
        sym = random.choice(DEMO_SYMBOLS)
        t_start = time.monotonic()
        _ = registry[sym]
        hit_times.append((time.monotonic() - t_start) * 1000)

    p99 = sorted(hit_times)[int(len(hit_times) * 0.99)]

    # Display table
    table = _make_table(registry, DEMO_SYMBOLS)
    console.print(table)

    stats = registry.stats
    console.print(Panel(
        f"[bold]Registry Stats[/bold]\n"
        f"Valid Entries : {stats['valid_entries']}\n"
        f"Cache Hits    : {stats['hits']}\n"
        f"Cache Misses  : {stats['misses']}\n"
        f"Hit Rate      : [bold green]{stats['hit_rate']}[/bold green]\n"
        f"P99 Lookup    : [bold]{p99:.3f}ms[/bold]",
        title="Performance",
        border_style="cyan",
    ))

    # Persist to disk
    registry.persist()
    console.print("\n[dim]Registry persisted to data/asset_registry.json[/dim]")

if __name__ == "__main__":
    run_demo()
