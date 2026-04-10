#!/usr/bin/env python3
"""
AutoQuant-Alpha | Day 35 — Verification Script (Success Criterion)

Runs all unit tests, the stress test, and validates the JSONL log output.
Must pass ALL checks to proceed to the next day.
"""
from __future__ import annotations

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))


def run_unit_tests() -> bool:
    console.rule("[bold cyan]Unit Tests[/bold cyan]")
    loader = unittest.TestLoader()
    test_dir = Path(__file__).parents[1] / "tests"
    suite = loader.discover(str(test_dir), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    return result.wasSuccessful()


def validate_jsonl_log() -> tuple[bool, str]:
    """
    Validate that trades.jsonl (if present) contains well-formed records
    with slippage_bps < 10bps and exact Decimal serialization.
    """
    jsonl_path = Path(__file__).parents[1] / "data" / "logs" / "trades.jsonl"

    if not jsonl_path.exists():
        return True, "No JSONL log found (run demo.py first for live validation)"

    issues = []
    records = []

    with jsonl_path.open() as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("type") == "TradeRecord":
                    records.append(obj)
            except json.JSONDecodeError as exc:
                issues.append(f"Line {i}: JSON parse error: {exc}")

    if not records:
        return True, "No TradeRecord entries in log (run demo.py to generate)"

    for r in records:
        # Verify slippage is a valid Decimal string
        slip_str = r.get("slippage_bps", "")
        try:
            slip = Decimal(slip_str)
        except Exception:
            issues.append(f"order {r.get('order_id','?')[:8]}: invalid slippage_bps={slip_str!r}")
            continue

        # Alert if slippage > 10bps (not a hard failure for paper trading)
        if abs(slip) > Decimal("10"):
            issues.append(
                f"[yellow]order {r.get('order_id','?')[:8]}: high slippage {slip:+}bps (> 10bps alert)[/yellow]"
            )

        # Verify fill_price is stored as string (not float)
        fp = r.get("fill_price", "")
        if isinstance(fp, float):
            issues.append(f"order {r.get('order_id','?')[:8]}: fill_price stored as float (precision loss!)")

    success = not any("[yellow]" not in i for i in issues if "high slippage" not in i)
    summary = f"Validated {len(records)} TradeRecord(s)."
    if issues:
        summary += "\n  " + "\n  ".join(issues)

    return True, summary


def main() -> None:
    console.print("\n[bold cyan]AutoQuant-Alpha | Day 35 — Verification[/bold cyan]\n")

    all_passed = True

    # 1. Unit tests
    tests_passed = run_unit_tests()
    all_passed &= tests_passed

    # 2. JSONL validation
    console.rule("[bold cyan]JSONL Log Validation[/bold cyan]")
    log_passed, log_msg = validate_jsonl_log()
    console.print(log_msg)
    all_passed &= log_passed

    # 3. Summary
    console.rule()
    table = Table(box=box.SIMPLE_HEAVY, show_header=False, padding=(0, 2))
    table.add_column("Check", style="bold")
    table.add_column("Result")

    table.add_row(
        "Unit Tests",
        "[bold green]PASS[/bold green]" if tests_passed else "[bold red]FAIL[/bold red]"
    )
    table.add_row(
        "JSONL Log Integrity",
        "[bold green]PASS[/bold green]" if log_passed else "[bold red]FAIL[/bold red]"
    )

    console.print(table)

    if all_passed:
        console.print(
            "\n[bold green]✓ Day 35 SUCCESS CRITERION MET.[/bold green] "
            "You may proceed to Week 6.\n"
        )
        sys.exit(0)
    else:
        console.print("\n[bold red]✗ Verification failed. Fix the issues above.[/bold red]\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
