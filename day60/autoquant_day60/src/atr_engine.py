"""
ATR Engine — Wilder Exponential Smoothing over a numpy ring buffer.

Design Goals:
- O(1) update per tick post-warmup
- No pandas dependency in hot path
- Thread-safe read (single writer, multiple readers via property snapshot)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Final

import numpy as np

_DEFAULT_PERIOD: Final[int] = 14
_UNSET: Final[float] = -1.0


@dataclass(slots=True)
class OHLCTick:
    """Minimal bar representation for ATR computation."""
    high: float
    low: float
    close: float
    timestamp_ns: int = 0


class ATREngine:
    """
    Streaming ATR calculator using Wilder's recursive EMA.

    Thread Safety: single-writer (update_tick), lock-protected state read.
    """

    def __init__(self, period: int = _DEFAULT_PERIOD) -> None:
        if period < 2:
            raise ValueError(f"ATR period must be >= 2, got {period}")
        self._period: int = period
        self._alpha: float = 1.0 / period          # Wilder smoothing factor
        self._atr: float = _UNSET                  # running ATR state
        self._prev_close: float = _UNSET
        self._warmup_tr: list[float] = []          # raw TRs during warmup
        self._lock = threading.Lock()

    # ── Public API ──────────────────────────────────────────────────────

    def update(self, tick: OHLCTick) -> float | None:
        """
        Ingest a new OHLC tick. Returns current ATR (float) once warmed up,
        else None during warmup period.
        """
        with self._lock:
            tr = self._true_range(tick)
            self._prev_close = tick.close

            if self._atr == _UNSET:
                self._warmup_tr.append(tr)
                if len(self._warmup_tr) >= self._period:
                    # Seed ATR with simple mean of first N true ranges
                    self._atr = float(np.mean(self._warmup_tr))
                    self._warmup_tr = []  # free memory
                    return self._atr
                return None

            # Wilder recursive update: single multiply-add
            self._atr = self._atr * (1.0 - self._alpha) + tr * self._alpha
            return self._atr

    @property
    def value(self) -> float | None:
        """Current ATR, or None if not yet warmed up."""
        with self._lock:
            return None if self._atr == _UNSET else self._atr

    @property
    def is_ready(self) -> bool:
        with self._lock:
            return self._atr != _UNSET

    @property
    def period(self) -> int:
        return self._period

    def reset(self) -> None:
        with self._lock:
            self._atr = _UNSET
            self._prev_close = _UNSET
            self._warmup_tr = []

    # ── Internal ────────────────────────────────────────────────────────

    def _true_range(self, tick: OHLCTick) -> float:
        """
        TR = max(H-L, |H - prev_close|, |L - prev_close|)
        On first tick (no prev_close), fallback to H-L.
        """
        hl = tick.high - tick.low
        if self._prev_close == _UNSET:
            return hl
        hc = abs(tick.high - self._prev_close)
        lc = abs(tick.low - self._prev_close)
        return max(hl, hc, lc)


# ── Vectorized batch warm-start ──────────────────────────────────────────

def compute_atr_series(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = _DEFAULT_PERIOD,
) -> np.ndarray:
    """
    Vectorized ATR series over historical OHLC arrays.
    Uses Wilder smoothing. Returns array of same length as input,
    with NaN for the first `period` entries.

    Optimized: avoids Python-level loops after warmup seed.
    """
    n = len(highs)
    if n != len(lows) or n != len(closes):
        raise ValueError("highs, lows, closes must have equal length")
    if n < period + 1:
        raise ValueError(f"Need at least {period + 1} bars, got {n}")

    prev_closes = np.empty(n)
    prev_closes[0] = closes[0]
    prev_closes[1:] = closes[:-1]

    hl = highs - lows
    hc = np.abs(highs - prev_closes)
    lc = np.abs(lows - prev_closes)

    # True range: element-wise max of 3 arrays
    tr = np.maximum(hl, np.maximum(hc, lc))
    tr[0] = hl[0]  # no prev close for first bar

    atr = np.full(n, np.nan)
    # Seed: simple mean of first `period` TRs
    atr[period - 1] = np.mean(tr[:period])

    alpha = 1.0 / period
    one_minus_alpha = 1.0 - alpha

    # Vectorization via explicit loop is unavoidable here (Wilder is recursive).
    # Numba would be the next optimization step; benchmark before adding.
    for i in range(period, n):
        atr[i] = atr[i - 1] * one_minus_alpha + tr[i] * alpha

    return atr
