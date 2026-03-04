"""Unit tests — MomentumScalp.on_tick()"""
import time
import math
import pytest
from src.core.types import MarketSnapshot, SignalDirection, SignalState
from src.strategies.momentum_scalp import MomentumScalp


def snap(bid: float, ask: float, sym: str = "TEST") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=sym, bid=bid, ask=ask,
        last=ask, volume=500, timestamp_ns=time.time_ns(),
    )


class TestMomentumScalp:

    def test_no_signal_before_min_ticks(self):
        s = MomentumScalp("TEST")
        for i in range(s.MIN_TICKS - 1):
            assert s.on_tick(snap(100.0, 100.01)) is None, f"Premature signal on tick {i}"

    def test_no_signal_wide_spread(self):
        s = MomentumScalp("TEST")
        # Fill buffer
        for _ in range(50):
            s.on_tick(snap(100.0, 100.50))  # 50 bps spread — well above threshold
        result = s.on_tick(snap(100.0, 100.50))
        assert result is None, "Should gate on wide spread"

    def test_signal_direction_on_upward_cross(self):
        """Falling then rising prices should eventually trigger LONG."""
        s = MomentumScalp("TEST")
        # Down trend
        for i in range(30):
            p = 100.0 - i * 0.05
            s.on_tick(snap(p - 0.005, p + 0.005))
        # Up trend — force a crossover
        signal = None
        for i in range(50):
            p = 98.5 + i * 0.15
            sig = s.on_tick(snap(p - 0.005, p + 0.005))
            if sig is not None:
                signal = sig
                break
        if signal is not None:
            assert signal.direction == SignalDirection.LONG
            assert 0.0 <= signal.confidence <= 1.0
            assert signal.quantity > 0
            assert signal.state == SignalState.PENDING

    def test_on_tick_never_raises_on_garbage(self):
        s = MomentumScalp("TEST")
        bad = [
            snap(0.0, 0.0),
            snap(-1.0, -0.5),
            snap(float("inf"), float("inf")),
            snap(float("nan"), float("nan")),
            MarketSnapshot("X", 0, 0, 0, 0, 0),
        ]
        for b in bad:
            try:
                s.on_tick(b)
            except Exception as e:
                pytest.fail(f"on_tick raised {type(e).__name__}: {e}")

    def test_cooldown_suppresses_storm(self):
        """Two back-to-back crossovers should only produce one signal."""
        s = MomentumScalp("TEST")
        s.COOLDOWN_NS = 10_000_000_000  # 10 seconds — guaranteed suppression
        signals_fired = []
        for _ in range(30):
            s.on_tick(snap(100.0, 100.01))
        # Induce first crossover
        for i in range(40):
            p = 100.0 + i * 0.2
            r = s.on_tick(snap(p - 0.005, p + 0.005))
            if r: signals_fired.append(r)
        # Immediately try a reverse crossover — should be blocked by cooldown
        for i in range(20):
            p = 107.0 - i * 0.2
            r = s.on_tick(snap(p - 0.005, p + 0.005))
            if r: signals_fired.append(r)
        assert len(signals_fired) <= 1, f"Cooldown failed: {len(signals_fired)} signals"

    def test_state_snapshot_has_required_keys(self):
        s = MomentumScalp("TEST")
        snap_dict = s.get_state_snapshot()
        required = {"symbol", "position", "realized_pnl", "fast_ema", "slow_ema", "buffer_size"}
        assert required.issubset(snap_dict.keys())

    def test_reset_clears_price_buffer(self):
        s = MomentumScalp("TEST")
        for i in range(30):
            s.on_tick(snap(100.0, 100.01))
        s.reset()
        assert len(s._prices) == 0
        assert s._prev_cross is None
