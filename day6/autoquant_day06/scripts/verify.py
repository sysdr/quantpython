"""
AutoQuant-Alpha Day 6 — Verification Script
Checks that the RetryWrapper meets production acceptance criteria.
"""

from __future__ import annotations

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from retry_wrapper import RetryWrapper, RetryConfig, APIError, CircuitState, CircuitOpenError
from fault_injector import FaultInjector

PASS = "✓"
FAIL = "✗"


def check(label: str, condition: bool) -> bool:
    symbol = PASS if condition else FAIL
    color = "\033[92m" if condition else "\033[91m"
    reset = "\033[0m"
    print(f"  {color}{symbol}{reset} {label}")
    return condition


async def run_verification() -> None:
    print("\n=== AutoQuant-Alpha Day 6 Verification ===\n")
    results = []

    # Test 1: Successful call with no faults
    config = RetryConfig(max_attempts=3, base_delay=0.05, cap_delay=1.0)
    w = RetryWrapper(config)
    result = await w.call(lambda: {"order_id": "TEST-001", "status": "accepted"})
    results.append(check("Clean call succeeds, no retries", w.stats()["retry_count"] == 0))

    # Test 2: Retries on 429, then succeeds
    call_count = 0
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise APIError("rate limited", 429)
        return {"order_id": "TEST-002", "status": "accepted"}

    w2 = RetryWrapper(RetryConfig(max_attempts=5, base_delay=0.01, cap_delay=0.1))
    r2 = await w2.call(flaky)
    results.append(check("Retries on 429 and eventually succeeds", r2["status"] == "accepted"))
    results.append(check("Retry count is 2", w2.stats()["retry_count"] == 2))

    # Test 3: Circuit breaker trips after failure_threshold
    w3 = RetryWrapper(RetryConfig(
        max_attempts=10, base_delay=0.01, cap_delay=0.1,
        failure_threshold=3, circuit_open_duration=1.0
    ))
    always_fail = FaultInjector(lambda: None, failure_rate=1.0, status_code=503)
    try:
        await w3.call(always_fail)
    except Exception:
        pass
    results.append(check(
        "Circuit opens after threshold failures",
        w3.circuit.state == CircuitState.OPEN
    ))

    # Test 4: Open circuit fails fast (no retries)
    fast_fail_start = time.monotonic()
    try:
        await w3.call(always_fail)
    except CircuitOpenError:
        pass
    fast_fail_duration = time.monotonic() - fast_fail_start
    results.append(check(
        f"Open circuit fails fast (< 50ms, got {fast_fail_duration*1000:.1f}ms)",
        fast_fail_duration < 0.05
    ))

    # Test 5: Circuit recovers after open_duration
    w4 = RetryWrapper(RetryConfig(
        max_attempts=5, base_delay=0.01, cap_delay=0.1,
        failure_threshold=3, circuit_open_duration=0.5
    ))
    fail_then_ok_count = 0
    def fail_then_ok():
        nonlocal fail_then_ok_count
        fail_then_ok_count += 1
        if fail_then_ok_count <= 3:
            raise APIError("down", 503)
        return {"order_id": "RECOVERED", "status": "accepted"}

    try:
        await w4.call(fail_then_ok)
    except Exception:
        pass
    await asyncio.sleep(0.6)  # Wait for circuit recovery window
    result4 = await w4.call(fail_then_ok)
    results.append(check(
        "Circuit recovers to CLOSED after open_duration",
        w4.circuit.state == CircuitState.CLOSED
    ))

    # Test 6: Non-retryable code raises immediately
    w5 = RetryWrapper(RetryConfig(max_attempts=5, base_delay=0.01, cap_delay=0.1))
    non_retryable_calls = 0
    def auth_fail():
        nonlocal non_retryable_calls
        non_retryable_calls += 1
        raise APIError("Forbidden", 403)
    try:
        await w5.call(auth_fail)
    except APIError:
        pass
    results.append(check(
        "403 raises immediately (no retry)",
        non_retryable_calls == 1 and w5.stats()["retry_count"] == 0
    ))

    passed = sum(results)
    total = len(results)
    print(f"\n{'='*42}")
    color = "\033[92m" if passed == total else "\033[91m"
    reset = "\033[0m"
    print(f"{color}{passed}/{total} checks passed{reset}")
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_verification())
