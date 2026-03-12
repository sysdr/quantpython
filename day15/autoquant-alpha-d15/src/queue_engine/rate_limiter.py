"""
Async Token Bucket Rate Limiter.

Alpaca paper trading: ~200 req/min sustained, burst ~20.
Set rate=3.33, capacity=20 to stay safely under limits.

The token bucket algorithm:
- Tokens refill continuously at `rate` tokens/second (up to `capacity`)
- Each API call consumes one token
- If no tokens available: sleep exactly long enough for one token to refill
- Result: smooth throughput within limit, handles bursts gracefully
"""

from __future__ import annotations

import asyncio
import time


class TokenBucketRateLimiter:

    def __init__(self, rate: float, capacity: float) -> None:
        """
        Args:
            rate:     Tokens added per second (sustained throughput limit).
            capacity: Maximum tokens in bucket (burst size).
        """
        if rate <= 0 or capacity <= 0:
            raise ValueError("rate and capacity must be positive")
        self._rate     = rate
        self._capacity = capacity
        self._tokens   = capacity          # Start full for immediate burst
        self._last_refill = time.monotonic()
        self._lock     = asyncio.Lock()

    async def acquire(self) -> float:
        """
        Acquire one token. Suspends until available.
        Returns: actual wait time in seconds (0.0 if token was immediately available).
        Useful for latency tracking and rate-limit pressure alerting.
        """
        async with self._lock:
            total_wait = 0.0
            while True:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return total_wait
                # Precise sleep: wait exactly for one token
                deficit  = 1.0 - self._tokens
                sleep_s  = deficit / self._rate
                await asyncio.sleep(sleep_s)
                total_wait += sleep_s

    def _refill(self) -> None:
        now     = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._capacity,
            self._tokens + elapsed * self._rate,
        )
        self._last_refill = now

    @property
    def available_tokens(self) -> float:
        """Non-destructive peek at current token count. Triggers a refill."""
        self._refill()
        return self._tokens
