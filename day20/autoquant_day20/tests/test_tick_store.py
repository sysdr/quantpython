"""
Unit tests: NumpyTickStore financial math correctness.
Run: python -m pytest tests/test_tick_store.py -v
"""

from __future__ import annotations

import time
import math
import numpy as np
import pytest

from src.data_structures.tick_store import (
    NaiveTickStore, NumpyTickStore, Tick, fnv1a_32, TICK_DTYPE
)


# ── Helpers ───────────────────────────────────────────────────────────────
def make_tick(symbol: str = "AAPL", price: float = 150.0,
              size: int = 100, bid: float = 149.95,
              ask: float = 150.05) -> Tick:
    return Tick(
        symbol=symbol, price=price, size=size,
        timestamp=time.perf_counter_ns(),
        bid=bid, ask=ask,
    )


# ── FNV-1a hash ───────────────────────────────────────────────────────────
def test_fnv1a_deterministic():
    assert fnv1a_32("AAPL") == fnv1a_32("AAPL")

def test_fnv1a_different_symbols():
    assert fnv1a_32("AAPL") != fnv1a_32("MSFT")

def test_fnv1a_range():
    h = fnv1a_32("TSLA")
    assert 0 <= h <= 0xFFFF_FFFF


# ── Tick dataclass ────────────────────────────────────────────────────────
def test_tick_spread_bps():
    tick = make_tick(price=100.0, bid=99.95, ask=100.05)
    # spread = 0.10, mid = 100.0 → 10 bps
    assert abs(tick.spread_bps - 10.0) < 0.01

def test_tick_frozen():
    tick = make_tick()
    with pytest.raises((AttributeError, TypeError)):
        tick.price = 999.0  # type: ignore[misc]

def test_tick_has_slots():
    tick = make_tick()
    assert not hasattr(tick, "__dict__"), "Slotted dataclass must not have __dict__"


# ── NumpyTickStore ────────────────────────────────────────────────────────
def test_numpy_store_append_and_len():
    store = NumpyTickStore(capacity=100)
    for i in range(10):
        store.append(make_tick(price=float(100 + i), size=10))
    assert len(store) == 10

def test_numpy_store_overflow():
    store = NumpyTickStore(capacity=5)
    for _ in range(5):
        store.append(make_tick())
    with pytest.raises(OverflowError):
        store.append(make_tick())

def test_numpy_store_dtype():
    store = NumpyTickStore(capacity=10)
    store.append(make_tick(symbol="AAPL", price=150.0, size=500))
    view = store.get_view()
    assert view.dtype == TICK_DTYPE
    assert view["size"][0] == 500
    assert abs(float(view["price"][0]) - 150.0) < 0.001

def test_numpy_store_memory_bytes():
    cap = 1_000
    store = NumpyTickStore(capacity=cap)
    # Preallocated: full capacity * 28 bytes
    assert store.memory_bytes == cap * TICK_DTYPE.itemsize

def test_numpy_store_vwap_single():
    store = NumpyTickStore(capacity=10)
    store.append(make_tick(price=100.0, size=200))
    assert abs(store.vwap() - 100.0) < 0.001

def test_numpy_store_vwap_weighted():
    store = NumpyTickStore(capacity=10)
    # 100 shares @ $100 + 300 shares @ $200 → VWAP = (10000+60000)/400 = $175
    store.append(make_tick(price=100.0, size=100))
    store.append(make_tick(price=200.0, size=300))
    expected = (100.0 * 100 + 200.0 * 300) / 400.0
    assert abs(store.vwap() - expected) < 0.001

def test_numpy_store_vwap_empty():
    store = NumpyTickStore(capacity=10)
    assert store.vwap() == 0.0

def test_numpy_store_mean_spread_bps():
    store = NumpyTickStore(capacity=10)
    # bid=99.95, ask=100.05 → spread=0.10, mid=100.0 → 10 bps
    for _ in range(5):
        store.append(make_tick(price=100.0, bid=99.95, ask=100.05))
    assert abs(store.mean_spread_bps() - 10.0) < 0.5

def test_numpy_store_zero_copy_view():
    store = NumpyTickStore(capacity=100)
    for i in range(10):
        store.append(make_tick(price=float(100 + i)))
    view = store.get_view()
    assert len(view) == 10
    # Verify the view shares memory with the store's array
    assert view.base is store._data or np.shares_memory(view, store._data)


# ── NaiveTickStore (memory estimates) ─────────────────────────────────────
def test_naive_memory_estimate_proportional():
    store = NaiveTickStore()
    for _ in range(1000):
        store.append(make_tick())
    naive_b = store.memory_estimate_bytes()
    slots_b = store.slots_estimate_bytes()
    assert naive_b > slots_b, "Naive must use more memory than slotted"
    assert naive_b // 1000 >= 100, "Estimate must be realistic (≥100 bytes/tick)"


# ── Cross-store consistency ────────────────────────────────────────────────
def test_symbol_hash_stored_correctly():
    store = NumpyTickStore(capacity=5)
    store.append(make_tick(symbol="AAPL"))
    view = store.get_view()
    assert view["symbol_hash"][0] == fnv1a_32("AAPL")
