"""
Verify: Validates trade_log.csv against Day 30 success criteria.

Checks:
  1. At least one FILLED order exists
  2. All FILLED orders have a valid order_id (UUID format)
  3. All FILLED orders have slippage_bps computed
  4. No row has slippage_bps exceeding 50 bps (sanity check)
  5. CSV is not corrupted (no partial rows)

Run: python scripts/verify.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

LOG_PATH = Path("data/trade_log.csv")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"


def verify() -> bool:
    print("AutoQuant-Alpha · Day 30 · Verification\n")

    if not LOG_PATH.exists() or LOG_PATH.stat().st_size == 0:
        print(f"{FAIL} trade_log.csv is missing or empty at {LOG_PATH}")
        return False

    with LOG_PATH.open() as fh:
        rows = list(csv.DictReader(fh))

    filled = [r for r in rows if r["status"] == "FILLED"]

    # Check 1: at least one fill
    ok1 = len(filled) > 0
    print(f"{PASS if ok1 else FAIL} FILLED orders found: {len(filled)}")

    # Check 2: valid UUIDs
    bad_ids = [r for r in filled if not UUID_RE.match(r.get("order_id", ""))]
    ok2 = len(bad_ids) == 0
    print(f"{PASS if ok2 else FAIL} All order_ids are valid UUIDs ({len(bad_ids)} invalid)")

    # Check 3: slippage computed
    missing_slip = [r for r in filled if not r.get("slippage_bps")]
    ok3 = len(missing_slip) == 0
    print(f"{PASS if ok3 else FAIL} All FILLED orders have slippage_bps ({len(missing_slip)} missing)")

    # Check 4: slippage < 50 bps (sanity)
    extreme = [r for r in filled if abs(float(r["slippage_bps"] or 0)) > 50]
    ok4 = len(extreme) == 0
    print(f"{PASS if ok4 else FAIL} No slippage > 50 bps ({len(extreme)} extreme)")

    # Check 5: no partial rows (all 11 columns present)
    partial = [r for r in rows if len(r) < 11]
    ok5 = len(partial) == 0
    print(f"{PASS if ok5 else FAIL} No corrupt rows ({len(partial)} partial)")

    passed = ok1 and ok2 and ok3 and ok4 and ok5
    print()
    if passed:
        sample = filled[0]
        print(f"  Sample order_id : {sample['order_id']}")
        print(f"  Slippage        : {sample['slippage_bps']} bps")
        print(f"  Status          : {sample['status']}")
        print(f"\n\033[92mDay 30 SUCCESS CRITERION MET. Proceed to Day 31.\033[0m")
    else:
        print("\033[91mVerification failed. Re-run demo.py and retry.\033[0m")

    return passed


if __name__ == "__main__":
    sys.exit(0 if verify() else 1)
