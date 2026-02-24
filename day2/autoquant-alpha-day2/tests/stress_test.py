"""
Stress test: reprice a synthetic portfolio of 10,000 bonds.
Target: < 2 seconds wall time on commodity hardware.
"""

from __future__ import annotations

import time
import random
import numpy as np
from datetime import date, timedelta
from rich.console import Console

from src.bond_pricer import BondSpec, BondPricer
from src.day_count import DayCount

console = Console()


def generate_random_bond(seed: int) -> tuple[BondSpec, float]:
    rng = random.Random(seed)
    coupon = round(rng.uniform(0.01, 0.08), 4)
    years_to_maturity = rng.randint(1, 30)
    maturity = date.today() + timedelta(days=365 * years_to_maturity)
    issue = date.today() - timedelta(days=rng.randint(0, 365))
    ytm = coupon + rng.uniform(-0.02, 0.02)
    ytm = max(0.001, ytm)  # No negative YTMs in stress test

    spec = BondSpec(
        face_value=1000.0,
        coupon_rate=coupon,
        maturity_date=maturity,
        issue_date=issue,
        frequency=2,
        day_count=DayCount.THIRTY_360,
    )
    return spec, ytm


def run_stress_test(n_bonds: int = 10_000) -> None:
    console.print(f"[bold cyan]Stress Test: Repricing {n_bonds:,} bonds[/bold cyan]")
    
    pricer = BondPricer()
    settlement = date.today() + timedelta(days=2)
    bonds = [generate_random_bond(i) for i in range(n_bonds)]

    console.print(f"[dim]Generated {n_bonds:,} random bonds[/dim]")

    errors = 0
    prices = []
    
    start = time.perf_counter()
    for spec, ytm in bonds:
        try:
            result = pricer.price(spec, ytm, settlement=settlement)
            prices.append(result.dirty)
        except Exception as e:
            errors += 1

    elapsed = time.perf_counter() - start

    prices_arr = np.array(prices)
    throughput = (n_bonds - errors) / elapsed

    console.print(f"[bold]Results:[/bold]")
    console.print(f"  Total bonds:     {n_bonds:>8,}")
    console.print(f"  Errors:          {errors:>8,}  {'[red]FAIL[/red]' if errors > 0 else '[green]PASS[/green]'}")
    console.print(f"  Wall time:       {elapsed:>8.3f}s  {'[green]PASS[/green]' if elapsed < 2.0 else '[red]SLOW[/red]'}")
    console.print(f"  Throughput:      {throughput:>8,.0f} bonds/s")
    console.print(f"  Price range:     [{prices_arr.min():.2f}, {prices_arr.max():.2f}]")
    console.print(f"  Mean price:      {prices_arr.mean():.4f}")

    if elapsed > 2.0:
        console.print("[red]WARNING: Reprice time exceeded 2s target.[/red]")
    else:
        console.print(f"\n[bold green]PASS: {n_bonds:,} bonds repriced in {elapsed:.3f}s[/bold green]")

if __name__ == "__main__":
    run_stress_test(10_000)
