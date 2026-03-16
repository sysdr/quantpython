"""
Unit tests: Float32RingBuffer correctness and memory properties.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.data_structures.ring_buffer import Float32RingBuffer


def test_push_and_len():
    buf = Float32RingBuffer(capacity=8)
    for i in range(5):
        buf.push(float(i))
    assert len(buf) == 5

def test_capacity_enforcement():
    buf = Float32RingBuffer(capacity=4)
    for i in range(8):
        buf.push(float(i))
    assert len(buf) == 4  # capped at capacity

def test_overwrite_oldest():
    buf = Float32RingBuffer(capacity=4)
    for i in range(6):   # push 0,1,2,3,4,5
        buf.push(float(i))
    arr = buf.to_numpy()
    # Oldest 2 evicted → should contain [2,3,4,5]
    assert set(arr.tolist()) == {2.0, 3.0, 4.0, 5.0}

def test_to_numpy_values():
    buf = Float32RingBuffer(capacity=8)
    values = [1.1, 2.2, 3.3, 4.4]
    for v in values:
        buf.push(v)
    arr = buf.to_numpy()
    assert len(arr) == 4
    np.testing.assert_allclose(arr, values, rtol=1e-5)

def test_non_power_of_two_raises():
    with pytest.raises(ValueError):
        Float32RingBuffer(capacity=100)

def test_mean():
    buf = Float32RingBuffer(capacity=8)
    for v in [1.0, 2.0, 3.0, 4.0]:
        buf.push(v)
    assert abs(buf.mean() - 2.5) < 1e-4

def test_memory_bytes():
    buf = Float32RingBuffer(capacity=1024)
    assert buf.memory_bytes == 1024 * 4  # float32 = 4 bytes each

def test_empty_numpy():
    buf = Float32RingBuffer(capacity=8)
    arr = buf.to_numpy()
    assert len(arr) == 0
