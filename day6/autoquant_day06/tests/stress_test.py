"""
Stress test: Circuit breaker under sustained overload.
Measures circuit trip latency and recovery timing.
"""

from __future__ import annotations

import asyncio
import time
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from retry_wrapper import RetryWrapper, RetryConfig, APIError, CircuitState, CircuitOpenError


async def stress_test() -> None:
    config = RetryConfig(
        max_attempts=5,
        base_delay=0.01,
        cap_delay=0.5,
        failure_threshold=5,
        circuit_open_duration=2.0,
    )

    w = RetryWrapper(config)
    results = {"success": 0, "failed": 0, "fast_failed": 0}

    def always_503():
        raise APIError("overloaded", 503)

    def healthy():
        return "ok"

    print("Phase 1: Sustained failures — tripping circuit...")
    for _ in range(30):
        try:
            await w.call(always_503)
        except CircuitOpenError:
            results["fast_failed"] += 1
        except Exception:
            results["failed"] += 1

    assert w.circuit.state == CircuitState.OPEN
    trip_time = time.monotonic()
    print(f"  Circuit OPEN after {w.circuit.trip_count} trip(s).")
    print(f"  Fast-fails: {results['fast_failed']}, Exhausted: {results['failed']}")

    print("Phase 2: Waiting for recovery window...")
    await asyncio.sleep(config.circuit_open_duration + 0.2)

    print("Phase 3: Probe recovery...")
    result = await w.call(healthy)
    assert result == "ok"
    assert w.circuit.state == CircuitState.CLOSED
    recovery_time = time.monotonic() - trip_time
    print(f"  Circuit CLOSED. Recovery time: {recovery_time:.2f}s")

    print("\n✓ Stress test passed.")


if __name__ == "__main__":
    asyncio.run(stress_test())
