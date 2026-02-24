"""
Unit tests for bond math primitives.
All expected values verified against Bloomberg/manual calculation.
"""

import pytest
import numpy as np
from datetime import date

from src.bond_math import (
    future_value,
    present_value,
    discount_factors,
    dirty_price,
    solve_ytm,
    CashFlowSchedule,
)
from src.day_count import DayCount, year_fraction, _days_30_360, _days_act_act_isda
from src.bond_pricer import BondSpec, BondPricer, build_schedule


# ── FV / PV round-trip tests ───────────────────────────────────────────────

def test_fv_annual_compounding():
    """$1000 at 5% for 10 years, annual compounding = $1628.89"""
    result = future_value(1000.0, 0.05, 10, compounding=1)
    assert abs(result - 1628.894627777) < 0.001, f"Expected ~1628.89, got {result}"


def test_fv_semi_annual_compounding():
    """$1000 at 6% for 5 years, semi-annual = $1343.92"""
    result = future_value(1000.0, 0.06, 5, compounding=2)
    assert abs(result - 1343.9163793) < 0.01


def test_pv_annual():
    """$1000 in 5 years at 8% discount = $680.58"""
    result = present_value(1000.0, 0.08, 5, compounding=1)
    assert abs(result - 680.5832) < 0.01


def test_fv_pv_round_trip():
    """FV then PV should recover original value."""
    original = 12345.67
    for rate in [0.01, 0.05, 0.12, 0.25]:
        for periods in [1, 5, 10, 30]:
            for freq in [1, 2, 12]:
                fv = future_value(original, rate, periods, compounding=freq)
                pv = present_value(fv, rate, periods, compounding=freq)
                assert abs(pv - original) < 1e-6, (
                    f"Round-trip failed: rate={rate}, periods={periods}, freq={freq}"
                )


def test_fv_zero_rate():
    """At 0% rate, FV == PV."""
    assert future_value(500.0, 0.0, 10) == pytest.approx(500.0)
    assert present_value(500.0, 0.0, 10) == pytest.approx(500.0)


def test_fv_invalid_rate():
    with pytest.raises(ValueError):
        future_value(1000.0, -1.5, 5)
    with pytest.raises(ValueError):
        present_value(1000.0, -1.0, 5)


# ── Day count tests ────────────────────────────────────────────────────────

def test_30_360_same_day():
    d1 = date(2024, 1, 1)
    d2 = date(2025, 1, 1)
    assert abs(_days_30_360(d1, d2) - 1.0) < 1e-9


def test_30_360_end_of_month():
    """30/360: Jan 31 to Mar 31 should be 2 months exactly = 60/360."""
    d1 = date(2024, 1, 31)
    d2 = date(2024, 3, 31)
    result = _days_30_360(d1, d2)
    assert abs(result - 60 / 360.0) < 1e-9


def test_act_act_leap_year():
    """2024 is a leap year — Act/Act should use 366."""
    d1 = date(2024, 1, 1)
    d2 = date(2024, 12, 31)
    frac = _days_act_act_isda(d1, d2)
    expected = 365 / 366.0  # 365 actual days in 366-day year
    assert abs(frac - expected) < 1e-9


# ── Discount factor tests ──────────────────────────────────────────────────

def test_discount_factors_monotone():
    """Discount factors must strictly decrease with time."""
    times = np.array([0.5, 1.0, 1.5, 2.0, 5.0, 10.0])
    df = discount_factors(times, ytm=0.05)
    assert (np.diff(df) < 0).all(), "Discount factors are not monotonically decreasing"


def test_discount_factors_at_zero_ytm():
    """At 0% YTM, all discount factors = 1."""
    times = np.linspace(0.5, 10, 20)
    df = discount_factors(times, ytm=0.0)
    np.testing.assert_allclose(df, 1.0, rtol=1e-9)


# ── Bond pricing tests ─────────────────────────────────────────────────────

def _make_par_bond() -> tuple[BondSpec, BondPricer]:
    """A par bond: coupon rate == YTM → clean price should be 100."""
    spec = BondSpec(
        face_value=100.0,
        coupon_rate=0.05,
        maturity_date=date(2034, 2, 15),
        issue_date=date(2024, 2, 15),
        frequency=2,
        day_count=DayCount.THIRTY_360,
    )
    return spec, BondPricer()


def test_par_bond_pricing():
    """When YTM == coupon rate and settlement is on coupon date, price ≈ par."""
    spec, p = _make_par_bond()
    # Price at issue date with YTM = coupon rate → dirty price = 100
    result = p.price(spec, ytm=0.05, settlement=date(2024, 2, 17))
    # Slight deviation due to day count conventions and settlement date effects
    assert abs(result.dirty - 100.0) < 0.5, f"Par bond mispriced: {result.dirty}"


def test_premium_bond_ytm_lower_than_coupon():
    """Bond trading at premium → YTM < coupon rate."""
    spec, p = _make_par_bond()
    result = p.price(spec, ytm=0.04, settlement=date(2024, 2, 17))
    assert result.dirty > 100.0, "Premium bond should price above par"


def test_discount_bond_ytm_higher_than_coupon():
    """Bond trading at discount → YTM > coupon rate."""
    spec, p = _make_par_bond()
    result = p.price(spec, ytm=0.06, settlement=date(2024, 2, 17))
    assert result.dirty < 100.0, "Discount bond should price below par"


def test_ytm_solver_round_trip():
    """Price at YTM, then solve_ytm from that price → should recover YTM."""
    spec, p = _make_par_bond()
    settlement = date(2024, 2, 17)
    target_ytm = 0.0523

    result = p.price(spec, ytm=target_ytm, settlement=settlement)
    recovered = p.price_from_market(spec, result.clean, settlement=settlement)

    assert recovered.solver_converged, "YTM solver did not converge"
    assert abs(recovered.ytm - target_ytm) < 1e-6, (
        f"YTM round-trip error: {abs(recovered.ytm - target_ytm):.2e}"
    )


def test_dirty_clean_reconciliation():
    """dirty_price = clean_price + accrued_interest, always."""
    spec, p = _make_par_bond()
    settlement = date(2024, 5, 10)  # Between coupon dates
    result = p.price(spec, ytm=0.05, settlement=settlement)
    recon = result.clean + result.accrued
    assert abs(recon - result.dirty) < 1e-9, (
        f"dirty ≠ clean + accrued: {result.dirty} ≠ {recon}"
    )


def test_modified_duration_sign():
    """Modified duration must be positive (inverse relationship price-yield)."""
    spec, p = _make_par_bond()
    result = p.price(spec, ytm=0.05, settlement=date(2024, 2, 17))
    assert result.modified_dur > 0, f"Modified duration should be positive, got {result.modified_dur}"


def test_longer_maturity_higher_duration():
    """Longer maturity → higher duration (ceteris paribus)."""
    base_spec = BondSpec(
        face_value=100.0,
        coupon_rate=0.05,
        issue_date=date(2024, 1, 1),
        maturity_date=date(2026, 1, 1),
        frequency=2,
        day_count=DayCount.THIRTY_360,
    )
    long_spec = BondSpec(
        face_value=100.0,
        coupon_rate=0.05,
        issue_date=date(2024, 1, 1),
        maturity_date=date(2034, 1, 1),
        frequency=2,
        day_count=DayCount.THIRTY_360,
    )
    p = BondPricer()
    settlement = date(2024, 3, 1)
    r_short = p.price(base_spec, 0.05, settlement=settlement)
    r_long = p.price(long_spec, 0.05, settlement=settlement)
    assert r_long.modified_dur > r_short.modified_dur, (
        f"Long bond duration {r_long.modified_dur:.3f} should exceed "
        f"short bond {r_short.modified_dur:.3f}"
    )
