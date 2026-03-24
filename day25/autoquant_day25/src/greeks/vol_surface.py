"""
src/greeks/vol_surface.py
Nearest-neighbor IV surface (starter implementation).

Homework task: replace with RectBivariateSpline.
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class VolSurface:
    """
    Discrete implied volatility surface indexed by (moneyness, expiry).
    moneyness = K / S (strike / spot)
    """
    moneyness_grid: np.ndarray   # shape (M,) sorted ascending
    expiry_grid: np.ndarray      # shape (E,) sorted ascending, in years
    vol_matrix: np.ndarray       # shape (M, E)

    def get_iv(self, K: float, S: float, T: float) -> float:
        """Nearest-neighbor lookup — O(log N) via searchsorted."""
        moneyness = K / S
        m_idx = np.searchsorted(self.moneyness_grid, moneyness, side="left")
        m_idx = min(max(m_idx, 0), len(self.moneyness_grid) - 1)
        e_idx = np.searchsorted(self.expiry_grid, T, side="left")
        e_idx = min(max(e_idx, 0), len(self.expiry_grid) - 1)
        return float(self.vol_matrix[m_idx, e_idx])

    def get_iv_vectorized(
        self, K: np.ndarray, S: float, T: np.ndarray
    ) -> np.ndarray:
        """Vectorized lookup for N contracts."""
        moneyness = K / S
        m_idx = np.clip(
            np.searchsorted(self.moneyness_grid, moneyness, side="left"),
            0, len(self.moneyness_grid) - 1,
        )
        e_idx = np.clip(
            np.searchsorted(self.expiry_grid, T, side="left"),
            0, len(self.expiry_grid) - 1,
        )
        return self.vol_matrix[m_idx, e_idx]

    @classmethod
    def build_synthetic(cls, spot: float = 500.0) -> "VolSurface":
        """
        Construct a realistic synthetic vol surface for demo/testing.
        Models the classic volatility smile (higher vol for OTM puts).
        """
        moneyness = np.linspace(0.80, 1.20, 17)   # 80% to 120% moneyness
        expiries   = np.array([1/52, 1/12, 3/12, 6/12, 1.0])  # 1w to 1y

        # Smile: ATM vol ~18%, wings higher, term structure upward-sloping
        smile_base = 0.18 + 0.12 * (moneyness - 1.0) ** 2   # shape (M,)
        term_factor = 1.0 + 0.15 * np.sqrt(expiries)         # shape (E,)

        vol_matrix = np.outer(smile_base, term_factor)        # shape (M, E)
        vol_matrix = np.clip(vol_matrix, 0.05, 0.80)

        return cls(
            moneyness_grid=moneyness,
            expiry_grid=expiries,
            vol_matrix=vol_matrix,
        )
