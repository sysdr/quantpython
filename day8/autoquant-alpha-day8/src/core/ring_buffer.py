"""
Numpy-backed circular ring buffer for tick price history.

Properties:
- Fixed allocation: numpy array created once at __init__, never resized.
- O(1) writes: single array index write + integer modulo.
- Vectorized reads: returns contiguous numpy slice (no Python loop).
- Zero GC pressure: no Python objects created in the hot path.

Why this matters:
Python list.append() is amortized O(1) but triggers periodic reallocation.
Under HFT conditions (10,000 ticks/sec), a reallocation stall of even 5ms
disrupts the tick processing pipeline. A fixed numpy array eliminates this.
"""
from __future__ import annotations
import numpy as np
from numpy.typing import NDArray


class RingBuffer:
    __slots__ = ("_buf", "_size", "_ptr", "_count", "_dtype")

    def __init__(self, size: int, dtype: type = np.float64) -> None:
        if size <= 0:
            raise ValueError(f"RingBuffer size must be > 0, got {size}")
        self._size:  int      = size
        self._buf:   NDArray  = np.zeros(size, dtype=dtype)
        self._ptr:   int      = 0      # Next write position
        self._count: int      = 0      # Elements written (capped at size)
        self._dtype           = dtype

    def push(self, value: float) -> None:
        """Write value to buffer. O(1). Never allocates."""
        self._buf[self._ptr] = value
        self._ptr = (self._ptr + 1) % self._size
        if self._count < self._size:
            self._count += 1

    def view(self, n: int | None = None) -> NDArray:
        """
        Return last n elements in chronological order (oldest → newest).

        Handles the wrap-around case with exactly 2 numpy slices and
        one np.concatenate — no Python-level loops.
        """
        count = self._count if n is None else min(n, self._count)
        if count == 0:
            return np.empty(0, dtype=self._dtype)

        start = (self._ptr - count) % self._size
        if start + count <= self._size:
            # Contiguous — return direct copy of slice
            return self._buf[start : start + count].copy()
        else:
            # Wrapped — stitch two segments
            tail = self._buf[start:]
            head = self._buf[: count - len(tail)]
            return np.concatenate((tail, head))

    @property
    def is_full(self) -> bool:
        return self._count == self._size

    def __len__(self) -> int:
        return self._count
