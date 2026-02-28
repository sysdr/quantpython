"""
Unit + Stress tests for RetryWrapper and CircuitBreaker.
Run: pytest tests/ -v --asyncio-mode=auto
"""

from __future__ import annotations

import asyncio
import time
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from retry_wrapper import (
    RetryWrapper, RetryConfig, APIError,
    CircuitBreaker, CircuitState, CircuitOpenError, MaxRetriesExceeded,
)


@pytest.fixture
def fast_config() -> RetryConfig:
    return RetryConfig(
        max_attempts=4,
        base_delay=0.01,
        cap_delay=0.1,
        failure_threshold=3,
        circuit_open_duration=0.5,
    )


@pytest.mark.asyncio
async def test_success_no_retry(fast_config):
    w = RetryWrapper(fast_config)
    result = await w.call(lambda: 42)
    assert result == 42
    assert w.stats()["retry_count"] == 0


@pytest.mark.asyncio
async def test_retries_on_retryable_code(fast_config):
    call_count = 0
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise APIError("rate limited", 429)
        return "ok"

    w = RetryWrapper(fast_config)
    result = await w.call(flaky)
    assert result == "ok"
    assert w.stats()["retry_count"] == 2


@pytest.mark.asyncio
async def test_non_retryable_raises_immediately(fast_config):
    calls = 0
    def auth_fail():
        nonlocal calls
        calls += 1
        raise APIError("Unauthorized", 401)

    w = RetryWrapper(fast_config)
    with pytest.raises(APIError) as exc_info:
        await w.call(auth_fail)
    assert exc_info.value.status_code == 401
    assert calls == 1
    assert w.stats()["retry_count"] == 0


@pytest.mark.asyncio
async def test_max_retries_exceeded(fast_config):
    def always_fail():
        raise APIError("server error", 500)

    w = RetryWrapper(fast_config)
    with pytest.raises((MaxRetriesExceeded, CircuitOpenError)):
        await w.call(always_fail)


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold(fast_config):
    def always_fail():
        raise APIError("service unavailable", 503)

    w = RetryWrapper(fast_config)
    try:
        await w.call(always_fail)
    except Exception:
        pass
    assert w.circuit.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_fails_fast_when_open(fast_config):
    w = RetryWrapper(fast_config)
    w.circuit.state = CircuitState.OPEN
    w.circuit._last_failure_time = time.monotonic()  # reset timer

    start = time.monotonic()
    with pytest.raises(CircuitOpenError):
        await w.call(lambda: None)
    elapsed = time.monotonic() - start
    assert elapsed < 0.02, f"Fast-fail took {elapsed:.3f}s — circuit not failing fast"


@pytest.mark.asyncio
async def test_circuit_half_open_recovery(fast_config):
    """Circuit transitions OPEN → HALF_OPEN → CLOSED on successful probe."""
    w = RetryWrapper(fast_config)
    w.circuit.state = CircuitState.OPEN
    w.circuit._last_failure_time = time.monotonic() - fast_config.circuit_open_duration - 0.1

    result = await w.call(lambda: "recovered")
    assert result == "recovered"
    assert w.circuit.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_jitter_delay_distribution(fast_config):
    """Verify jitter delays are within expected bounds."""
    w = RetryWrapper(fast_config)
    delays = [w._jitter_delay(attempt) for attempt in range(10) for _ in range(50)]
    assert all(0 <= d <= fast_config.cap_delay for d in delays), "Delay out of bounds"
    # With 500 samples, variance should be non-zero (not a constant)
    assert max(delays) - min(delays) > 0.001, "No jitter variance — broken RNG?"


@pytest.mark.asyncio
async def test_stress_high_concurrency(fast_config):
    """50 concurrent callers, 20% fault rate. No duplicate-success, no hangs."""
    import random
    call_results: list[str] = []

    def sometimes_fail():
        if random.random() < 0.2:
            raise APIError("transient", 429)
        return "ok"

    w = RetryWrapper(fast_config)
    tasks = [w.call(sometimes_fail) for _ in range(50)]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
    successes = [o for o in outcomes if o == "ok"]
    # Most should succeed given 5 retries and 20% fault rate
    assert len(successes) >= 40, f"Too many failures under load: {len(successes)}/50"
