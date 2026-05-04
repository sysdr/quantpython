"""
timer.py — High-resolution latency recording primitives.

Design rationale:
  • time.perf_counter_ns()  : monotonic, nanosecond resolution, CLOCK_MONOTONIC.
  • NamedTuple for samples  : immutable, compact memory layout, no __dict__.
  • deque(maxlen=N)         : O(1) append + eviction, bounded memory.
  • numpy for aggregation   : vectorized percentiles, never blocks hot path.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np


class LatencySample(NamedTuple):
    """Immutable record of a single order round-trip measurement."""

    order_id: str
    t1_ns: int  # perf_counter_ns() immediately before I/O syscall
    t2_ns: int  # perf_counter_ns() immediately after I/O syscall returns

    @property
    def latency_us(self) -> float:
        """Latency in microseconds. Raises ValueError if negative (clock fault)."""
        delta = self.t2_ns - self.t1_ns
        if delta < 0:
            raise ValueError(
                f"Negative latency detected for order {self.order_id}: "
                f"delta={delta}ns. Non-monotonic clock source suspected."
            )
        return delta / 1_000.0

    @property
    def latency_ms(self) -> float:
        return self.latency_us / 1_000.0

    def to_dict(self) -> dict[str, object]:
        return {
            "order_id": self.order_id,
            "t1_ns": self.t1_ns,
            "t2_ns": self.t2_ns,
            "latency_us": self.latency_us,
        }


@dataclass
class LatencyRecorder:
    """
    Ring-buffer backed latency recorder.

    Thread safety: deque.append() is atomic under CPython's GIL for a
    single writer. If you have multiple writer threads, subclass this and
    wrap _buffer access with threading.Lock. See homework in lesson_article.md.
    """

    maxlen: int = 10_000

    def __post_init__(self) -> None:
        self._buffer: deque[LatencySample] = deque(maxlen=self.maxlen)
        self._negative_count: int = 0

    def record(self, order_id: str, t1_ns: int, t2_ns: int) -> LatencySample:
        """Stamp a sample and push to ring buffer. O(1). Never blocks."""
        sample = LatencySample(order_id=order_id, t1_ns=t1_ns, t2_ns=t2_ns)
        # Detect clock fault without raising — log and continue
        if sample.t2_ns < sample.t1_ns:
            self._negative_count += 1
        self._buffer.append(sample)
        return sample

    def snapshot(self) -> np.ndarray:
        """
        Return a numpy float64 array of valid latency samples in microseconds.
        Negative samples are excluded (clock fault artefacts).
        """
        valid = [s.latency_us for s in self._buffer if s.t2_ns >= s.t1_ns]
        return np.array(valid, dtype=np.float64)

    def percentiles(self) -> dict[str, float]:
        """Vectorized percentile aggregation. Call off the hot path."""
        arr = self.snapshot()
        if arr.size == 0:
            return {
                "p50": 0.0, "p95": 0.0, "p99": 0.0,
                "min": 0.0, "max": 0.0,
                "count": 0.0, "negative": float(self._negative_count),
            }
        return {
            "p50":     float(np.percentile(arr, 50)),
            "p95":     float(np.percentile(arr, 95)),
            "p99":     float(np.percentile(arr, 99)),
            "min":     float(arr.min()),
            "max":     float(arr.max()),
            "count":   float(arr.size),
            "negative": float(self._negative_count),
        }

    def histogram_bins(self, n_bins: int = 10) -> tuple[np.ndarray, np.ndarray]:
        """Return (bin_edges, counts) for a Rich sparkline."""
        arr = self.snapshot()
        if arr.size == 0:
            return np.array([]), np.array([])
        counts, edges = np.histogram(arr, bins=n_bins)
        return edges, counts

    @property
    def saturation(self) -> float:
        """Fraction of ring buffer used. 1.0 = full, oldest samples evicted."""
        return len(self._buffer) / self.maxlen

    def __len__(self) -> int:
        return len(self._buffer)
