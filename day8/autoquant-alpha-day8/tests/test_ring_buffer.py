"""Unit tests — RingBuffer."""
import pytest
import numpy as np
from src.core.ring_buffer import RingBuffer


class TestRingBuffer:

    def test_empty_on_creation(self):
        buf = RingBuffer(size=10)
        assert len(buf) == 0
        assert buf.view().size == 0

    def test_partial_fill_order(self):
        buf = RingBuffer(size=10)
        for i in range(5):
            buf.push(float(i))
        assert len(buf) == 5
        np.testing.assert_array_equal(buf.view(), [0, 1, 2, 3, 4])

    def test_wrap_around_drops_oldest(self):
        buf = RingBuffer(size=5)
        for i in range(8):
            buf.push(float(i))
        assert len(buf) == 5
        np.testing.assert_array_equal(buf.view(), [3, 4, 5, 6, 7])

    def test_view_n_returns_last_n(self):
        buf = RingBuffer(size=10)
        for i in range(10):
            buf.push(float(i))
        np.testing.assert_array_equal(buf.view(n=3), [7, 8, 9])

    def test_view_n_larger_than_count(self):
        buf = RingBuffer(size=10)
        for i in range(4):
            buf.push(float(i))
        result = buf.view(n=10)
        np.testing.assert_array_equal(result, [0, 1, 2, 3])

    def test_is_full(self):
        buf = RingBuffer(size=3)
        assert not buf.is_full
        buf.push(1.0); buf.push(2.0); buf.push(3.0)
        assert buf.is_full
        buf.push(4.0)
        assert buf.is_full  # Still full after overwrite

    def test_dtype_preservation(self):
        buf = RingBuffer(size=5, dtype=np.float32)
        buf.push(1.5)
        assert buf.view().dtype == np.float32

    def test_invalid_size_raises(self):
        with pytest.raises(ValueError):
            RingBuffer(size=0)
        with pytest.raises(ValueError):
            RingBuffer(size=-5)

    def test_multiple_wraps(self):
        """Verify correctness after wrapping the buffer 3x."""
        buf = RingBuffer(size=4)
        for i in range(12):
            buf.push(float(i))
        # Last 4 values should be [8, 9, 10, 11]
        np.testing.assert_array_equal(buf.view(), [8, 9, 10, 11])

    def test_view_returns_copy_not_reference(self):
        """Mutations to view output must not affect buffer."""
        buf = RingBuffer(size=5)
        for i in range(5):
            buf.push(float(i))
        view = buf.view()
        view[0] = 999.0
        np.testing.assert_array_equal(buf.view(), [0, 1, 2, 3, 4])
