"""
Day Count Convention implementations.
These are NOT cosmetic — wrong conventions = systematic pricing error.
Supported: 30/360 (US Bond), Act/360, Act/365, Act/Act (ISDA)
"""

from __future__ import annotations
from datetime import date
from enum import Enum, auto
import numpy as np


class DayCount(Enum):
    THIRTY_360 = auto()        # US Corporate / Municipal
    ACT_360 = auto()           # Money market, most FRNs
    ACT_365 = auto()           # UK Gilts, some LIBOR instruments
    ACT_ACT_ISDA = auto()      # US Treasuries, most government bonds


def _days_30_360(d1: date, d2: date) -> float:
    """
    30/360 US Bond convention.
    Each month treated as 30 days, year as 360.
    """
    y1, m1, dd1 = d1.year, d1.month, d1.day
    y2, m2, dd2 = d2.year, d2.month, d2.day

    # Adjust end-of-month rules
    if dd1 == 31:
        dd1 = 30
    if dd2 == 31 and dd1 == 30:
        dd2 = 30

    return (360 * (y2 - y1) + 30 * (m2 - m1) + (dd2 - dd1)) / 360.0


def _days_act_360(d1: date, d2: date) -> float:
    return (d2 - d1).days / 360.0


def _days_act_365(d1: date, d2: date) -> float:
    return (d2 - d1).days / 365.0


def _days_act_act_isda(d1: date, d2: date) -> float:
    """
    Act/Act ISDA: split across year boundaries.
    Critical for multi-year instruments — simple Act/365 is wrong here.
    """
    if d1.year == d2.year:
        days_in_year = 366.0 if _is_leap(d1.year) else 365.0
        return (d2 - d1).days / days_in_year

    # Split at year boundary
    end_of_year = date(d1.year, 12, 31)
    start_of_next = date(d1.year + 1, 1, 1)

    frac_first = (end_of_year - d1).days / (366.0 if _is_leap(d1.year) else 365.0)
    # Recurse for remaining years
    frac_rest = _days_act_act_isda(start_of_next, d2)
    return frac_first + frac_rest


def _is_leap(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


# Dispatch table — avoids if/elif chains in hot paths
_CONVENTION_FN = {
    DayCount.THIRTY_360: _days_30_360,
    DayCount.ACT_360: _days_act_360,
    DayCount.ACT_365: _days_act_365,
    DayCount.ACT_ACT_ISDA: _days_act_act_isda,
}


def year_fraction(
    start: date,
    end: date,
    convention: DayCount = DayCount.ACT_ACT_ISDA,
) -> float:
    """Compute time fraction between two dates under given day count convention."""
    if end < start:
        raise ValueError(f"end date {end} precedes start date {start}")
    return _CONVENTION_FN[convention](start, end)


def year_fractions_vectorized(
    settlement: date,
    coupon_dates: list[date],
    convention: DayCount = DayCount.ACT_ACT_ISDA,
) -> np.ndarray:
    """
    Vectorized year fractions from settlement to each coupon date.
    Returns float64 array — feed directly into discount factor computation.
    """
    fn = _CONVENTION_FN[convention]
    return np.array([fn(settlement, cd) for cd in coupon_dates], dtype=np.float64)
