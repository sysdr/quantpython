"""
Stress test: submit N simulated orders and assert latency SLAs.

Usage:
    python tests/stress_test.py --n 1000 --p99-threshold-us 600000

Exit 0 on pass, 1 on failure.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running as `python tests/stress_test.py` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from src.match_engine import SimulatedMatchEngine
from src.timer import LatencyRecorder

CONSOLE = Console()


def run_stress(n: int, p99_threshold_us: float, sim_range: tuple[float, float]) -> bool:
    recorder = LatencyRecorder(maxlen=max(n, 10_000))
    engine = SimulatedMatchEngine(
        recorder=recorder,
        sim_latency_range_us=sim_range,
    )

    CONSOLE.print(
        f"[bold]Stress Test[/bold] — {n:,} orders | "
        f"sim latency range: {sim_range[0]/1e3:.0f}µs–{sim_range[1]/1e3:.0f}µs"
    )

    symbols = ["AAPL", "MSFT", "GOOG", "TSLA", "NVDA"]
    sides = ["BUY", "SELL"]

    wall_start = time.perf_counter()
    for i in range(n):
        engine.submit_order(
            symbol=symbols[i % len(symbols)],
            qty=1.0,
            side=sides[i % 2],
        )

    elapsed = time.perf_counter() - wall_start
    throughput = n / elapsed

    p = recorder.percentiles()

    tbl = Table(title="Stress Test Results", show_header=True, header_style="bold cyan")
    tbl.add_column("Metric", style="dim", width=18)
    tbl.add_column("Value", justify="right", width=20)
    tbl.add_column("SLA", justify="right", width=20)
    tbl.add_column("Status", justify="center", width=10)

    checks: list[tuple[str, float, float]] = [
        ("p99 (µs)",    p["p99"],        p99_threshold_us),
        ("p95 (µs)",    p["p95"],        p99_threshold_us * 0.8),
        ("negatives",   p["negative"],   0.0),
    ]

    all_pass = True
    for metric, val, sla in checks:
        passed = val <= sla
        all_pass = all_pass and passed
        tbl.add_row(
            metric,
            f"{val:>14,.1f}",
            f"≤ {sla:>12,.1f}",
            "[green]✓ PASS[/green]" if passed else "[red]✗ FAIL[/red]",
        )

    tbl.add_row("[dim]throughput[/dim]", f"{throughput:>10,.1f} ord/s", "—", "—")
    tbl.add_row("[dim]p50 (µs)[/dim]",   f"{p['p50']:>14,.1f}", "—", "—")
    tbl.add_row("[dim]count[/dim]",       f"{int(p['count']):>14,}", "—", "—")

    CONSOLE.print(tbl)
    return all_pass


def main() -> None:
    ap = argparse.ArgumentParser(description="AutoQuant Day 55 stress test")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--p99-threshold-us", type=float, default=600_000.0)
    ap.add_argument("--sim-min-us", type=float, default=50_000.0)
    ap.add_argument("--sim-max-us", type=float, default=500_000.0)
    args = ap.parse_args()

    passed = run_stress(
        n=args.n,
        p99_threshold_us=args.p99_threshold_us,
        sim_range=(args.sim_min_us, args.sim_max_us),
    )
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
