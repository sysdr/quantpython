"""
src/execution/hedge_engine.py
Delta hedge engine: monitors net portfolio delta and fires equity orders
via Alpaca when the delta band is breached.
"""
from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from src.greeks.models import PortfolioGreeks, MarketState

logger = logging.getLogger(__name__)


@dataclass
class HedgeConfig:
    underlying_symbol: str = "SPY"
    delta_threshold: float = 5.0       # hedge when |net_delta| exceeds this
    spread_cost_bps: float = 2.0       # expected round-trip spread in bps
    min_hedge_interval_s: float = 5.0  # enforce minimum time between hedges


@dataclass
class HedgeResult:
    order_id: str
    shares_ordered: int
    side: str
    delta_before: float
    delta_after_estimate: float
    timestamp_ns: int
    slippage_bps: float | None = None   # filled post-execution


class DeltaHedgeEngine:
    """
    Monitors PortfolioGreeks and fires hedging orders when delta band breached.

    Threading model: single-threaded. Call check_and_hedge() from your
    main event loop. Do NOT call from multiple threads — TradingClient
    is not thread-safe.
    """

    def __init__(self, portfolio: PortfolioGreeks, config: HedgeConfig):
        self.portfolio = portfolio
        self.config = config
        self._last_hedge_ns: int = 0
        self._hedge_history: list[HedgeResult] = []

        api_key = os.environ.get("ALPACA_API_KEY", "")
        secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
        paper = os.environ.get("ALPACA_BASE_URL", "").find("paper") >= 0

        if api_key and secret_key:
            self._client = TradingClient(
                api_key=api_key,
                secret_key=secret_key,
                paper=paper,
            )
            logger.info("Alpaca TradingClient initialized (paper=%s)", paper)
        else:
            self._client = None
            logger.warning("No Alpaca credentials — hedge orders will be simulated")

    def check_and_hedge(self, mkt: MarketState) -> HedgeResult | None:
        """
        Core hedge logic. Returns HedgeResult if order was placed, else None.
        """
        now_ns = time.perf_counter_ns()
        elapsed_s = (now_ns - self._last_hedge_ns) / 1e9

        if elapsed_s < self.config.min_hedge_interval_s:
            return None

        net_delta = self.portfolio.net_delta(mkt)

        if abs(net_delta) <= self.config.delta_threshold:
            return None

        # Hedge shares = -net_delta / contract_multiplier
        # (net_delta already accounts for multiplier from OptionPosition.delta)
        shares = -round(net_delta / 100)   # approximate: 1 share = delta 1
        if shares == 0:
            return None

        side = OrderSide.BUY if shares > 0 else OrderSide.SELL
        abs_shares = abs(shares)

        logger.info(
            "Hedge triggered: net_delta=%.2f, ordering %d shares %s %s",
            net_delta, abs_shares, side.value, self.config.underlying_symbol,
        )

        order_id = self._submit_order(abs_shares, side)

        result = HedgeResult(
            order_id=order_id,
            shares_ordered=abs_shares,
            side=side.value,
            delta_before=net_delta,
            delta_after_estimate=net_delta + shares * 100,  # rough
            timestamp_ns=now_ns,
        )
        self._hedge_history.append(result)
        self._last_hedge_ns = now_ns
        self.portfolio.add_hedge_cost(abs_shares * mkt.spot * self.config.spread_cost_bps / 10000)

        return result

    def _submit_order(self, qty: int, side: OrderSide) -> str:
        if self._client is None:
            simulated_id = f"SIM-{int(time.time_ns())}"
            logger.info("Simulated order: id=%s qty=%d side=%s", simulated_id, qty, side.value)
            return simulated_id

        req = MarketOrderRequest(
            symbol=self.config.underlying_symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
        order = self._client.submit_order(req)
        return str(order.id)

    @property
    def hedge_history(self) -> list[HedgeResult]:
        return list(self._hedge_history)
