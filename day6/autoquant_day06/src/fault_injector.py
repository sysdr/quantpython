"""
Fault injection harness for stress testing the RetryWrapper.
Simulates real API failure profiles without hitting live endpoints.
"""

from __future__ import annotations

import random
from typing import Any
from retry_wrapper import APIError


class FaultInjector:
    """
    Wraps a real callable and injects failures at a controlled rate.
    Supports burst mode (simulate outage windows) and rate-limit profiles.
    """

    def __init__(
        self,
        real_func: Any,
        failure_rate: float = 0.3,
        status_code: int = 429,
        burst_at: int | None = None,
        burst_duration: int = 3,
    ) -> None:
        self._func = real_func
        self._failure_rate = failure_rate
        self._status_code = status_code
        self._burst_at = burst_at
        self._burst_duration = burst_duration
        self._call_count = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self._call_count += 1

        in_burst = (
            self._burst_at is not None
            and self._burst_at <= self._call_count < self._burst_at + self._burst_duration
        )

        if in_burst or random.random() < self._failure_rate:
            raise APIError(
                f"Injected fault (call #{self._call_count})",
                status_code=self._status_code,
            )

        return self._func(*args, **kwargs)
