"""
kelly/risk_guard.py

Stateless pre-trade risk checks executed synchronously *before* order submission.
Returns a RiskDecision — callers must check .approved before placing orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .sizer import SizeResult


@dataclass(slots=True)
class RiskDecision:
    approved: bool
    reason: str  # Human-readable, logged verbatim


class RiskGuard:
    """
    Hard-limit risk filter.  None of these checks can be overridden at runtime.

    Parameters
    ----------
    max_single_position_pct : float  Hard cap per position (e.g. 0.15 = 15% NAV)
    max_total_exposure_pct  : float  Sum of all position fracs (e.g. 0.80)
    min_shares              : int    Reject allocations too small to be meaningful
    """

    def __init__(
        self,
        max_single_position_pct: float = 0.15,
        max_total_exposure_pct: float = 0.80,
        min_shares: int = 1,
    ) -> None:
        self._max_single = max_single_position_pct
        self._max_total = max_total_exposure_pct
        self._min_shares = min_shares

    def check(
        self,
        proposed: SizeResult,
        existing_fractions: Sequence[float],
    ) -> RiskDecision:
        """
        Evaluate proposed trade against risk limits.

        Parameters
        ----------
        proposed         : SizeResult from PositionSizer
        existing_fractions : current portfolio weights (sum of open position fracs)
        """
        if proposed.shares < self._min_shares:
            return RiskDecision(False, f"Shares={proposed.shares} below min={self._min_shares}")

        if proposed.nav_fraction > self._max_single:
            return RiskDecision(
                False,
                f"Position frac {proposed.nav_fraction:.3f} > single cap {self._max_single}"
            )

        total_exposure = sum(existing_fractions) + proposed.nav_fraction
        if total_exposure > self._max_total:
            return RiskDecision(
                False,
                f"Total exposure {total_exposure:.3f} > max {self._max_total} after adding {proposed.symbol}"
            )

        return RiskDecision(True, "OK")
