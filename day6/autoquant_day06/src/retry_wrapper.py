"""
AutoQuant-Alpha | Day 6
Production-grade async retry wrapper with circuit breaker.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import partial
from typing import Any, Callable
import structlog

log = structlog.get_logger(__name__)


class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


class CircuitOpenError(RuntimeError):
    """Raised when a request is rejected by an open circuit."""


class MaxRetriesExceeded(RuntimeError):
    """Raised when all retry attempts are exhausted."""


class APIError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 5
    base_delay: float = 0.5
    cap_delay: float = 30.0
    retryable_codes: frozenset[int] = frozenset({429, 500, 502, 503, 504})
    circuit_open_duration: float = 60.0
    failure_threshold: int = 3


@dataclass
class CircuitBreaker:
    config: RetryConfig
    state: CircuitState = CircuitState.CLOSED
    _failures: int = field(default=0, repr=False)
    _last_failure_time: float = field(default=0.0, repr=False)
    _total_trips: int = field(default=0, repr=False)

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            log.info("circuit.closed", previous_state="HALF_OPEN")
        self.state = CircuitState.CLOSED
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure_time = time.monotonic()
        if self._failures >= self.config.failure_threshold:
            if self.state != CircuitState.OPEN:
                self._total_trips += 1
                log.warning(
                    "circuit.opened",
                    failures=self._failures,
                    trip_count=self._total_trips,
                )
            self.state = CircuitState.OPEN

    def should_attempt_reset(self) -> bool:
        elapsed = time.monotonic() - self._last_failure_time
        return elapsed >= self.config.circuit_open_duration

    @property
    def trip_count(self) -> int:
        return self._total_trips


class RetryWrapper:
    """
    Async-first retry wrapper with exponential backoff (full jitter)
    and integrated circuit breaker.
    """

    def __init__(self, config: RetryConfig | None = None) -> None:
        self.config = config or RetryConfig()
        self.circuit = CircuitBreaker(config=self.config)
        self._call_count = 0
        self._retry_count = 0

    def _jitter_delay(self, attempt: int) -> float:
        """AWS full-jitter: uniform sample from [0, min(cap, base * 2^attempt)]"""
        exponential = self.config.base_delay * (2 ** attempt)
        capped = min(self.config.cap_delay, exponential)
        return random.uniform(0, capped)

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute func(*args, **kwargs) with retry + circuit breaker.
        func may be synchronous; it is dispatched via run_in_executor to
        avoid blocking the event loop.
        """
        self._call_count += 1

        if self.circuit.state == CircuitState.OPEN:
            if self.circuit.should_attempt_reset():
                self.circuit.state = CircuitState.HALF_OPEN
                log.info("circuit.half_open")
            else:
                raise CircuitOpenError(
                    f"Circuit is OPEN — failing fast "
                    f"(trips={self.circuit.trip_count})"
                )

        loop = asyncio.get_event_loop()
        last_exc: Exception | None = None

        for attempt in range(self.config.max_attempts):
            try:
                result = await loop.run_in_executor(
                    None, partial(func, *args, **kwargs)
                )
                self.circuit.record_success()
                log.debug(
                    "api.call.success",
                    attempt=attempt,
                    func=func.__name__,
                )
                return result

            except APIError as exc:
                last_exc = exc
                if exc.status_code not in self.config.retryable_codes:
                    log.error(
                        "api.call.non_retryable",
                        status_code=exc.status_code,
                        func=func.__name__,
                    )
                    raise

                self.circuit.record_failure()
                self._retry_count += 1

                if self.circuit.state == CircuitState.OPEN:
                    log.warning(
                        "api.call.circuit_tripped",
                        attempt=attempt,
                        func=func.__name__,
                    )
                    raise CircuitOpenError("Circuit tripped mid-retry sequence") from exc

                if attempt < self.config.max_attempts - 1:
                    delay = self._jitter_delay(attempt)
                    log.warning(
                        "api.call.retry",
                        attempt=attempt + 1,
                        max_attempts=self.config.max_attempts,
                        delay_s=round(delay, 3),
                        status_code=exc.status_code,
                    )
                    await asyncio.sleep(delay)

        raise MaxRetriesExceeded(
            f"Exhausted {self.config.max_attempts} attempts"
        ) from last_exc

    @property
    def retry_rate(self) -> float:
        if self._call_count == 0:
            return 0.0
        return self._retry_count / self._call_count

    def stats(self) -> dict[str, Any]:
        return {
            "call_count": self._call_count,
            "retry_count": self._retry_count,
            "retry_rate": round(self.retry_rate, 4),
            "circuit_state": self.circuit.state.name,
            "circuit_trips": self.circuit.trip_count,
        }
