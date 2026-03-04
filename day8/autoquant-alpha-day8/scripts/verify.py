"""
Day 8 completion verifier.
Checks workspace structure, unit tests, and stress test.
"""
from __future__ import annotations
import subprocess, sys, os
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

REQUIRED = [
    "src/core/types.py", "src/core/ring_buffer.py",
    "src/core/interface.py", "src/core/state.py",
    "src/strategies/momentum_scalp.py",
    "src/execution/order_manager.py", "src/execution/alpaca_bridge.py",
    "src/dashboard/cli_dashboard.py",
    "tests/test_ring_buffer.py", "tests/test_on_tick.py",
    "tests/stress_test.py",
]

def check_structure() -> bool:
    print("[1/3] Workspace structure")
    ok = True
    for f in REQUIRED:
        exists = (ROOT / f).exists()
        print(f"  {'✓' if exists else '✗ MISSING'}  {f}")
        if not exists: ok = False
    return ok

def run_unit_tests() -> bool:
    print("\n[2/3] Unit tests")
    r = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_ring_buffer.py", "tests/test_on_tick.py", "-v", "--tb=short"],
        cwd=ROOT,
    )
    return r.returncode == 0

def run_stress_test() -> bool:
    print("\n[3/3] Stress test")
    r = subprocess.run([sys.executable, "tests/stress_test.py"], cwd=ROOT)
    return r.returncode == 0

if __name__ == "__main__":
    ok  = check_structure()
    ok  = run_unit_tests()  and ok
    ok  = run_stress_test() and ok
    print("\n" + ("✓  ALL CHECKS PASSED — Day 8 Complete!" if ok
                    else "✗  SOME CHECKS FAILED — review output above"))
    sys.exit(0 if ok else 1)
