"""
Core bond mathematics: FV, PV, discount factors, YTM solver.
All hot paths are vectorized. No Python loops in pricing critical section.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class CashFlowSchedule:
    """Pre-computed cash flow schedule. Build once, reprice many times."""
    times: np.ndarray        # Year fractions from settlement (float64)
    amounts: np.ndarray      # Cash flow amounts (float64)
    coupon_dates: list[date]
    settlement: date

    def __post_init__(self) -> None:
        assert len(self.times) == len(self.amounts), "times/amounts length mismatch"
        assert (self.times > 0).all(), "All cash flows must be in the future"


def future_value(
    present_value: float,
    rate: float,
    periods: int,
    *,
    compounding: int = 1,  # 1=annual, 2=semi-annual, 12=monthly
) -> float:
    """
    FV = PV × (1 + r/m)^(n×m)
    
    Args:
        present_value: Initial investment
        rate: Annual rate (e.g., 0.05 for 5%)
        periods: Number of years
        compounding: Compounding frequency per year
    """
    if rate < -1.0:
        raise ValueError("Rate cannot be less than -100%")
    return present_value * (1.0 + rate / compounding) ** (periods * compounding)


def present_value(
    future_value: float,
    rate: float,
    periods: int,
    *,
    compounding: int = 1,
) -> float:
    """
    PV = FV / (1 + r/m)^(n×m)
    Inverse of future_value. Rate must be > -1.
    """
    if rate <= -1.0:
        raise ValueError("Rate must be > -100% for meaningful PV")
    return future_value / (1.0 + rate / compounding) ** (periods * compounding)


def discount_factors(
    times: np.ndarray,
    ytm: float,
    *,
    frequency: int = 2,  # Semi-annual default (US convention)
) -> np.ndarray:
    """
    Vectorized discount factors: df[i] = 1 / (1 + ytm/freq)^(times[i] * freq)
    
    This is the hot path. NumPy broadcasts across the entire times array
    in a single C-level operation — no Python loop.
    """
    return 1.0 / (1.0 + ytm / frequency) ** (times * frequency)


def dirty_price(schedule: CashFlowSchedule, ytm: float, frequency: int = 2) -> float:
    """
    Dirty price = sum of all discounted cash flows.
    This is what you *actually pay* when buying a bond.
    Assumes face value is embedded in the final cash flow.
    """
    df = discount_factors(schedule.times, ytm, frequency=frequency)
    # np.dot: single BLAS call, faster than sum(a*b for a,b in zip(...))
    return float(np.dot(schedule.amounts, df))


def accrued_interest(
    face: float,
    coupon_rate: float,
    frequency: int,
    days_since_last_coupon: int,
    days_in_coupon_period: int,
) -> float:
    """
    Accrued interest = (face × annual_coupon / freq) × (days_since / days_in_period)
    
    Critical: use ACTUAL days from day count convention, not assumed period lengths.
    """
    periodic_coupon = face * coupon_rate / frequency
    return periodic_coupon * (days_since_last_coupon / days_in_coupon_period)


def clean_price(schedule: CashFlowSchedule, ytm: float, accr_int: float, frequency: int = 2) -> float:
    """Clean price = dirty price - accrued interest. This is what markets quote."""
    return dirty_price(schedule, ytm, frequency=frequency) - accr_int


def bond_duration(schedule: CashFlowSchedule, ytm: float, frequency: int = 2) -> float:
    """
    Macaulay duration: time-weighted average of discounted cash flows.
    Used as the first derivative in Newton-Raphson YTM solver.
    """
    df = discount_factors(schedule.times, ytm, frequency=frequency)
    discounted = schedule.amounts * df
    total_pv = float(np.sum(discounted))
    if total_pv == 0:
        raise ValueError("Bond PV is zero — check cash flow schedule")
    return float(np.dot(schedule.times, discounted)) / total_pv


def modified_duration(schedule: CashFlowSchedule, ytm: float, frequency: int = 2) -> float:
    """Modified duration = Macaulay duration / (1 + ytm/freq). Price sensitivity per unit rate."""
    mac_dur = bond_duration(schedule, ytm, frequency=frequency)
    return mac_dur / (1.0 + ytm / frequency)


def dv01(schedule: CashFlowSchedule, ytm: float, face: float = 100.0, frequency: int = 2) -> float:
    """
    Dollar value of 1 basis point.
    DV01 = -dP/dy × 0.0001 ≈ modified_duration × dirty_price × 0.0001
    """
    dp = dirty_price(schedule, ytm, frequency=frequency)
    md = modified_duration(schedule, ytm, frequency=frequency)
    return md * dp * 0.0001


def solve_ytm(
    schedule: CashFlowSchedule,
    target_price: float,
    *,
    frequency: int = 2,
    tol: float = 1e-8,
    max_iter: int = 50,
) -> float:
    """
    Newton-Raphson YTM solver with explicit bracketing and bisection fallback.
    
    Why NR over scipy.optimize?
    - We own the derivative (duration) analytically — no finite difference needed
    - NR converges quadratically once near the root (vs bisection's linear)
    - Explicit fallback: if |step| > 0.5 or we diverge, bisect instead
    
    Returns: YTM as decimal (e.g., 0.0423 for 4.23%)
    """
    # ── Bracket search ──────────────────────────────────────────────
    # Find r_low, r_high such that P(r_low) > target > P(r_high)
    r_low, r_high = -0.20, 5.0  # -20% to 500% covers all real bonds
    
    p_low = dirty_price(schedule, r_low, frequency=frequency)
    p_high = dirty_price(schedule, r_high, frequency=frequency)

    if not (p_low > target_price > p_high):
        raise ValueError(
            f"Cannot bracket YTM: P({r_low:.0%})={p_low:.4f}, "
            f"target={target_price:.4f}, P({r_high:.0%})={p_high:.4f}"
        )

    # ── Initial guess: simple approximation ─────────────────────────
    # Crude but gives NR a good starting point
    annual_coupon = schedule.amounts[:-1].mean() if len(schedule.amounts) > 1 else 0.0
    years = schedule.times[-1]
    approx_par = (schedule.amounts[-1] - schedule.amounts[:-1].mean()) if len(schedule.amounts) > 1 else schedule.amounts[-1]
    r = (annual_coupon + (approx_par - target_price) / years) / ((approx_par + target_price) / 2.0)
    r = max(r_low + 0.001, min(r, r_high - 0.001))

    # ── Newton-Raphson with bisection fallback ───────────────────────
    for iteration in range(max_iter):
        p = dirty_price(schedule, r, frequency=frequency)
        error = p - target_price

        if abs(error) < tol:
            return r

        # Analytical derivative: dP/dr = -modified_duration × P × (1 + r/freq)
        # Equivalently: use duration * price directly
        md = modified_duration(schedule, r, frequency=frequency)
        dp_dr = -md * p

        if abs(dp_dr) < 1e-12:
            # Derivative too flat — fall back to bisection
            r = (r_low + r_high) / 2.0
        else:
            step = error / dp_dr
            r_new = r - step

            # If NR step leaves bracket or is too large, bisect instead
            if r_new <= r_low or r_new >= r_high or abs(step) > 0.5:
                r_new = (r_low + r_high) / 2.0

            r = r_new

        # Update bracket
        p_current = dirty_price(schedule, r, frequency=frequency)
        if p_current > target_price:
            r_low = r
        else:
            r_high = r

    raise RuntimeError(
        f"YTM solver did not converge after {max_iter} iterations. "
        f"Final error: {error:.2e}. Check cash flow schedule."
    )
