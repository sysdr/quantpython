#!/usr/bin/env python3
"""
Verification script: validates bond pricer against known values
and optionally against Alpaca market data.
"""

import sys
sys.path.insert(0, ".")

from datetime import date, timedelta
from rich.console import Console
from rich.table import Table
from rich import box

from src.bond_pricer import BondSpec, BondPricer
from src.day_count import DayCount
from src.alpaca_bridge import fetch_benchmark_prices

console = Console()
pricer = BondPricer()

PASS = "[bold green]PASS[/bold green]"
FAIL = "[bold red]FAIL[/bold red]"


def check(label: str, condition: bool, detail: str = "") -> bool:
    status = PASS if condition else FAIL
    console.print(f"  {status}  {label}" + (f" — {detail}" if detail else ""))
    return condition


def main() -> int:
    console.print("\n[bold cyan]AutoQuant-Alpha Day 2 — Verification Suite[/bold cyan]\n")
    results: list[bool] = []

    # 1. FV round-trip
    from src.bond_math import future_value, present_value
    fv = future_value(1000.0, 0.05, 10)
    pv = present_value(fv, 0.05, 10)
    results.append(check("FV/PV round-trip", abs(pv - 1000.0) < 1e-6,
                          f"error={abs(pv - 1000.0):.2e}"))

    # 2. Par bond pricing
    spec = BondSpec(
        face_value=100.0,
        coupon_rate=0.05,
        maturity_date=date(2034, 2, 15),
        issue_date=date(2024, 2, 15),
        frequency=2,
        day_count=DayCount.THIRTY_360,
    )
    result = pricer.price(spec, ytm=0.05, settlement=date(2024, 2, 17))
    err_bps = abs(result.dirty - 100.0) * 100  # in bps since face=100
    results.append(check("Par bond pricing error < 50 bps", err_bps < 50,
                          f"error={err_bps:.2f} bps"))

    # 3. YTM solver convergence
    target_ytm = 0.0523
    res = pricer.price(spec, ytm=target_ytm, settlement=date(2024, 2, 17))
    recovered = pricer.price_from_market(spec, res.clean, settlement=date(2024, 2, 17))
    ytm_err_bps = abs(recovered.ytm - target_ytm) * 10000
    results.append(check("YTM solver convergence < 0.001 bps", ytm_err_bps < 0.001,
                          f"error={ytm_err_bps:.4f} bps"))
    results.append(check("YTM solver converged flag", recovered.solver_converged))

    # 4. Dirty/clean reconciliation
    settlement = date(2024, 5, 10)
    res2 = pricer.price(spec, ytm=0.05, settlement=settlement)
    recon_err = abs(res2.dirty - res2.clean - res2.accrued)
    results.append(check("Dirty = Clean + Accrued reconciliation",
                          recon_err < 1e-9, f"error={recon_err:.2e}"))

    # 5. Duration sanity check
    results.append(check("Modified duration > 0", res2.modified_dur > 0,
                          f"dur={res2.modified_dur:.4f}"))

    # 6. DV01 sanity: 30Y should have higher DV01 than 2Y
    spec_30y = BondSpec(
        face_value=100.0,
        coupon_rate=0.045,
        maturity_date=date.today() + timedelta(days=10950),
        issue_date=date.today() - timedelta(days=60),
        frequency=2,
        day_count=DayCount.ACT_ACT_ISDA,
    )
    spec_2y = BondSpec(
        face_value=100.0,
        coupon_rate=0.048,
        maturity_date=date.today() + timedelta(days=730),
        issue_date=date.today() - timedelta(days=30),
        frequency=2,
        day_count=DayCount.ACT_ACT_ISDA,
    )
    r30 = pricer.price(spec_30y, 0.046)
    r2 = pricer.price(spec_2y, 0.048)
    results.append(check("30Y DV01 > 2Y DV01",
                          r30.dv01_per_face > r2.dv01_per_face,
                          f"30Y=${r30.dv01_per_face:.4f}, 2Y=${r2.dv01_per_face:.4f}"))

    # 7. Alpaca market data (optional)
    console.print("\n[dim]Fetching Alpaca benchmark prices (requires API keys)...[/dim]")
    prices = fetch_benchmark_prices()
    for ticker, price in prices.items():
        if price is not None:
            results.append(check(f"Alpaca {ticker} price fetch", price > 0,
                                  f"${price:.2f}"))
        else:
            console.print(f"  [yellow]SKIP[/yellow]  Alpaca {ticker} — no credentials or unavailable")

    # Summary
    passed = sum(results)
    total = len(results)
    console.print(f"\n{'─'*50}")
    if passed == total:
        console.print(f"[bold green]ALL {total} CHECKS PASSED ✓[/bold green]")
    else:
        console.print(f"[bold red]{total - passed} FAILED / {total} CHECKS[/bold red]")
    console.print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
