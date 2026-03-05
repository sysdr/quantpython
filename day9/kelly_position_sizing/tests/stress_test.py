"""
tests/stress_test.py

Performance and robustness stress test for the Kelly estimator.

Run: python tests/stress_test.py

Measures:
  1. Bootstrap timing for 100k resamples (n_bootstrap=100_000, n_trades=200)
  2. Concurrent estimation of 50 symbols
  3. Numerical stability under edge cases
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
import numpy as np
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


def _synth(n: int, wr: float, aw: float, al: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    w = rng.choice([True, False], size=n, p=[wr, 1-wr])
    return np.where(w, rng.normal(aw, aw*0.2, n), -rng.normal(al, al*0.2, n))


def run_stress() -> None:
    from src.kelly.estimator import KellyEstimator

    console.print("[bold cyan]AutoQuant-Alpha | Stress Test Suite[/bold cyan]\n")

    # ---------------------------------------------------------------
    # Test 1: Timing — 100k bootstrap resamples
    # ---------------------------------------------------------------
    console.print("[yellow]Test 1: Bootstrap timing (n_bootstrap=100_000, n_trades=200)[/yellow]")
    est_heavy = KellyEstimator(n_bootstrap=100_000, spread_bps=5.0, seed=0)
    r = _synth(200, 0.55, 0.018, 0.012, 0)
    t0 = time.perf_counter()
    result = est_heavy.estimate("TIMING", r)
    elapsed = (time.perf_counter() - t0) * 1000
    console.print(f"  100k resamples completed in [bold green]{elapsed:.1f} ms[/bold green]")
    assert elapsed < 10_000, f"Bootstrap too slow: {elapsed:.1f}ms (threshold: 10000ms)"
    console.print("  [green]✓ PASS[/green]")

    # ---------------------------------------------------------------
    # Test 2: Concurrent estimation of 50 symbols
    # ---------------------------------------------------------------
    console.print("\n[yellow]Test 2: 50-symbol concurrent estimation[/yellow]")
    est = KellyEstimator(n_bootstrap=5_000, spread_bps=5.0, seed=42)
    symbols = [f"SYM{i:02d}" for i in range(50)]
    histories = [_synth(150, 0.50 + i*0.005, 0.015, 0.012, i) for i in range(50)]

    t0 = time.perf_counter()
    estimates = [est.estimate(sym, hist) for sym, hist in zip(symbols, histories)]
    elapsed = (time.perf_counter() - t0) * 1000

    console.print(f"  50 symbols estimated in [bold green]{elapsed:.1f} ms[/bold green]")
    has_edge_count = sum(1 for e in estimates if e.has_edge)
    console.print(f"  {has_edge_count}/50 symbols detected with edge")
    assert elapsed < 10_000
    console.print("  [green]✓ PASS[/green]")

    # ---------------------------------------------------------------
    # Test 3: Numerical stability
    # ---------------------------------------------------------------
    console.print("\n[yellow]Test 3: Numerical stability under edge cases[/yellow]")
    edge_cases = [
        ("all_wins",    np.abs(_synth(100, 0.99, 0.01, 0.001, 0))),
        ("all_losses",  -np.abs(_synth(100, 0.01, 0.01, 0.01, 0))),
        ("tiny_sample", _synth(3, 0.55, 0.02, 0.01, 0)),
        ("huge_wins",   _synth(100, 0.55, 10.0, 1.0, 0)),
        ("near_zero",   _synth(100, 0.55, 1e-6, 1e-6, 0)),
        ("mixed_zeros", np.concatenate([np.zeros(50), _synth(50, 0.55, 0.02, 0.01, 0)])),
    ]

    for case_name, returns in edge_cases:
        try:
            result = est.estimate(case_name, returns)
            assert result.boot_kelly_p5 >= 0.0, "Kelly p5 went negative"
            assert not np.isnan(result.boot_kelly_p5), "Kelly p5 is NaN"
            console.print(f"  {case_name:20s} → has_edge={result.has_edge}, p5={result.boot_kelly_p5:.4f} [green]✓[/green]")
        except Exception as e:
            console.print(f"  {case_name:20s} [red]FAIL: {e}[/red]")
            raise

    # ---------------------------------------------------------------
    # Test 4: Regime sensitivity (homework validation)
    # ---------------------------------------------------------------
    console.print("\n[yellow]Test 4: Below-edge regime produces near-zero sizing[/yellow]")
    from src.kelly.sizer import PositionSizer
    est4 = KellyEstimator(n_bootstrap=5_000, spread_bps=5.0, seed=0)
    sizer = PositionSizer(kelly_fraction=0.5, max_position_fraction=0.15)
    below_edge_returns = _synth(200, wr=0.47, aw=0.012, al=0.010, seed=99)
    e4 = est4.estimate("BELOW_EDGE", below_edge_returns)
    s4 = sizer.size(e4, nav=100_000, price=100.0)
    console.print(f"  win_rate=0.47 → f_final={s4.kelly_fraction:.4f}, shares={s4.shares}")
    assert s4.kelly_fraction < 0.02, f"Expected near-zero sizing, got {s4.kelly_fraction:.4f}"
    console.print("  [green]✓ PASS[/green]")

    console.print("\n[bold green]All stress tests passed.[/bold green]")


if __name__ == "__main__":
    run_stress()
