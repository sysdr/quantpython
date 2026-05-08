"""
ATR-Scaled Slippage Model.

Model:
    slippage_bps = BASE_BPS + ATR_SCALAR * (ATR / MidPrice) * 10_000

Calibration:
    ATR_SCALAR is estimated via OLS on historical fill data.
    Default value (0.35) is a reasonable starting point for US mid-cap equities.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Final

_BPS_FACTOR: Final[float] = 10_000.0


class OrderSide(str, Enum):
    BUY = auto()
    SELL = auto()


@dataclass(frozen=True, slots=True)
class SlippageEstimate:
    """Immutable slippage estimate attached to a pending order."""
    symbol: str
    side: OrderSide
    mid_price: float
    atr: float
    predicted_bps: float
    adjusted_price: float

    @property
    def predicted_dollars(self) -> float:
        return self.mid_price * (self.predicted_bps / _BPS_FACTOR)

    def __str__(self) -> str:
        return (
            f"[{self.symbol} {self.side.upper()}] "
            f"mid={self.mid_price:.4f} atr={self.atr:.4f} "
            f"predicted={self.predicted_bps:.2f}bps "
            f"adj_price={self.adjusted_price:.4f}"
        )


@dataclass(slots=True)
class SlippageModel:
    """
    Parameterized linear slippage model.

    Parameters
    ----------
    base_bps : float
        Floor slippage cost (accounts for half-spread, fees). Default 3 bps.
    atr_scalar : float
        Multiplier mapping ATR/Price ratio to additional slippage bps.
        Calibrate per-symbol against historical fill data. Default 0.35.
    max_bps : float
        Hard cap on predicted slippage. Prevents runaway estimates during
        black swan events. Default 50 bps.
    """

    base_bps: float = 3.0
    atr_scalar: float = 0.35
    max_bps: float = 50.0

    def __post_init__(self) -> None:
        if self.base_bps < 0:
            raise ValueError("base_bps must be non-negative")
        if self.atr_scalar < 0:
            raise ValueError("atr_scalar must be non-negative")
        if self.max_bps <= self.base_bps:
            raise ValueError("max_bps must exceed base_bps")

    def estimate(
        self,
        symbol: str,
        side: OrderSide,
        mid_price: float,
        atr: float,
    ) -> SlippageEstimate:
        """
        Compute slippage estimate for an order.

        The adjusted_price is what we *expect* to pay (buy) or receive (sell)
        after slippage — use this for P&L pre-attribution.
        """
        if mid_price <= 0:
            raise ValueError(f"mid_price must be positive, got {mid_price}")
        if atr < 0:
            raise ValueError(f"atr must be non-negative, got {atr}")

        volatility_component = self.atr_scalar * (atr / mid_price) * _BPS_FACTOR
        raw_bps = self.base_bps + volatility_component
        predicted_bps = min(raw_bps, self.max_bps)

        # Price adjustment: buys pay more, sells receive less
        match side:
            case OrderSide.BUY:
                adjusted = mid_price * (1.0 + predicted_bps / _BPS_FACTOR)
            case OrderSide.SELL:
                adjusted = mid_price * (1.0 - predicted_bps / _BPS_FACTOR)
            case _:
                raise ValueError(f"Unknown side: {side}")

        return SlippageEstimate(
            symbol=symbol,
            side=side,
            mid_price=mid_price,
            atr=atr,
            predicted_bps=predicted_bps,
            adjusted_price=adjusted,
        )

    def realized_slippage_bps(
        self, mid_price: float, fill_price: float, side: OrderSide
    ) -> float:
        """
        Compute actual slippage in bps from a confirmed fill.

        Positive = slippage worked against us (normal).
        Negative = price improvement (rare, lucky).
        """
        if mid_price <= 0:
            raise ValueError("mid_price must be positive")
        match side:
            case OrderSide.BUY:
                delta = fill_price - mid_price
            case OrderSide.SELL:
                delta = mid_price - fill_price
            case _:
                raise ValueError(f"Unknown side: {side}")
        return (delta / mid_price) * _BPS_FACTOR

    def model_error_bps(
        self, estimate: SlippageEstimate, fill_price: float
    ) -> float:
        """Signed error: predicted - realized. Positive = overestimated cost."""
        realized = self.realized_slippage_bps(
            estimate.mid_price, fill_price, estimate.side
        )
        return estimate.predicted_bps - realized
