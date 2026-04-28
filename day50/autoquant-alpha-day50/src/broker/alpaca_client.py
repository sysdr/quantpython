"""
Alpaca Paper Trading client with arrival-price tracking.
Pattern: capture quote → submit order → poll fill → compute slippage.
Production note: replace poll loop with WebSocket stream for live trading.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Graceful import: falls back to simulation mode if alpaca-py not configured
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest
    _ALPACA_AVAILABLE = True
except ImportError:
    _ALPACA_AVAILABLE = False
    logger.warning("alpaca-py not installed. Using simulation mode.")

from src.engine.fill_engine import (
    Quote, Side, FillResult, compute_arrival_price
)
from src.engine.slippage_tracker import SlippageTracker


class MarketClosedError(RuntimeError):
    """Raised when submitting a live equity order while Alpaca reports the market closed."""


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


class AlpacaPaperClient:
    """
    Wraps Alpaca paper trading with arrival-price discipline.
    Every order submission captures a pre-flight quote.
    """

    FILL_POLL_INTERVAL_S: float = 0.25
    FILL_TIMEOUT_S: float = 30.0

    def __init__(self) -> None:
        self.tracker = SlippageTracker(window=500)
        force_sim = _env_flag("ALPACA_SIMULATION")

        api_key = os.getenv("ALPACA_API_KEY", "")
        secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        placeholder = {"", "your_paper_api_key_here", "your_paper_secret_key_here"}
        keys_ok = (
            api_key not in placeholder
            and secret_key not in placeholder
            and len(api_key) > 8
            and len(secret_key) > 8
        )

        if force_sim:
            self._sim_mode = True
            logger.info("Running in SIMULATION mode (ALPACA_SIMULATION is set).")
        elif not _ALPACA_AVAILABLE:
            self._sim_mode = True
            logger.info("Running in SIMULATION mode (no API keys or alpaca-py).")
        elif keys_ok:
            self._sim_mode = False
            self._trading = TradingClient(
                api_key=api_key,
                secret_key=secret_key,
                paper=True,
                url_override=base_url,
            )
            self._data = StockHistoricalDataClient(
                api_key=api_key,
                secret_key=secret_key,
            )
            logger.info("Alpaca Paper client initialized (live mode).")
        else:
            self._sim_mode = True
            logger.info("Running in SIMULATION mode (placeholder or missing API keys).")

    def _fill_timeout_s(self) -> float:
        raw = os.getenv("ALPACA_FILL_TIMEOUT_S", "").strip()
        if raw:
            try:
                return max(5.0, float(raw))
            except ValueError:
                pass
        return self.FILL_TIMEOUT_S

    def _ensure_market_open(self) -> None:
        """
        DAY market orders rest until the next session; polling would always time out when closed.
        """
        try:
            clock = self._trading.get_clock()
        except Exception as e:
            logger.warning("Could not fetch Alpaca market clock (%s); proceeding anyway.", e)
            return
        if clock.is_open:
            return
        nxt = clock.next_open.isoformat() if clock.next_open else "unknown"
        raise MarketClosedError(
            f"Alpaca reports the market is closed (next_open={nxt}). "
            "Equity market orders only fill while the session is open; run again during regular hours "
            "or use simulation mode without live keys."
        )

    async def get_quote(self, symbol: str) -> Quote:
        if self._sim_mode:
            return self._synthetic_quote(symbol)
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        raw = self._data.get_stock_latest_quote(req)
        q = raw[symbol]
        return Quote.from_floats(float(q.bid_price), float(q.ask_price))

    async def submit_with_arrival_tracking(
        self,
        symbol: str,
        qty: Decimal,
        side: Side,
    ) -> FillResult:
        """
        THE PATTERN:
        1. Capture quote (arrival price locked in)
        2. Submit market order
        3. Await fill confirmation
        4. Compute + record slippage
        """
        # Step 1: Lock arrival quote (skip pointless quote/API when venue is closed)
        if not self._sim_mode:
            self._ensure_market_open()
        arrival_quote = await self.get_quote(symbol)
        arrival_price = compute_arrival_price(arrival_quote, side)
        logger.info(
            f"Arrival quote {symbol}: bid={arrival_quote.bid} ask={arrival_quote.ask} "
            f"mid={arrival_quote.mid} spread={arrival_quote.spread_bps:.2f}bps"
        )

        # Step 2: Submit
        if self._sim_mode:
            fill = await self._simulate_fill(
                symbol, qty, side, arrival_quote, arrival_price
            )
        else:
            fill = await self._live_fill(
                symbol, qty, side, arrival_quote, arrival_price
            )

        # Step 3: Record
        self.tracker.record(fill.slippage_bps)
        logger.info(fill.summary())
        return fill

    async def _live_fill(
        self,
        symbol: str,
        qty: Decimal,
        side: Side,
        arrival_quote: Quote,
        arrival_price: Decimal,
    ) -> FillResult:
        order_side = OrderSide.BUY if side == Side.BUY else OrderSide.SELL
        req = MarketOrderRequest(
            symbol=symbol,
            qty=float(qty),
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = self._trading.submit_order(req)
        logger.info(f"Order submitted: {order.id}")

        # Poll for fill (replace with WebSocket in production)
        fill_price = await self._poll_for_fill(str(order.id), qty)

        return FillResult(
            order_id=str(order.id),
            symbol=symbol,
            side=side,
            qty=qty,
            arrival_mid=arrival_quote.mid,
            arrival_price=arrival_price,
            fill_price=fill_price,
            fill_timestamp_ns=time.time_ns(),
        )

    async def _poll_for_fill(self, order_id: str, qty: Decimal) -> Decimal:
        """Production note: this is a polling fallback. Use order stream in prod."""
        timeout_s = self._fill_timeout_s()
        deadline = time.monotonic() + timeout_s
        terminal_bad = frozenset(
            (
                OrderStatus.CANCELED,
                OrderStatus.REJECTED,
                OrderStatus.EXPIRED,
                OrderStatus.STOPPED,
                OrderStatus.SUSPENDED,
                OrderStatus.REPLACED,
            )
        )
        qty_f = float(qty)
        while time.monotonic() < deadline:
            order = self._trading.get_order_by_id(order_id)
            st = order.status
            if st in terminal_bad:
                raise RuntimeError(
                    f"Order {order_id} ended without fill (status={st}). "
                    "Check Alpaca dashboard for rejects or constraints."
                )
            filled_qty = float(order.filled_qty or 0)
            if order.filled_avg_price and (
                st == OrderStatus.FILLED or filled_qty + 1e-9 >= qty_f
            ):
                return Decimal(str(order.filled_avg_price))
            await asyncio.sleep(self.FILL_POLL_INTERVAL_S)

        order = self._trading.get_order_by_id(order_id)
        fq = getattr(order, "filled_qty", None)
        st = getattr(order, "status", "?")
        raise TimeoutError(
            f"Order {order_id} did not fill within {timeout_s}s (status={st}, filled_qty={fq}). "
            "If the market just closed, try again later; you can raise ALPACA_FILL_TIMEOUT_S for slow paper fills."
        )

    async def _simulate_fill(
        self,
        symbol: str,
        qty: Decimal,
        side: Side,
        arrival_quote: Quote,
        arrival_price: Decimal,
    ) -> FillResult:
        """
        Simulation: fills at arrival price ± small random noise to model
        real-world micro-slippage (queue position, latency jitter).
        """
        import random
        import uuid
        await asyncio.sleep(0.05)  # Simulate network round-trip

        # Model: fill price = arrival_price + N(0, 0.5bps) noise
        noise_bps = random.gauss(0.5, 0.8)  # slight positive bias (realistic)
        noise_abs = float(arrival_price) * noise_bps / 10_000
        fill_float = float(arrival_price) + noise_abs
        fill_price = Decimal(str(round(fill_float, 4)))

        return FillResult(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            qty=qty,
            arrival_mid=arrival_quote.mid,
            arrival_price=arrival_price,
            fill_price=fill_price,
            fill_timestamp_ns=time.time_ns(),
        )

    def _synthetic_quote(self, symbol: str) -> Quote:
        """Synthetic NBBO for simulation mode."""
        import random
        base_prices = {
            "SPY": 520.0, "QQQ": 435.0, "AAPL": 185.0,
            "TSLA": 175.0, "NVDA": 875.0,
        }
        mid = base_prices.get(symbol, 100.0)
        spread_pct = 0.0002  # 2bps
        half = mid * spread_pct / 2
        jitter = random.uniform(-0.01, 0.01)
        return Quote.from_floats(
            bid=mid - half + jitter,
            ask=mid + half + jitter,
        )
