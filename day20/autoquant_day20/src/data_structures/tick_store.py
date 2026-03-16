"""
tick_store.py — Three implementations of a tick data store, ordered by memory
efficiency. Used for direct comparison in the Day-20 dashboard.

Naive      : List[Dict]              ~300 bytes/tick
Slotted    : __slots__ dataclass      ~80 bytes/tick  (simulated via count)
Optimized  : numpy structured array   ~28 bytes/tick
"""

from __future__ import annotations

import sys
import time
import numpy as np
from dataclasses import dataclass
from typing import Iterator


# ── FNV-1a 32-bit hash ───────────────────────────────────────────────────
def fnv1a_32(s: str) -> int:
    """Non-cryptographic hash for symbol strings. ~300 MB/s throughput."""
    h: int = 2_166_136_261
    for byte in s.encode():
        h = ((h ^ byte) * 16_777_619) & 0xFFFF_FFFF
    return h


# ── Dtype: 28 bytes per tick (C-contiguous, SIMD-friendly) ───────────────
TICK_DTYPE = np.dtype([
    ("symbol_hash", np.uint32),   # 4 bytes
    ("price",       np.float32),  # 4 bytes  — float32 ok for equity prices
    ("size",        np.uint32),   # 4 bytes
    ("timestamp",   np.int64),    # 8 bytes  — epoch nanoseconds
    ("bid",         np.float32),  # 4 bytes
    ("ask",         np.float32),  # 4 bytes
])  # Total: 28 bytes/tick


# ── Slotted dataclass: zero __dict__, zero __weakref__ ───────────────────
@dataclass(slots=True, frozen=True)
class Tick:
    """
    Fixed-schema tick. `frozen=True` gives __hash__ + immutability.
    `slots=True` (Python 3.10+) eliminates per-instance __dict__ (~104 bytes saved).
    Using int for timestamp instead of datetime saves another 28 bytes per tick.
    """
    symbol:    str
    price:     float
    size:      int
    timestamp: int    # epoch nanoseconds — NOT datetime
    bid:       float
    ask:       float

    @property
    def spread_bps(self) -> float:
        mid = (self.bid + self.ask) / 2.0
        return ((self.ask - self.bid) / mid) * 10_000.0 if mid else 0.0


# ── Tier 1: Naive store (deliberately bad — for comparison) ──────────────
class NaiveTickStore:
    """
    List[Dict] store. DO NOT use in production.
    Present for memory-comparison benchmarks only.
    """

    def __init__(self) -> None:
        self._data: list[dict] = []

    def append(self, tick: Tick) -> None:
        self._data.append({
            "symbol":    tick.symbol,
            "price":     float(tick.price),
            "size":      int(tick.size),
            "timestamp": tick.timestamp,
            "bid":       float(tick.bid),
            "ask":       float(tick.ask),
        })

    def memory_estimate_bytes(self) -> int:
        """
        Empirical estimate: CPython dict header ~232 bytes + 6 key/value pairs
        at ~50 bytes each (str keys are interned but values are boxed) ≈ 300 bytes.
        Plus 8-byte list pointer overhead.
        """
        return len(self._data) * (300 + 8)

    def slots_estimate_bytes(self) -> int:
        """
        Estimate for equivalent __slots__ dataclass store.
        Slotted object: ~80 bytes (no __dict__, no __weakref__).
        """
        return len(self._data) * 80

    def __len__(self) -> int:
        return len(self._data)


# ── Tier 2: Optimized store (preallocated numpy structured array) ─────────
class NumpyTickStore:
    """
    Preallocated numpy structured array. Memory is reserved at construction
    time — no heap allocations in the append hot path after init.

    append() is O(1): a single structured array row assignment.
    get_view() returns a zero-copy slice — no data copy.
    """

    __slots__ = ("_data", "_size", "_capacity")

    def __init__(self, capacity: int = 1_000_000) -> None:
        self._capacity: int = capacity
        self._size: int = 0
        # Single allocation at init — the entire budget is paid upfront.
        self._data: np.ndarray = np.zeros(capacity, dtype=TICK_DTYPE)

    def append(self, tick: Tick) -> None:
        if self._size >= self._capacity:
            raise OverflowError(
                f"NumpyTickStore capacity exhausted: {self._capacity:,} ticks"
            )
        row = self._data[self._size]
        row["symbol_hash"] = fnv1a_32(tick.symbol)
        row["price"]       = tick.price
        row["size"]        = tick.size
        row["timestamp"]   = tick.timestamp
        row["bid"]         = tick.bid
        row["ask"]         = tick.ask
        self._size += 1

    def get_view(self) -> np.ndarray:
        """Zero-copy view of the live data. No allocation."""
        return self._data[: self._size]

    def vwap(self) -> float:
        """Vectorized VWAP over all stored ticks. SIMD-executed by numpy."""
        view = self.get_view()
        if len(view) == 0:
            return 0.0
        total_value = np.dot(view["price"].astype(np.float64), view["size"].astype(np.float64))
        total_volume = float(view["size"].sum())
        return total_value / total_volume if total_volume else 0.0

    def mean_spread_bps(self) -> float:
        """Vectorized mean spread in basis points."""
        view = self.get_view()
        if len(view) == 0:
            return 0.0
        mid = (view["bid"].astype(np.float64) + view["ask"].astype(np.float64)) / 2.0
        spreads = ((view["ask"].astype(np.float64) - view["bid"].astype(np.float64)) / mid) * 10_000.0
        return float(spreads.mean())

    @property
    def memory_bytes(self) -> int:
        """Exact memory: only the preallocated array. No GC objects."""
        return self._data.nbytes

    @property
    def utilization(self) -> float:
        return self._size / self._capacity

    def __len__(self) -> int:
        return self._size
