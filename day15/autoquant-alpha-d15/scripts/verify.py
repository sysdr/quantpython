"""
Day 15 Verification Script.
Checks DLQ CSV for failed orders and reports pass/fail.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

DLQ_CSV = Path("data/dlq/dead_letters.csv")


def verify_dlq() -> int:
    """Returns number of DLQ entries (0 = pass)."""
    if not DLQ_CSV.exists():
        print("  ✓ No DLQ file (zero failed orders)")
        return 0
    with DLQ_CSV.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print("  ✓ DLQ file exists but is empty")
        return 0
    print(f"  ✗ DLQ contains {len(rows)} failed order(s):")
    for r in rows[:5]:
        print(f"    {r.get('order_id', '?')[:8]} | {r.get('symbol')} | {r.get('error')}")
    if len(rows) > 5:
        print(f"    ... and {len(rows) - 5} more. See {DLQ_CSV}")
    return len(rows)


def main() -> None:
    print("\n=== AutoQuant-Alpha D15 — Verification ===")
    failures = verify_dlq()
    if failures:
        print(f"\n✗ FAILED: {failures} DLQ entries. Resolve before Day 16.")
        sys.exit(1)
    print("\n✓ PASSED: All orders filled, DLQ clean. Proceed to Day 16.")


if __name__ == "__main__":
    main()
