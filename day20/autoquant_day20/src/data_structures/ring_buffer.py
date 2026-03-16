"""
ring_buffer.py — Lock-free ring buffer using array.array.

array.array is a thin C-array wrapper:
  - No per-element GC objects (unlike list)
  - Direct memoryview support (zero-copy reads)
  - Fits in L1/L2 cache for small capacities
  - ~4 bytes/element for float32 vs ~28 bytes for a Python float in a list
"""

from __future__ import annotations

from array import array
import numpy as np


class Float32RingBuffer:
    """
    Circular buffer for single-channel float32 streams (spread, latency, etc.)
    Capacity must be a power of 2 for bitmask-based index arithmetic.
    """

    __slots__ = ("_buf", "_head", "_tail", "_size", "_capacity", "_mask")

    def __init__(self, capacity: int = 4096) -> None:
        if capacity & (capacity - 1) != 0:
            raise ValueError(f"capacity must be a power of 2, got {capacity}")
        self._capacity: int = capacity
        self._mask: int = capacity - 1
        self._buf: array = array("f", [0.0] * capacity)
        self._head: int = 0
        self._tail: int = 0
        self._size: int = 0

    def push(self, value: float) -> None:
        """O(1) push. Overwrites oldest element when full."""
        self._buf[self._tail] = value
        self._tail = (self._tail + 1) & self._mask
        if self._size == self._capacity:
            self._head = (self._head + 1) & self._mask
        else:
            self._size += 1

    def to_numpy(self) -> np.ndarray:
        """
        Zero-copy path when buffer is not wrapped.
        Allocates a contiguous array when wrapped (unavoidable).
        """
        n = self._size
        if n == 0:
            return np.empty(0, dtype=np.float32)

        # array("f") already exposes float32-compatible buffer; no recast needed.
        mv = memoryview(self._buf)

        if self._head + n <= self._capacity:
            # Contiguous segment — true zero-copy via frombuffer
            return np.frombuffer(mv[self._head: self._head + n], dtype=np.float32).copy()

        # Wrapped: two segments — one allocation unavoidable
        out = np.empty(n, dtype=np.float32)
        first = self._capacity - self._head
        out[:first] = np.frombuffer(mv[self._head:], dtype=np.float32)
        out[first:] = np.frombuffer(mv[: self._tail], dtype=np.float32)
        return out

    def mean(self) -> float:
        if self._size == 0:
            return 0.0
        return float(self.to_numpy().mean())

    def percentile(self, q: float) -> float:
        if self._size == 0:
            return 0.0
        return float(np.percentile(self.to_numpy(), q))

    @property
    def memory_bytes(self) -> int:
        info = self._buf.buffer_info()
        return info[1] * self._buf.itemsize  # n_elements * 4 bytes

    def __len__(self) -> int:
        return self._size
