"""
src/greeks/engine.py
Vectorized BSM Greeks engine.

Design contract:
- bsm_greeks_vectorized: O(1) NumPy calls regardless of chain size N
- bsm_delta_scalar / bsm_gamma_scalar: single-contract fast path
- All functions are pure (no side effects, no global state)
"""
from __future__ import annotations

import math
import numpy as np
from scipy.special import ndtr  # vectorized norm.cdf — single C dispatch


# ── Scalar fast paths (used for on-demand property lookups) ──────────────────

def bsm_delta_scalar(
    S: float, K: float, r: float, T: float, sigma: float, is_call: bool
) -> float:
    """
    Per-contract delta. Called from OptionPosition.delta().
    Uses math.log + direct erf approximation — avoids scipy dispatch overhead
    for the single-contract case.
    """
    if T <= 0 or sigma <= 0:
        # At expiry: delta is 0 or 1 (deep ITM) or 0 (OTM)
        if is_call:
            return 1.0 if S >= K else 0.0
        else:
            return -1.0 if S <= K else 0.0

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    # math.erfc is faster than scipy.stats.norm.cdf for scalar
    N_d1 = 0.5 * math.erfc(-d1 / math.sqrt(2))
    return N_d1 if is_call else N_d1 - 1.0


def bsm_gamma_scalar(
    S: float, K: float, r: float, T: float, sigma: float
) -> float:
    if T <= 0 or sigma <= 0:
        return 0.0
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    n_d1 = math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)
    return n_d1 / (S * sigma * sqrt_T)


# ── Vectorized batch path (used for full-chain pricing) ──────────────────────

def bsm_greeks_vectorized(
    S: float,
    K: np.ndarray,
    r: float,
    T: np.ndarray,
    sigma: np.ndarray,
    is_call: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute delta and gamma for N contracts in a single vectorized pass.

    Args:
        S      : scalar spot price
        K      : (N,) strikes
        r      : scalar risk-free rate
        T      : (N,) time-to-expiry in years
        sigma  : (N,) implied vols per contract
        is_call: (N,) bool mask

    Returns:
        delta : (N,) per-contract delta (not multiplied by quantity)
        gamma : (N,) per-contract gamma
    """
    # Guard against degenerate inputs — avoids NaN propagation
    valid = (T > 1e-6) & (sigma > 1e-6)

    delta = np.where(is_call, np.where(S >= K, 1.0, 0.0), np.where(S <= K, -1.0, 0.0))
    gamma = np.zeros_like(K, dtype=np.float64)

    if not np.any(valid):
        return delta, gamma

    Sv = S
    Kv, Tv, sv, cv = K[valid], T[valid], sigma[valid], is_call[valid]

    sqrt_T = np.sqrt(Tv)
    d1 = (np.log(Sv / Kv) + (r + 0.5 * sv ** 2) * Tv) / (sv * sqrt_T)

    # ndtr: single dispatch to C for entire array — the core performance win
    N_d1 = ndtr(d1)

    delta[valid] = np.where(cv, N_d1, N_d1 - 1.0)

    # Gamma PDF: manual computation avoids scipy.stats.norm.pdf overhead
    n_d1 = np.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)
    gamma[valid] = n_d1 / (Sv * sv * sqrt_T)

    return delta, gamma
