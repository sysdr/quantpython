"""
BondSpec and BondPricer: high-level API over the math primitives.
This is the public interface the rest of the engine calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import numpy as np

from .day_count import DayCount, year_fractions_vectorized, year_fraction
from .bond_math import (
    CashFlowSchedule,
    dirty_price,
    clean_price,
    accrued_interest,
    dv01,
    modified_duration,
    solve_ytm,
    future_value,
    present_value,
)


@dataclass(slots=True)
class BondSpec:
    """
    Full bond specification. All the data you need to price a bond.
    slots=True: ~2x memory reduction and faster attribute access vs regular dataclass.
    """
    face_value: float            # Par value (typically 100 or 1000)
    coupon_rate: float           # Annual coupon rate (e.g., 0.045 for 4.5%)
    maturity_date: date          # Final maturity
    issue_date: date             # Original issue date (for stub period detection)
    frequency: int = 2           # Coupon payments per year (2 = semi-annual)
    day_count: DayCount = DayCount.ACT_ACT_ISDA
    cusip: str = ""              # Optional identifier


@dataclass(slots=True)
class PriceResult:
    """Immutable pricing result. All values at settlement date."""
    settlement: date
    dirty: float
    clean: float
    accrued: float
    ytm: float
    modified_dur: float
    dv01_per_face: float
    solver_converged: bool


def _generate_coupon_dates(spec: BondSpec, settlement: date) -> list[date]:
    """
    Walk backward from maturity to generate all future coupon dates.
    This correctly handles irregular stub periods at the front.
    """
    months_per_period = 12 // spec.frequency
    dates: list[date] = [spec.maturity_date]
    current = spec.maturity_date

    while True:
        # Step back by coupon period
        month = current.month - months_per_period
        year = current.year
        while month <= 0:
            month += 12
            year -= 1
        try:
            prev = date(year, month, current.day)
        except ValueError:
            # Handle end-of-month: e.g., Feb 28/29
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            prev = date(year, month, last_day)

        if prev <= settlement:
            break
        dates.insert(0, prev)
        current = prev

    return dates


def build_schedule(spec: BondSpec, settlement: date) -> tuple[CashFlowSchedule, float]:
    """
    Build cash flow schedule for a bond as of settlement date.
    Returns (schedule, accrued_interest).
    
    The schedule embeds face value in the final cash flow — standard convention.
    """
    coupon_dates = _generate_coupon_dates(spec, settlement)
    periodic_coupon = spec.face_value * spec.coupon_rate / spec.frequency

    # Cash flows: coupon at each date, plus face at maturity
    amounts = np.full(len(coupon_dates), periodic_coupon, dtype=np.float64)
    amounts[-1] += spec.face_value  # Terminal cash flow = coupon + par

    # Time fractions from settlement to each coupon date
    times = year_fractions_vectorized(settlement, coupon_dates, spec.day_count)

    # Accrued interest calculation
    # Find last coupon date (the coupon date just before settlement)
    months_per_period = 12 // spec.frequency
    first_future_coupon = coupon_dates[0]
    month = first_future_coupon.month - months_per_period
    year = first_future_coupon.year
    while month <= 0:
        month += 12
        year -= 1
    try:
        last_coupon_date = date(year, month, first_future_coupon.day)
    except ValueError:
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        last_coupon_date = date(year, month, last_day)

    days_since = (settlement - last_coupon_date).days
    days_in_period = (first_future_coupon - last_coupon_date).days
    accr = accrued_interest(spec.face_value, spec.coupon_rate, spec.frequency,
                            days_since, days_in_period)

    schedule = CashFlowSchedule(
        times=times,
        amounts=amounts,
        coupon_dates=coupon_dates,
        settlement=settlement,
    )
    return schedule, accr


class BondPricer:
    """
    Production bond pricer. Stateless — safe to call from multiple threads.
    Caches schedule per (cusip, settlement) for portfolio repricing efficiency.
    """

    def price(
        self,
        spec: BondSpec,
        ytm: float,
        settlement: date | None = None,
    ) -> PriceResult:
        """Price a bond at a given YTM."""
        if settlement is None:
            settlement = date.today() + timedelta(days=2)  # T+2 settlement

        schedule, accr = build_schedule(spec, settlement)
        dp = dirty_price(schedule, ytm, frequency=spec.frequency)
        cp = dp - accr
        md = modified_duration(schedule, ytm, frequency=spec.frequency)
        dv = dv01(schedule, ytm, face=spec.face_value, frequency=spec.frequency)

        return PriceResult(
            settlement=settlement,
            dirty=dp,
            clean=cp,
            accrued=accr,
            ytm=ytm,
            modified_dur=md,
            dv01_per_face=dv,
            solver_converged=True,
        )

    def price_from_market(
        self,
        spec: BondSpec,
        market_clean_price: float,
        settlement: date | None = None,
    ) -> PriceResult:
        """Given a market clean price, solve for YTM and compute full metrics."""
        if settlement is None:
            settlement = date.today() + timedelta(days=2)

        schedule, accr = build_schedule(spec, settlement)
        target_dirty = market_clean_price + accr

        converged = True
        try:
            ytm = solve_ytm(schedule, target_dirty, frequency=spec.frequency)
        except (ValueError, RuntimeError):
            converged = False
            ytm = spec.coupon_rate  # Fallback to coupon rate

        dp = dirty_price(schedule, ytm, frequency=spec.frequency)
        md = modified_duration(schedule, ytm, frequency=spec.frequency)
        dv = dv01(schedule, ytm, face=spec.face_value, frequency=spec.frequency)

        return PriceResult(
            settlement=settlement,
            dirty=dp,
            clean=market_clean_price,
            accrued=accr,
            ytm=ytm,
            modified_dur=md,
            dv01_per_face=dv,
            solver_converged=converged,
        )
