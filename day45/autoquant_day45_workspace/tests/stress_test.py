"""
tests/stress_test.py
Concurrency stress test: 1000 simultaneous reservation attempts.
Assert zero buying-power violations.
"""
from __future__ import annotations

import concurrent.futures
import time
from decimal import Decimal

from src.margin.account import (
    AccountMode,
    DAY_TRADE_LEVERAGE,
    MarginAccount,
    OVERNIGHT_LEVERAGE,
)


def _max_concurrent_reservations(
    initial_cash: Decimal, reserve_amount: Decimal, mode: AccountMode
) -> int:
    """Upper bound on simultaneous reserves (same size) at t=0 with no positions."""
    if mode == AccountMode.CASH:
        cap = initial_cash
    elif mode == AccountMode.MARGIN:
        cap = (initial_cash * OVERNIGHT_LEVERAGE).quantize(Decimal("0.01"))
    else:
        cap = (initial_cash * DAY_TRADE_LEVERAGE).quantize(Decimal("0.01"))
    return int(cap // reserve_amount)


def run_stress_test(
    n_threads: int = 1000,
    reserve_amount: Decimal = Decimal("500.00"),
    initial_cash: Decimal = Decimal("10000.00"),
    mode: AccountMode = AccountMode.CASH,
) -> dict:
    acct = MarginAccount(initial_cash, mode=mode)
    successes = 0
    failures  = 0
    start_ns  = time.perf_counter_ns()

    def attempt(i: int) -> bool:
        r = acct.reserve(f"stress-{i}", reserve_amount)
        return r.success

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(n_threads, 200)) as pool:
        futs = [pool.submit(attempt, i) for i in range(n_threads)]
        for f in concurrent.futures.as_completed(futs):
            if f.result():
                successes += 1
            else:
                failures += 1

    elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
    snap = acct.snapshot()

    max_allowed = _max_concurrent_reservations(initial_cash, reserve_amount, mode)

    result = {
        "n_threads":       n_threads,
        "successes":       successes,
        "failures":        failures,
        "max_allowed":     max_allowed,
        "reserved_total":  float(snap.reserved),
        "initial_cash":    float(initial_cash),
        "violation":       successes > max_allowed,
        "elapsed_ms":      elapsed_ms,
    }

    print(f"\n{'='*55}")
    print(f"  STRESS TEST: {n_threads} concurrent reservation attempts")
    print(f"{'='*55}")
    print(f"  Initial Cash:   ${initial_cash:,.2f}")
    print(f"  Per-Reserve:    ${reserve_amount:,.2f}")
    print(f"  Max Allowed:    {max_allowed}")
    print(f"  Approved:       {successes}")
    print(f"  Rejected:       {failures}")
    print(f"  Reserved Total: ${snap.reserved:,.2f}")
    print(f"  Elapsed:        {elapsed_ms:.1f}ms")
    print(f"  VIOLATION:      {'❌ YES — BUG DETECTED' if result['violation'] else '✅ NONE'}")
    print(f"{'='*55}\n")

    assert not result["violation"], (
        f"BUYING POWER VIOLATION: {successes} approved but max is {max_allowed}"
    )

    return result


if __name__ == "__main__":
    # Test 1: CASH mode, tight budget
    run_stress_test(n_threads=1000, reserve_amount=Decimal("500"), initial_cash=Decimal("10000"))

    # Test 2: DAY_TRADE mode with 4x leverage
    run_stress_test(
        n_threads=1000,
        reserve_amount=Decimal("2000"),
        initial_cash=Decimal("10000"),
        mode=AccountMode.DAY_TRADE,
    )

    print("All stress tests passed ✅")
