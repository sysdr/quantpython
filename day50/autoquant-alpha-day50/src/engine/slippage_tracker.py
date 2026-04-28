"""
Ring-buffer slippage tracker using NumPy vectorized ops.
No Python loops in the hot path. Thread-safe for single-writer.
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class SlippageStats:
    count: int
    mean_bps: float
    std_bps: float
    p50_bps: float
    p95_bps: float
    p99_bps: float
    worst_bps: float


class SlippageTracker:
    """
    Fixed-size ring buffer storing slippage_bps as float64.
    Window=500 → 4KB footprint, negligible GC pressure.
    """

    __slots__ = ("_buf", "_idx", "_count", "_window")

    def __init__(self, window: int = 500) -> None:
        self._window = window
        self._buf: np.ndarray = np.full(window, np.nan, dtype=np.float64)
        self._idx: int = 0
        self._count: int = 0

    def record(self, slippage_bps: float) -> None:
        self._buf[self._idx % self._window] = slippage_bps
        self._idx += 1
        self._count = min(self._count + 1, self._window)

    def stats(self) -> SlippageStats:
        valid = self._buf[: self._count] if self._count < self._window else self._buf
        valid = valid[~np.isnan(valid)]
        if len(valid) == 0:
            return SlippageStats(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        return SlippageStats(
            count=len(valid),
            mean_bps=float(np.mean(valid)),
            std_bps=float(np.std(valid)),
            p50_bps=float(np.percentile(valid, 50)),
            p95_bps=float(np.percentile(valid, 95)),
            p99_bps=float(np.percentile(valid, 99)),
            worst_bps=float(np.max(valid)),
        )

    def is_alarming(self, threshold_bps: float = 5.0) -> bool:
        s = self.stats()
        return s.mean_bps > threshold_bps or s.p99_bps > threshold_bps * 3

    def reset(self) -> None:
        self._buf[:] = np.nan
        self._idx = 0
        self._count = 0
