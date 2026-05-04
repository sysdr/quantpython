"""
verify.py — Day 55 success criterion checker.

Reads the JSONL log produced by demo.py and verifies:
  1. Zero negative latency samples
  2. p99 < threshold (default 600,000 µs)
  3. Sample count >= minimum (default 50)

Usage:
    python scripts/verify.py --log data/latency_samples.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from rich.console import Console
from rich.table import Table

CONSOLE = Console()


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main() -> None:
    ap = argparse.ArgumentParser(description="Day 55 success criterion verifier")
    ap.add_argument("--log", type=Path, default=Path("data/latency_samples.jsonl"))
    ap.add_argument("--p99-threshold-us", type=float, default=600_000.0)
    ap.add_argument("--min-samples", type=int, default=50)
    args = ap.parse_args()

    if not args.log.exists():
        CONSOLE.print(f"[red]Log file not found: {args.log}[/red]")
        CONSOLE.print("[dim]Run: python scripts/demo.py --orders 100 first[/dim]")
        sys.exit(1)

    records = load_jsonl(args.log)
    CONSOLE.print(f"[dim]Loaded {len(records)} records from {args.log}[/dim]\n")

    latencies = np.array([r["latency_us"] for r in records], dtype=np.float64)
    negatives = int((latencies < 0).sum())
    p99 = float(np.percentile(latencies, 99)) if latencies.size > 0 else float("inf")
    count = len(records)

    checks = [
        ("Monotonicity (zero negatives)", negatives == 0,
         f"{negatives} negative sample(s)", "0 required"),
        (f"p99 < {args.p99_threshold_us:,.0f} µs", p99 < args.p99_threshold_us,
         f"p99 = {p99:,.1f} µs", f"< {args.p99_threshold_us:,.0f} µs"),
        (f"Sample count ≥ {args.min_samples}", count >= args.min_samples,
         f"count = {count}", f"≥ {args.min_samples}"),
    ]

    tbl = Table(title="Day 55 — Success Criterion", show_header=True,
                header_style="bold cyan", border_style="cyan")
    tbl.add_column("Check", width=38)
    tbl.add_column("Measured", justify="right", width=22)
    tbl.add_column("Threshold", justify="right", width=18)
    tbl.add_column("Result", justify="center", width=10)

    all_pass = True
    for label, passed, measured, threshold in checks:
        all_pass = all_pass and passed
        tbl.add_row(
            label, measured, threshold,
            "[bold green]✓ PASS[/bold green]" if passed else "[bold red]✗ FAIL[/bold red]",
        )

    CONSOLE.print(tbl)

    if all_pass:
        CONSOLE.print("\n[bold green]✓ All checks passed — Day 55 complete.[/bold green]")
        CONSOLE.print("[dim]You may proceed to Day 56.[/dim]")
        sys.exit(0)
    else:
        CONSOLE.print("\n[bold red]✗ Some checks failed. Review the output above.[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
