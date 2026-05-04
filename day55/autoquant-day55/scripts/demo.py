"""
demo.py — Live dashboard demo for Day 55.

Usage:
    python scripts/demo.py --orders 200 --symbol AAPL
    python scripts/demo.py --orders 500 --sim-min-us 10000 --sim-max-us 800000
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from rich.console import Console

from src.dashboard import LiveDashboard
from src.match_engine import SimulatedMatchEngine
from src.timer import LatencyRecorder

CONSOLE = Console()


def main() -> None:
    ap = argparse.ArgumentParser(description="AutoQuant Day 55 live demo")
    ap.add_argument("--orders", type=int, default=100)
    ap.add_argument("--symbol", type=str, default="AAPL")
    ap.add_argument("--sim-min-us", type=float, default=50_000.0)
    ap.add_argument("--sim-max-us", type=float, default=450_000.0)
    ap.add_argument("--delay-ms", type=float, default=50.0,
                    help="Inter-order delay in ms (controls dashboard refresh visibility)")
    args = ap.parse_args()

    api_key    = os.getenv("ALPACA_API_KEY", "")
    secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    paper      = os.getenv("ALPACA_PAPER", "true").lower() == "true"

    recorder = LatencyRecorder(maxlen=10_000)
    engine = SimulatedMatchEngine(
        recorder=recorder,
        api_key=api_key,
        secret_key=secret_key,
        paper=paper,
        sim_latency_range_us=(args.sim_min_us, args.sim_max_us),
        log_path=Path("data/latency_samples.jsonl"),
    )

    source = "Alpaca paper API" if engine._source == "alpaca" else "simulation mode"
    CONSOLE.print(
        f"[bold cyan]AutoQuant-Alpha Day 55[/bold cyan] — "
        f"Submitting [bold]{args.orders}[/bold] orders via [yellow]{source}[/yellow]"
    )

    sides = ["BUY", "SELL"]
    with LiveDashboard(recorder=recorder, refresh_rate=8) as dash:
        for i in range(args.orders):
            result = engine.submit_order(
                symbol=args.symbol,
                qty=1.0,
                side=sides[i % 2],
            )
            dash.push(result)
            time.sleep(args.delay_ms / 1_000.0)

    # Final summary
    p = recorder.percentiles()
    CONSOLE.print("\n[bold]Final Percentiles[/bold]")
    CONSOLE.print(
        f"  p50={p['p50']:,.1f}µs  p95={p['p95']:,.1f}µs  "
        f"p99={p['p99']:,.1f}µs  count={int(p['count']):,}  "
        f"negatives={int(p['negative'])}"
    )

    if int(p["negative"]) > 0:
        CONSOLE.print("[bold red]⚠ WARNING: Negative latency samples detected. "
                      "Check clock source.[/bold red]")
    else:
        CONSOLE.print("[bold green]✓ Zero negative samples — clock is monotonic.[/bold green]")

    CONSOLE.print(f"[dim]Log written to: data/latency_samples.jsonl[/dim]")


if __name__ == "__main__":
    main()
