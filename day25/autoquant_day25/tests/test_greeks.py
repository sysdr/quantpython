"""
tests/test_greeks.py
Unit tests for BSM Greeks implementation.
Tests: correctness, boundary conditions, vectorized vs scalar consistency.
"""
import math
import numpy as np
import pytest

from src.greeks.engine import (
    bsm_delta_scalar,
    bsm_gamma_scalar,
    bsm_greeks_vectorized,
)
from src.greeks.models import (
    OptionContract,
    OptionPosition,
    PortfolioGreeks,
    MarketState,
    PositionState,
)
from src.greeks.vol_surface import VolSurface


# ── Analytic reference values from Haug "The Complete Guide to Option Pricing" ─

class TestDeltaScalar:
    def test_atm_call_delta_approx_half(self):
        """ATM call delta ≈ 0.5 for short expiry."""
        d = bsm_delta_scalar(S=100, K=100, r=0.05, T=0.01, sigma=0.20, is_call=True)
        assert 0.50 < d < 0.60, f"ATM call delta should be ~0.53, got {d:.4f}"

    def test_deep_itm_call_delta_near_one(self):
        d = bsm_delta_scalar(S=150, K=100, r=0.05, T=1.0, sigma=0.20, is_call=True)
        assert d > 0.95

    def test_deep_otm_put_delta_near_zero(self):
        d = bsm_delta_scalar(S=100, K=50, r=0.05, T=1.0, sigma=0.20, is_call=False)
        assert abs(d) < 0.05

    def test_call_put_delta_parity(self):
        """Call delta - Put delta = 1 (put-call parity for delta)."""
        s = dict(S=100, K=100, r=0.05, T=0.5, sigma=0.25)
        d_call = bsm_delta_scalar(**s, is_call=True)
        d_put  = bsm_delta_scalar(**s, is_call=False)
        assert abs((d_call - d_put) - 1.0) < 1e-10

    def test_expiry_boundary_call(self):
        """At T=0, ITM call delta=1, OTM call delta=0."""
        assert bsm_delta_scalar(S=101, K=100, r=0.05, T=0.0, sigma=0.20, is_call=True) == 1.0
        assert bsm_delta_scalar(S=99,  K=100, r=0.05, T=0.0, sigma=0.20, is_call=True) == 0.0


class TestGammaScalar:
    def test_gamma_positive(self):
        """Gamma is always non-negative."""
        for S in [80, 100, 120]:
            g = bsm_gamma_scalar(S=S, K=100, r=0.05, T=1.0, sigma=0.20)
            assert g >= 0, f"Gamma negative at S={S}"

    def test_gamma_peak_at_atm(self):
        """Gamma is maximized near ATM."""
        g_atm = bsm_gamma_scalar(S=100, K=100, r=0.05, T=1.0, sigma=0.20)
        g_itm = bsm_gamma_scalar(S=130, K=100, r=0.05, T=1.0, sigma=0.20)
        g_otm = bsm_gamma_scalar(S=70,  K=100, r=0.05, T=1.0, sigma=0.20)
        assert g_atm > g_itm
        assert g_atm > g_otm

    def test_gamma_delta_consistency(self):
        """
        Finite difference check: ∂Delta/∂S ≈ Gamma.
        Tolerance 1e-4 for h=0.01 step.
        """
        S, K, r, T, sig = 100.0, 100.0, 0.05, 1.0, 0.20
        h = 0.01
        d_up   = bsm_delta_scalar(S+h, K, r, T, sig, is_call=True)
        d_down = bsm_delta_scalar(S-h, K, r, T, sig, is_call=True)
        fd_gamma = (d_up - d_down) / (2 * h)
        analytical_gamma = bsm_gamma_scalar(S, K, r, T, sig)
        assert abs(fd_gamma - analytical_gamma) < 1e-4, (
            f"FD gamma={fd_gamma:.6f} vs analytical={analytical_gamma:.6f}"
        )


class TestVectorizedConsistency:
    def test_vectorized_matches_scalar(self):
        """Vectorized engine must match scalar engine within 1e-10."""
        np.random.seed(42)
        N = 200
        S = 500.0
        K     = np.random.uniform(450, 550, N)
        T     = np.random.uniform(0.02, 1.0, N)
        sigma = np.random.uniform(0.10, 0.50, N)
        is_call = np.random.randint(0, 2, N).astype(bool)

        delta_v, gamma_v = bsm_greeks_vectorized(S, K, 0.05, T, sigma, is_call)

        for i in range(N):
            d_s = bsm_delta_scalar(S, K[i], 0.05, T[i], sigma[i], bool(is_call[i]))
            g_s = bsm_gamma_scalar(S, K[i], 0.05, T[i], sigma[i])
            assert abs(delta_v[i] - d_s) < 1e-10, f"Delta mismatch at i={i}"
            assert abs(gamma_v[i] - g_s) < 1e-10, f"Gamma mismatch at i={i}"


class TestKahanSummation:
    def test_kahan_precision(self):
        """Kahan sum of 1M small values must have error < 1e-8."""
        portfolio = PortfolioGreeks()
        target = 1_000_000 * 0.1
        for _ in range(1_000_000):
            portfolio.add_hedge_cost(0.1)
        error = abs(portfolio.total_hedge_cost - target)
        assert error < 1e-8, f"Kahan error {error:.2e} exceeds 1e-8"


class TestVolSurface:
    def test_surface_builds(self):
        vs = VolSurface.build_synthetic()
        assert vs.vol_matrix.shape == (17, 5)

    def test_iv_in_valid_range(self):
        vs = VolSurface.build_synthetic(spot=500.0)
        iv = vs.get_iv(K=500, S=500, T=0.25)
        assert 0.05 <= iv <= 0.80

    def test_vectorized_lookup_consistent(self):
        vs = VolSurface.build_synthetic(spot=500.0)
        K = np.array([490.0, 500.0, 510.0])
        T = np.array([0.25, 0.25, 0.25])
        iv_vec = vs.get_iv_vectorized(K, 500.0, T)
        for i, (k, t) in enumerate(zip(K, T)):
            assert abs(iv_vec[i] - vs.get_iv(k, 500.0, t)) < 1e-12


class TestOptionPosition:
    def _make_position(self) -> tuple[OptionPosition, MarketState]:
        contract = OptionContract(
            symbol="SPY", strike=500.0, expiry_years=0.25,
            option_type="call", implied_vol=0.20,
        )
        pos = OptionPosition(contract=contract, quantity=10, entry_price=5.0)
        mkt = MarketState(spot=500.0, risk_free_rate=0.05, timestamp_ns=0)
        return pos, mkt

    def test_position_delta_sign(self):
        pos, mkt = self._make_position()
        assert pos.delta(mkt) > 0, "Long call should have positive delta"

    def test_position_gamma_positive(self):
        pos, mkt = self._make_position()
        assert pos.gamma(mkt) > 0

    def test_short_position_negates_greeks(self):
        pos, mkt = self._make_position()
        pos.quantity = -10
        assert pos.delta(mkt) < 0
        assert pos.gamma(mkt) < 0
