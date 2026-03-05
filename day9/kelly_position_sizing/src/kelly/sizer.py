"""
kelly/sizer.py

Translates a KellyEstimate into a concrete share count, accounting for:
  - Fractional Kelly multiplier (typically 0.5)
  - Hard cap on single-position fraction of NAV
  - Correlation haircut across existing portfolio positions
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Mapping

from .estimator import KellyEstimate


@dataclass(slots=True)
class SizeResult:
    symbol: str
    kelly_fraction: float          # f_final going into share calc
    dollar_allocation: float
    shares: int
    nav_fraction: float            # dollar_allocation / nav
    at_hard_cap: bool              # True → Kelly was clipped to max_position_fraction


class PositionSizer:
    """
    Convert a KellyEstimate → concrete share count.

    Parameters
    ----------
    kelly_fraction : float
        Fractional multiplier (0.5 = half-Kelly).
    max_position_fraction : float
        Hard upper bound on NAV allocation to any single position (e.g. 0.15).
    correlation_haircut : bool
        If True, reduce allocation when existing portfolio has correlated positions.
    """

    def __init__(
        self,
        kelly_fraction: float = 0.5,
        max_position_fraction: float = 0.15,
        correlation_haircut: bool = True,
    ) -> None:
        if not 0 < kelly_fraction <= 1.0:
            raise ValueError(f"kelly_fraction must be in (0, 1], got {kelly_fraction}")
        if not 0 < max_position_fraction <= 1.0:
            raise ValueError(f"max_position_fraction must be in (0, 1], got {max_position_fraction}")

        self._kf = kelly_fraction
        self._max_frac = max_position_fraction
        self._use_corr = correlation_haircut

    def size(
        self,
        estimate: KellyEstimate,
        nav: float,
        price: float,
        portfolio_returns: Mapping[str, np.ndarray] | None = None,
        symbol_returns: np.ndarray | None = None,
    ) -> SizeResult:
        """
        Compute share count for `estimate.symbol`.

        Parameters
        ----------
        estimate : KellyEstimate
        nav : float
            Current account Net Asset Value in USD.
        price : float
            Current ask price for entry.
        portfolio_returns : mapping of {symbol: returns_array} for existing positions.
            Used to compute correlation haircut.
        symbol_returns : ndarray of this symbol's historical returns.
            Required if portfolio_returns is provided.
        """
        if not estimate.has_edge:
            return SizeResult(
                symbol=estimate.symbol,
                kelly_fraction=0.0, dollar_allocation=0.0,
                shares=0, nav_fraction=0.0, at_hard_cap=False,
            )

        f_raw = estimate.boot_kelly_p5 * self._kf  # Half-Kelly applied

        # Correlation haircut: if existing positions are correlated, reduce
        if self._use_corr and portfolio_returns and symbol_returns is not None:
            haircut = self._correlation_haircut(symbol_returns, portfolio_returns)
            f_raw *= (1.0 - haircut)

        at_hard_cap = f_raw > self._max_frac
        f_final = min(f_raw, self._max_frac)
        f_final = max(f_final, 0.0)

        dollar_alloc = nav * f_final
        shares = max(0, int(dollar_alloc / price))

        return SizeResult(
            symbol=estimate.symbol,
            kelly_fraction=f_final,
            dollar_allocation=dollar_alloc,
            shares=shares,
            nav_fraction=f_final,
            at_hard_cap=at_hard_cap,
        )

    # ------------------------------------------------------------------

    def _correlation_haircut(
        self,
        symbol_returns: np.ndarray,
        portfolio_returns: Mapping[str, np.ndarray],
    ) -> float:
        """
        Compute weighted average absolute correlation of new symbol vs
        existing portfolio symbols.  Returns a value in [0, 0.5].
        A corr of 0.8 → haircut of 0.4 (40% reduction in allocation).
        """
        correlations: list[float] = []
        min_len = len(symbol_returns)

        for existing_returns in portfolio_returns.values():
            n = min(min_len, len(existing_returns))
            if n < 10:
                continue
            corr = float(np.corrcoef(symbol_returns[-n:], existing_returns[-n:])[0, 1])
            if not np.isnan(corr):
                correlations.append(abs(corr))

        if not correlations:
            return 0.0

        avg_corr = float(np.mean(correlations))
        # Haircut = 50% of avg correlation.  Max haircut = 50%.
        return min(avg_corr * 0.5, 0.5)
