#!/usr/bin/env python3
"""
verify.py — Run full test suite + print pass/fail table.
"""

import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

TESTS = [
    ("Unit: log return accuracy",        "tests/test_return_engine.py::test_log_return_accuracy"),
    ("Unit: NaN propagation guard",       "tests/test_return_engine.py::test_nan_propagation_guard"),
    ("Unit: corporate action detection",  "tests/test_return_engine.py::test_corporate_action_detection"),
    ("Unit: vectorised vs loop parity",   "tests/test_return_engine.py::test_vectorised_vs_loop_parity"),
    ("Unit: arithmetic conversion",       "tests/test_return_engine.py::test_arithmetic_conversion"),
    ("Stress: 500-symbol timing",         "tests/stress_test.py::test_500_symbols_timing"),
    ("Stress: memory footprint",          "tests/stress_test.py::test_memory_footprint"),
]


def run_test(test_id: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_id, "-q", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    )
    return result.returncode == 0


def main() -> None:
    console.rule("[bold blue]AutoQuant-Alpha · Day 10 · Verification Suite[/]")

    table = Table(box=box.SIMPLE_HEAD)
    table.add_column("Test", style="white", width=45)
    table.add_column("Result", justify="center", width=10)

    passed = failed = 0
    for name, test_id in TESTS:
        ok = run_test(test_id)
        if ok:
            table.add_row(name, "[bold green]PASS[/]")
            passed += 1
        else:
            table.add_row(name, "[bold red]FAIL[/]")
            failed += 1

    console.print(table)
    console.print(
        f"\n[bold]{'[green]ALL PASS' if failed == 0 else '[red]FAILURES DETECTED'}[/bold] "
        f"({passed}/{passed+failed} tests passed)"
    )

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
