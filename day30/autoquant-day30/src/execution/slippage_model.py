"""
SlippageModel
-------------
Maintains a rolling window of realized slippage observations and computes
distributional statistics.  Raises SlippageBreachError if p99 exceeds
the configured alert threshold — preventing new orders during high-friction
regimes.

Regime Logic:
  - NORMAL  : rolling p50_abs_bps < 3.0
  - ELEVATED: 3.0 <= rolling p50_abs_bps < 8.0
  - HIGH    : rolling p50_abs_bps >= 8.0 → switch to limit orders (Day 31)
"""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto


class SlippageRegime(Enum):
    NORMAL = auto()
    ELEVATED = auto()
    HIGH = auto()


class SlippageBreachError(RuntimeError):
    """Raised when p99 slippage exceeds the alert threshold."""


@dataclass(frozen=True)
class SlippageStats:
    n: int
    p50_bps: float
    p99_bps: float
    mean_bps: float
    max_bps: float
    regime: SlippageRegime


class SlippageModel:
    """Rolling slippage tracker with regime detection."""

    def __init__(
        self,
        window: int = 100,
        alert_threshold_bps: float = 15.0,
    ) -> None:
        self._window = window
        self._alert_threshold = alert_threshold_bps
        self._observations: deque[float] = deque(maxlen=window)
        self._regime: SlippageRegime = SlippageRegime.NORMAL

    def record(self, slippage_bps: Decimal) -> SlippageStats:
        """Add one observation and recompute stats."""
        self._observations.append(float(slippage_bps))
        stats = self.compute_stats()

        if stats.p99_bps > self._alert_threshold:
            raise SlippageBreachError(
                f"p99 slippage {stats.p99_bps:.2f} bps exceeds threshold "
                f"{self._alert_threshold:.2f} bps — halt new market orders"
            )

        self._regime = stats.regime
        return stats

    def compute_stats(self) -> SlippageStats:
        if not self._observations:
            return SlippageStats(
                n=0,
                p50_bps=0.0,
                p99_bps=0.0,
                mean_bps=0.0,
                max_bps=0.0,
                regime=SlippageRegime.NORMAL,
            )

        obs = sorted(self._observations)
        n = len(obs)

        def percentile(sorted_data: list[float], pct: float) -> float:
            idx = (pct / 100) * (len(sorted_data) - 1)
            lo, hi = int(idx), min(int(idx) + 1, len(sorted_data) - 1)
            return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (idx - lo)

        p50 = percentile(obs, 50)
        p99 = percentile(obs, 99)
        mean = statistics.mean(obs)
        maximum = obs[-1]

        abs_obs = [abs(x) for x in obs]
        p50_abs = percentile(sorted(abs_obs), 50)

        if p50_abs < 3.0:
            regime = SlippageRegime.NORMAL
        elif p50_abs < 8.0:
            regime = SlippageRegime.ELEVATED
        else:
            regime = SlippageRegime.HIGH

        return SlippageStats(
            n=n,
            p50_bps=round(p50, 4),
            p99_bps=round(p99, 4),
            mean_bps=round(mean, 4),
            max_bps=round(maximum, 4),
            regime=regime,
        )

    @property
    def regime(self) -> SlippageRegime:
        return self._regime

    @property
    def observation_count(self) -> int:
        return len(self._observations)
