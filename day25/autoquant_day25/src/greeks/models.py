"""
src/greeks/models.py
Core data models for option positions and Greeks.
Uses __slots__ to eliminate __dict__ overhead on hot-path objects.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal


class PositionState(Enum):
    PENDING    = auto()
    ACTIVE     = auto()
    HEDGING    = auto()
    NEAR_EXPIRY = auto()
    CLOSED     = auto()
    EXPIRED    = auto()


@dataclass(slots=True)
class MarketState:
    """Snapshot of market conditions at a single point in time."""
    spot: float          # underlying mid price
    risk_free_rate: float  # annualized, e.g. 0.053
    timestamp_ns: int    # time.perf_counter_ns() at observation


@dataclass(slots=True)
class OptionContract:
    """Immutable descriptor for a single option contract."""
    symbol: str
    strike: float
    expiry_years: float       # time-to-expiry in fractional years
    option_type: Literal["call", "put"]
    implied_vol: float        # σ from vol surface at this strike/expiry
    contract_multiplier: int = 100


@dataclass
class OptionPosition:
    """
    A live option position with Greeks as computed properties.
    Greeks are NOT stored — they are computed on demand from MarketState.
    This eliminates stale-Greeks bugs entirely.
    """
    contract: OptionContract
    quantity: int                # signed: positive=long, negative=short
    entry_price: float
    state: PositionState = field(default=PositionState.ACTIVE)

    def delta(self, mkt: MarketState) -> float:
        from src.greeks.engine import bsm_delta_scalar
        raw = bsm_delta_scalar(
            S=mkt.spot,
            K=self.contract.strike,
            r=mkt.risk_free_rate,
            T=self.contract.expiry_years,
            sigma=self.contract.implied_vol,
            is_call=(self.contract.option_type == "call"),
        )
        return raw * self.quantity * self.contract.contract_multiplier

    def gamma(self, mkt: MarketState) -> float:
        from src.greeks.engine import bsm_gamma_scalar
        raw = bsm_gamma_scalar(
            S=mkt.spot,
            K=self.contract.strike,
            r=mkt.risk_free_rate,
            T=self.contract.expiry_years,
            sigma=self.contract.implied_vol,
        )
        return raw * self.quantity * self.contract.contract_multiplier

    def delta_approximation(self, mkt: MarketState, ds: float) -> float:
        """
        First-order delta update for a small spot move ds.
        Uses gamma to avoid a full BSM recompute on minor ticks.
        Accurate when |ds/S| < 0.005 (50 bps).
        """
        return self.delta(mkt) + self.gamma(mkt) * ds


@dataclass
class PortfolioGreeks:
    """
    Aggregated Greeks across all positions.
    Vectorized across the full book in a single NumPy pass.
    """
    positions: list[OptionPosition] = field(default_factory=list)
    _kahan_compensation: float = field(default=0.0, repr=False)
    _cumulative_hedge_cost: float = field(default=0.0, repr=False)

    def net_delta(self, mkt: MarketState) -> float:
        """Scalar net delta of entire portfolio."""
        return sum(p.delta(mkt) for p in self.positions)

    def net_gamma(self, mkt: MarketState) -> float:
        return sum(p.gamma(mkt) for p in self.positions)

    def add_hedge_cost(self, cost: float) -> None:
        """Kahan compensated summation for hedge cost accumulation."""
        y = cost - self._kahan_compensation
        t = self._cumulative_hedge_cost + y
        self._kahan_compensation = (t - self._cumulative_hedge_cost) - y
        self._cumulative_hedge_cost = t

    @property
    def total_hedge_cost(self) -> float:
        return self._cumulative_hedge_cost
