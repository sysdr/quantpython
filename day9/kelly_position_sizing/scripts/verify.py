#!/usr/bin/env python3.11
"""
scripts/verify.py

Connects to Alpaca paper-trading and verifies:
  1. Account is accessible and NAV > 0
  2. Kelly estimation runs without error on synthetic data
  3. Sizing produces a valid (possibly 0-share) result
  4. Prints success criterion table
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


async def verify() -> None:
    console.print("[bold cyan]AutoQuant-Alpha Day 9 — Verification Script[/bold cyan]\n")

    # ---- Step 1: Load config (will raise if .env is missing) ----
    console.print("[yellow]Step 1: Loading configuration...[/yellow]")
    try:
        from src.config import CFG
        console.print(f"  API key prefix: {CFG.alpaca_api_key[:6]}... [green]✓[/green]")
        console.print(f"  Base URL: {CFG.alpaca_base_url} [green]✓[/green]")
    except Exception as e:
        console.print(f"  [red]Config failed: {e}[/red]")
        console.print("  → Copy .env.example to .env and fill in your Alpaca paper keys.")
        sys.exit(1)

    # ---- Step 2: Alpaca connectivity ----
    console.print("\n[yellow]Step 2: Alpaca paper-trading connectivity...[/yellow]")
    from src.broker.alpaca_client import AlpacaBroker
    broker = AlpacaBroker(CFG.alpaca_api_key, CFG.alpaca_secret_key, paper=True)
    try:
        nav = await broker.get_nav()
        console.print(f"  Account NAV: ${nav:,.2f} [green]✓[/green]")
    except Exception as e:
        console.print(f"  [red]Alpaca connection failed: {e}[/red]")
        console.print("  → Ensure paper API keys are set and alpaca-py is installed.")
        sys.exit(1)

    # ---- Step 3: Kelly estimation ----
    console.print("\n[yellow]Step 3: Kelly estimation on synthetic data...[/yellow]")
    from src.kelly.estimator import KellyEstimator
    from src.kelly.sizer import PositionSizer
    from src.kelly.risk_guard import RiskGuard

    estimator = KellyEstimator(n_bootstrap=CFG.bootstrap_n, spread_bps=CFG.spread_bps, seed=CFG.bootstrap_seed)
    sizer = PositionSizer(kelly_fraction=CFG.kelly_fraction, max_position_fraction=CFG.max_position_fraction)
    guard = RiskGuard()

    rng = np.random.default_rng(0)
    wins = rng.normal(0.018, 0.004, 70)
    losses = rng.normal(-0.012, 0.003, 50)
    synthetic_returns = np.concatenate([wins, losses])
    np.random.shuffle(synthetic_returns)

    est = estimator.estimate("VERIFY_SYM", synthetic_returns)
    sizing = sizer.size(est, nav=nav, price=150.0)
    decision = guard.check(sizing, existing_fractions=[0.05])

    table = Table(title="Verification Results", box=box.ROUNDED)
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="cyan")
    table.add_column("Status", style="bold")

    rows = [
        ("Symbol",          "VERIFY_SYM",                    "✓"),
        ("Win Rate",        f"{est.raw_win_rate*100:.1f}%",  "✓"),
        ("Raw b-ratio",     f"{est.raw_b_ratio:.3f}",        "✓"),
        ("Spread-adj b",    f"{est.spread_adj_b_ratio:.3f}", "✓"),
        ("Kelly p5",        f"{est.boot_kelly_p5:.4f}",      "✓"),
        ("Half-Kelly",      f"{est.boot_kelly_p5*0.5:.4f}",  "✓"),
        ("f-final",         f"{sizing.kelly_fraction:.4f}",  "✓"),
        ("Shares",          str(sizing.shares),              "✓"),
        ("Risk Approved",   str(decision.approved),          "✓" if decision.approved else "⚠"),
        ("Risk Reason",     decision.reason,                 ""),
    ]
    for name, val, status in rows:
        color = "green" if status == "✓" else ("yellow" if status == "⚠" else "dim")
        table.add_row(name, val, f"[{color}]{status}[/{color}]")

    console.print(table)

    # ---- Success Criterion ----
    console.print("\n[bold green]SUCCESS CRITERIA CHECK:[/bold green]")
    checks = [
        ("NAV > $0",                nav > 0),
        ("has_edge detected",       est.has_edge),
        ("Kelly p5 in (0, 0.5]",    0 < est.boot_kelly_p5 <= 0.5),
        ("Shares ≥ 0",              sizing.shares >= 0),
        ("f-final ≤ max_frac",      sizing.kelly_fraction <= CFG.max_position_fraction + 1e-9),
        ("Boot std < 0.12",         est.boot_kelly_std < 0.12),
    ]
    all_pass = True
    for label, passed in checks:
        icon = "[green]✓ PASS[/green]" if passed else "[red]✗ FAIL[/red]"
        console.print(f"  {label}: {icon}")
        all_pass = all_pass and passed

    if all_pass:
        console.print("\n[bold green]Day 9 verification PASSED. Ready for Day 10.[/bold green]")
    else:
        console.print("\n[bold red]One or more checks failed. Review the output above.[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(verify())
