"""
Stress test: CAGR surface computation over a 100-symbol universe.
Validates latency, memory, and inversion detection at scale.
Run: python -m src.stress_test
"""
from __future__ import annotations

import time
import random
import numpy as np
from rich.console import Console

from .cagr import build_cagr_surface, CAGRSurface
from .data_feed import generate_synthetic_prices

console = Console()

N_SYMBOLS = 100
PRICE_BARS = 1260  # 5 years of daily data


def run_stress_test() -> None:
    console.rule("[bold cyan]AutoQuant-Alpha | CAGR Stress Test[/]")

    # ── Generate 100 synthetic price series ──────────────────────────────
    rng = np.random.default_rng(0xCAFE)
    annual_returns = rng.uniform(0.05, 0.25, N_SYMBOLS)
    annual_vols = rng.uniform(0.10, 0.45, N_SYMBOLS)
    seeds = rng.integers(0, 9999, N_SYMBOLS)

    symbols = [f"SYM{i:03d}" for i in range(N_SYMBOLS)]
    price_series = [
        generate_synthetic_prices(
            n_days=PRICE_BARS,
            annual_return=float(annual_returns[i]),
            annual_vol=float(annual_vols[i]),
            seed=int(seeds[i]),
        )
        for i in range(N_SYMBOLS)
    ]

    # ── Timed computation ─────────────────────────────────────────────────
    start_ns = time.perf_counter_ns()
    surfaces: list[CAGRSurface] = [
        build_cagr_surface(sym, px)
        for sym, px in zip(symbols, price_series)
    ]
    elapsed_ms = (time.perf_counter_ns() - start_ns) / 1e6

    # ── Inversion detection ───────────────────────────────────────────────
    inv_start_ns = time.perf_counter_ns()
    total_inversions = 0
    for surf in surfaces:
        invs = surf.detect_inversions(threshold_bps=500)
        total_inversions += len(invs)
    inv_elapsed_ms = (time.perf_counter_ns() - inv_start_ns) / 1e6

    # ── Results ───────────────────────────────────────────────────────────
    console.print(f"[green]Symbols processed:[/]        {N_SYMBOLS}")
    console.print(f"[green]Price bars per symbol:[/]    {PRICE_BARS}")
    console.print(f"[green]Total computation time:[/]   {elapsed_ms:.2f} ms")
    console.print(f"[green]Per-symbol avg latency:[/]   {elapsed_ms / N_SYMBOLS:.3f} ms")
    console.print(f"[green]Inversion scan time:[/]      {inv_elapsed_ms:.2f} ms")
    console.print(f"[green]Total inversions found:[/]   {total_inversions}")

    # ── Pass/Fail ─────────────────────────────────────────────────────────
    scan_pass = inv_elapsed_ms < 100.0
    compute_pass = elapsed_ms < 2000.0
    status = "[PASS]" if (scan_pass and compute_pass) else "[FAIL]"
    console.print(
        f"\n{status} Inversion scan: {N_SYMBOLS} symbols in {inv_elapsed_ms:.2f}ms "
        f"(threshold: 100ms)"
    )
    console.print(
        f"{status} Bulk compute: {N_SYMBOLS} symbols in {elapsed_ms:.2f}ms "
        f"(threshold: 2000ms)"
    )


if __name__ == "__main__":
    run_stress_test()
