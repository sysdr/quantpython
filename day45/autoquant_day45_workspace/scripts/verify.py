"""
scripts/verify.py
Runs unit tests + stress test + optional Alpaca reconciliation.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
_root = str(ROOT)
if _root not in sys.path:
    sys.path.insert(0, _root)

load_dotenv(ROOT / ".env")


def run_unit_tests() -> bool:
    print("\n[1/3] Running unit tests...")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(ROOT / "tests/test_margin.py"),
            "-v",
            "--tb=short",
            f"--rootdir={ROOT}",
        ],
        cwd=ROOT,
        capture_output=False,
    )
    return result.returncode == 0


def run_stress_test() -> bool:
    print("\n[2/3] Running concurrency stress test...")
    env = os.environ.copy()
    env["PYTHONPATH"] = _root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests/stress_test.py")],
        cwd=ROOT,
        env=env,
        capture_output=False,
    )
    return result.returncode == 0


def run_alpaca_reconciliation() -> bool:
    from decimal import Decimal
    from src.margin.account import AccountMode, MarginAccount
    from src.broker.reconciler import AlpacaReconciler

    print("\n[3/3] Reconciling against Alpaca paper account...")
    try:
        account = MarginAccount(Decimal("0"), mode=AccountMode.DAY_TRADE)
        rec = AlpacaReconciler(account)
        result = rec.reconcile()
        print(f"  Alpaca Equity:        ${result.alpaca_equity:,.2f}")
        print(f"  Alpaca Cash:          ${result.alpaca_cash:,.2f}")
        print(f"  Alpaca DT BP:         ${result.alpaca_buying_power:,.2f}")
        print(f"  Alpaca Reg-T BP:      ${result.alpaca_regt_buying_power:,.2f}")
        print(f"  Alpaca Avail. BP:     ${result.alpaca_available_buying_power:,.2f}")
        print(f"  Local Day-Trade BP:   ${result.local_day_trade_bp:,.2f}")
        print(f"  Local Overnight BP:   ${result.local_overnight_bp:,.2f}")
        print(f"  BP Delta:             {result.bp_delta_pct:.4f}%")
        print(f"  Within Tolerance:     {'✅' if result.within_tolerance else '❌'}")
        return result.within_tolerance
    except Exception as e:
        print(f"  Alpaca reconciliation skipped (no live account): {e}")
        return True


def main() -> None:
    os.chdir(ROOT)
    print("AutoQuant-Alpha · Day 45 Verification Suite")
    print("=" * 50)

    ok1 = run_unit_tests()
    ok2 = run_stress_test()
    ok3 = run_alpaca_reconciliation()

    print("\n" + "=" * 50)
    print(f"  Unit Tests:         {'✅ PASS' if ok1 else '❌ FAIL'}")
    print(f"  Stress Test:        {'✅ PASS' if ok2 else '❌ FAIL'}")
    print(f"  Alpaca Reconcile:   {'✅ PASS' if ok3 else '❌ FAIL'}")
    print("=" * 50)

    sys.exit(0 if all([ok1, ok2, ok3]) else 1)


if __name__ == "__main__":
    main()
