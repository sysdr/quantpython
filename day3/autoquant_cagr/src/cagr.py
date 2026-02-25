"""
Core CAGR computation engine.

Design invariants:
- All inputs are 1-D float64 NumPy arrays of ADJUSTED close prices.
- Log-return convention: 252 trading days per year (not 365 calendar days).
- Non-finite returns are zero-filled with a WARNING — never silently propagated.
- All public functions are pure (no side effects, no global mutation).
"""
from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass

from .config import TRADING_DAYS_PER_YEAR, TENORS, TENOR_ORDER, build_logger

logger = build_logger("cagr")


# ── Data structures ───────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class LogReturnSeries:
    """Validated log-return vector with quality metadata."""
    values: np.ndarray         # float64, zero-filled for non-finite
    nan_count: int             # original non-finite count before fill
    source_length: int         # length of original price series


@dataclass(frozen=True, slots=True)
class CAGRSurface:
    """Return term structure across all configured tenors."""
    symbol: str
    cagr_by_tenor: dict[str, float]   # NaN if insufficient history
    nan_ratio: float                  # quality indicator from source series

    def tenors(self) -> list[str]:
        return TENOR_ORDER

    def values(self) -> list[float]:
        return [self.cagr_by_tenor.get(t, float("nan")) for t in TENOR_ORDER]

    def as_pct(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for t in TENOR_ORDER:
            v = self.cagr_by_tenor.get(t, float("nan"))
            result[t] = f"{v * 100:+.2f}%" if np.isfinite(v) else "  N/A "
        return result

    def detect_inversions(
        self, threshold_bps: float = 500.0
    ) -> list[tuple[str, str, float]]:
        """
        Returns list of (short_tenor, long_tenor, spread_bps) where
        the shorter-tenor CAGR exceeds the longer-tenor CAGR by > threshold_bps.
        """
        inversions: list[tuple[str, str, float]] = []
        valid = [
            (t, self.cagr_by_tenor[t])
            for t in TENOR_ORDER
            if t in self.cagr_by_tenor and np.isfinite(self.cagr_by_tenor[t])
        ]
        for i in range(len(valid)):
            for j in range(i + 1, len(valid)):
                short_t, short_v = valid[i]
                long_t, long_v = valid[j]
                spread_bps = (short_v - long_v) * 10_000
                if spread_bps > threshold_bps:
                    inversions.append((short_t, long_t, spread_bps))
        return inversions


# ── Core math ─────────────────────────────────────────────────────────────

def compute_log_returns(prices: np.ndarray) -> LogReturnSeries:
    """
    Convert price series to log-return series.

    Zero-fill strategy for non-finite values:
    - Halt / zero-price bars → log(0) = -inf → treated as 0% return
    - This preserves the 252-day denominator integrity
    """
    if len(prices) < 2:
        return LogReturnSeries(
            values=np.array([], dtype=np.float64),
            nan_count=0,
            source_length=len(prices),
        )

    prices = np.asarray(prices, dtype=np.float64)

    with np.errstate(divide="ignore", invalid="ignore"):
        raw = np.log(prices[1:] / prices[:-1])

    finite_mask = np.isfinite(raw)
    nan_count = int((~finite_mask).sum())

    if nan_count > 0:
        logger.warning(
            "Non-finite log-returns detected: %d/%d → zero-filled",
            nan_count,
            len(raw),
        )

    filled = np.where(finite_mask, raw, 0.0)
    return LogReturnSeries(
        values=filled,
        nan_count=nan_count,
        source_length=len(prices),
    )


def cagr_from_log_returns(log_rets: np.ndarray, window: int) -> float:
    """
    Geometric CAGR for the trailing `window` trading days.

    Formula: exp(sum(log_returns[-window:]) / (window / 252)) - 1

    This is exact — no floating-point drift from repeated price multiplication.
    Returns NaN if insufficient data.
    """
    if len(log_rets) < window:
        return float("nan")

    windowed = log_rets[-window:]
    total_log_return = float(windowed.sum())
    years = window / TRADING_DAYS_PER_YEAR
    return float(np.exp(total_log_return / years) - 1.0)


def build_cagr_surface(symbol: str, prices: np.ndarray) -> CAGRSurface:
    """
    Full pipeline: prices → log-returns → CAGR surface.

    Args:
        symbol: Ticker identifier for logging/display.
        prices: 1-D array of adjusted close prices, chronological order.

    Returns:
        CAGRSurface with per-tenor CAGR values.
    """
    series = compute_log_returns(prices)
    nan_ratio = series.nan_count / max(len(series.values), 1)

    surface = {
        tenor: cagr_from_log_returns(series.values, days)
        for tenor, days in TENORS.items()
    }

    logger.info(
        "CAGR surface built | symbol=%s | price_bars=%d | nan_ratio=%.4f",
        symbol,
        len(prices),
        nan_ratio,
    )

    return CAGRSurface(
        symbol=symbol,
        cagr_by_tenor=surface,
        nan_ratio=nan_ratio,
    )
