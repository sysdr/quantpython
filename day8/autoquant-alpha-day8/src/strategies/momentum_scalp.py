"""
MomentumScalp: EMA-crossover momentum strategy.

Signal Logic:
─────────────
1. Maintain a 100-slot ring buffer of mid-prices.
2. Compute EMA(5) and EMA(20) from the buffer on every tick.
3. Detect direction change (cross) between fast and slow EMA.
4. Gate signal on:
   a. Minimum buffer depth (25 ticks for EMA warm-up)
   b. Spread threshold (< 10 bps — don't trade a wide book)
   c. Cooldown (500ms between signals — prevents signal storms)
   d. Position limit (no stacking beyond max_position)

Performance target: on_tick() completes in < 500µs (P99).
"""
from __future__ import annotations
import time
from typing import Optional
import numpy as np

from ..core.interface import OnTickInterface
from ..core.types import MarketSnapshot, Signal, SignalDirection, SignalState
from ..core.ring_buffer import RingBuffer
from ..core.state import StrategyState


def _ema(prices: np.ndarray, period: int) -> float:
    """
    Compute EMA(period) over the full prices array.

    Re-computed from scratch on each call (no incremental state).
    This avoids floating-point drift that accumulates in long-running
    incremental EMAs. Input is a fixed-size numpy slice — cost is
    constant and bounded regardless of how long the system has been running.
    """
    if len(prices) == 0:
        return 0.0
    if len(prices) < period:
        return float(np.mean(prices))
    k    = 2.0 / (period + 1)
    ema  = float(prices[0])
    for p in prices[1:]:
        ema = float(p) * k + ema * (1.0 - k)
    return ema


class MomentumScalp(OnTickInterface):
    """
    Concrete strategy implementing OnTickInterface.

    Parameters
    ----------
    symbol       : Ticker to trade (e.g. "AAPL").
    max_position : Hard position limit. Signals suppressed at limit.
    """

    # ── Tunable Parameters ─────────────────────────────────────────────
    MAX_SPREAD_BPS:  float = 10.0
    FAST_PERIOD:     int   = 5
    SLOW_PERIOD:     int   = 20
    MIN_TICKS:       int   = 25        # EMA warm-up period
    COOLDOWN_NS:     int   = 500_000_000  # 500 ms in nanoseconds
    BUFFER_SIZE:     int   = 100

    def __init__(self, symbol: str, max_position: int = 100) -> None:
        self.symbol       = symbol
        self.max_position = max_position
        self._prices      = RingBuffer(size=self.BUFFER_SIZE)
        self._state       = StrategyState(symbol=symbol)
        self._prev_cross: Optional[str] = None   # "above" | "below"
        self._last_fast:  float = 0.0
        self._last_slow:  float = 0.0
        self._cost_basis: float = 0.0   # Simple average entry price

    # ── Hot Path ───────────────────────────────────────────────────────
    def on_tick(self, snapshot: MarketSnapshot) -> Optional[Signal]:
        """
        Core signal-generation logic. Target latency: < 500µs (P99).

        Never raises. All exceptions are caught and return None to
        prevent them from propagating up and crashing the event loop.
        """
        try:
            # ── 1. Update price buffer ─────────────────────────────────
            self._prices.push(snapshot.mid)

            # ── 2. Warm-up gate ────────────────────────────────────────
            if len(self._prices) < self.MIN_TICKS:
                return None

            # ── 3. Compute EMAs (vectorized numpy path) ────────────────
            prices    = self._prices.view()
            fast_ema  = _ema(prices, self.FAST_PERIOD)
            slow_ema  = _ema(prices, self.SLOW_PERIOD)

            # ── 4. Crossover detection ─────────────────────────────────
            current_cross = "above" if fast_ema > slow_ema else "below"
            cross_occurred = (
                self._prev_cross is not None and
                current_cross != self._prev_cross
            )
            prev_cross       = self._prev_cross
            self._prev_cross = current_cross
            self._last_fast  = fast_ema
            self._last_slow  = slow_ema

            if not cross_occurred:
                return None

            # ── 5. Spread gate ─────────────────────────────────────────
            if snapshot.spread_bps > self.MAX_SPREAD_BPS:
                return None

            # ── 6. Cooldown gate ───────────────────────────────────────
            now_ns = time.time_ns()
            if (self._state.last_signal_at_ns is not None and
                    now_ns - self._state.last_signal_at_ns < self.COOLDOWN_NS):
                return None

            # ── 7. Position limit gate ─────────────────────────────────
            if abs(self._state.position) >= self.max_position:
                return None

            # ── 8. Construct Signal ────────────────────────────────────
            direction = (
                SignalDirection.LONG
                if current_cross == "above"
                else SignalDirection.SHORT
            )
            ref_price = snapshot.ask if direction == SignalDirection.LONG else snapshot.bid

            # Confidence: EMA separation as fraction of price, capped at 1.0
            confidence = 0.5
            if slow_ema != 0.0:
                confidence = min(abs(fast_ema - slow_ema) / slow_ema * 100.0, 1.0)

            self._state.record_signal(now_ns)

            return Signal(
                symbol          = snapshot.symbol,
                direction       = direction,
                confidence      = round(confidence, 4),
                reference_price = ref_price,
                quantity        = 10,
                state           = SignalState.PENDING,
            )

        except Exception:
            # Swallow ALL exceptions. Log externally via the execution layer.
            # This function must never propagate.
            return None

    # ── Lifecycle ──────────────────────────────────────────────────────
    def reset(self) -> None:
        """Called on WebSocket reconnection. Clears price history."""
        self._prices     = RingBuffer(size=self.BUFFER_SIZE)
        self._prev_cross = None
        self._last_fast  = 0.0
        self._last_slow  = 0.0

    def get_state_snapshot(self) -> dict:
        state = self._state.to_dict()
        state.update({
            "fast_ema":    round(self._last_fast, 4),
            "slow_ema":    round(self._last_slow, 4),
            "buffer_size": len(self._prices),
            "prev_cross":  self._prev_cross or "none",
        })
        return state
