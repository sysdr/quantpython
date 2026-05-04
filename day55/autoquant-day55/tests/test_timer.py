"""
Unit tests for timer.py

Run: pytest tests/test_timer.py -v
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from src.timer import LatencyRecorder, LatencySample


# ── LatencySample ─────────────────────────────────────────────────────────────

class TestLatencySample:
    def test_latency_us_correct(self) -> None:
        s = LatencySample("order-1", 1_000_000, 1_500_000)
        assert s.latency_us == pytest.approx(500.0)

    def test_latency_ms_correct(self) -> None:
        s = LatencySample("order-1", 0, 1_000_000_000)
        assert s.latency_ms == pytest.approx(1_000.0)

    def test_negative_latency_raises(self) -> None:
        s = LatencySample("order-bad", 1_500_000, 1_000_000)
        with pytest.raises(ValueError, match="Negative latency"):
            _ = s.latency_us

    def test_zero_latency_is_valid(self) -> None:
        s = LatencySample("order-z", 5_000, 5_000)
        assert s.latency_us == pytest.approx(0.0)

    def test_to_dict_contains_keys(self) -> None:
        s = LatencySample("ord-x", 1000, 2000)
        d = s.to_dict()
        assert {"order_id", "t1_ns", "t2_ns", "latency_us"} <= d.keys()


# ── LatencyRecorder ───────────────────────────────────────────────────────────

class TestLatencyRecorder:
    def test_record_and_len(self) -> None:
        rec = LatencyRecorder(maxlen=100)
        rec.record("a", 0, 1_000_000)
        rec.record("b", 0, 2_000_000)
        assert len(rec) == 2

    def test_ring_buffer_bounded(self) -> None:
        rec = LatencyRecorder(maxlen=5)
        for i in range(10):
            rec.record(str(i), 0, i * 1_000_000)
        assert len(rec) == 5

    def test_oldest_evicted(self) -> None:
        rec = LatencyRecorder(maxlen=3)
        for i in range(5):
            rec.record(str(i), 0, (i + 1) * 1_000)
        ids = [s.order_id for s in rec._buffer]
        assert ids == ["2", "3", "4"]

    def test_snapshot_excludes_negatives(self) -> None:
        rec = LatencyRecorder(maxlen=10)
        rec.record("good", 100, 200)
        # Manually inject a "negative" sample by bypassing record()
        from src.timer import LatencySample
        rec._buffer.append(LatencySample("bad", 200, 100))
        arr = rec.snapshot()
        assert arr.size == 1
        assert arr[0] == pytest.approx((200 - 100) / 1_000.0)

    def test_percentiles_correct(self) -> None:
        rec = LatencyRecorder(maxlen=1000)
        # Insert 100 samples: 1µs to 100µs
        for i in range(1, 101):
            rec.record(str(i), 0, i * 1_000)
        p = rec.percentiles()
        assert p["p50"] == pytest.approx(50.5, abs=1.0)
        assert p["p99"] == pytest.approx(99.0, abs=2.0)
        assert p["min"] == pytest.approx(1.0, abs=0.1)
        assert p["max"] == pytest.approx(100.0, abs=0.1)

    def test_empty_percentiles_returns_zeros(self) -> None:
        rec = LatencyRecorder()
        p = rec.percentiles()
        assert p["count"] == 0.0

    def test_saturation(self) -> None:
        rec = LatencyRecorder(maxlen=10)
        for i in range(5):
            rec.record(str(i), 0, 1_000)
        assert rec.saturation == pytest.approx(0.5)

    def test_perf_counter_ns_monotonic(self) -> None:
        """Sanity check: perf_counter_ns never decreases."""
        samples = [time.perf_counter_ns() for _ in range(1000)]
        deltas = [samples[i+1] - samples[i] for i in range(len(samples)-1)]
        assert all(d >= 0 for d in deltas), "perf_counter_ns is not monotonic!"

    def test_negative_count_tracked(self) -> None:
        rec = LatencyRecorder(maxlen=10)
        rec.record("neg", 1000, 500)  # t2 < t1
        assert rec._negative_count == 1
        p = rec.percentiles()
        assert p["negative"] == 1.0
