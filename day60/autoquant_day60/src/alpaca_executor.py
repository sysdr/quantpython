"""
Alpaca Paper Trading Executor with ATR-Slippage Pre-Attribution.

This module:
1. Fetches latest quote (mid price) from Alpaca
2. Computes ATR-based slippage estimate
3. Submits market order
4. Reconciles predicted vs realized slippage on fill
5. Logs everything via OrderLogger (non-blocking)
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

from src.atr_engine import ATREngine, OHLCTick, compute_atr_series
from src.slippage_model import OrderSide, SlippageModel
from src.order_logger import OrderLogger, OrderRecord

import numpy as np


def _to_alpaca_side(side: OrderSide) -> AlpacaSide:
    return AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL


class AlpacaSlippageExecutor:
    """
    End-to-end execution pipeline with ATR slippage pre-attribution.

    Parameters
    ----------
    symbol : str
    quantity : int
        Shares to trade.
    side : OrderSide
    atr_period : int
        Lookback for ATR computation (default 14).
    model : SlippageModel | None
        If None, uses default model parameters.
    log_path : Path
        Where to write JSONL order log.
    """

    def __init__(
        self,
        symbol: str,
        quantity: int,
        side: OrderSide = OrderSide.BUY,
        atr_period: int = 14,
        model: SlippageModel | None = None,
        log_path: Path = Path("data/orders.jsonl"),
    ) -> None:
        api_key = os.environ["ALPACA_API_KEY"]
        secret_key = os.environ["ALPACA_SECRET_KEY"]
        base_url = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

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
        self.symbol = symbol
        self.quantity = quantity
        self.side = side
        self._atr_period = atr_period
        self._model = model or SlippageModel()
        self._logger = OrderLogger(log_path)
        self._logger.start()

    def execute(self) -> OrderRecord:
        """
        Full execution cycle: quote → ATR → slippage estimate → order → reconcile.
        Returns the completed OrderRecord.
        """
        t0 = time.perf_counter()

        # Step 1: Get mid price from latest quote
        quote_req = StockLatestQuoteRequest(
            symbol_or_symbols=self.symbol,
            feed=DataFeed.IEX,
        )
        latest_quotes = self._data.get_stock_latest_quote(quote_req)
        if self.symbol not in latest_quotes:
            available = ", ".join(sorted(latest_quotes.keys())) or "(none)"
            raise RuntimeError(
                f"No latest quote returned for {self.symbol}. "
                f"Available symbols in response: {available}. "
                "This often means your market data feed entitlement doesn't match the request; "
                "try IEX (default in this project) or check your Alpaca plan / symbol."
            )
        quote = latest_quotes[self.symbol]
        mid_price = (quote.ask_price + quote.bid_price) / 2.0

        # Step 2: Compute ATR from recent daily bars (last 30 days)
        atr = self._compute_atr()

        # Step 3: Slippage estimate
        estimate = self._model.estimate(
            symbol=self.symbol,
            side=self.side,
            mid_price=mid_price,
            atr=atr,
        )
        print(f"[SLIPPAGE ESTIMATE] {estimate}")

        # Step 4: Submit market order
        ts_utc = datetime.now(timezone.utc).isoformat()
        order_request = MarketOrderRequest(
            symbol=self.symbol,
            qty=self.quantity,
            side=_to_alpaca_side(self.side),
            time_in_force=TimeInForce.DAY,
        )
        order = self._trading.submit_order(order_request)
        alpaca_id = str(order.id)
        print(f"[ORDER SUBMITTED] id={alpaca_id} status={order.status}")

        # Step 5: Poll for fill (paper trading fills near-instantly)
        fill_price: float | None = None
        for _ in range(20):
            time.sleep(0.25)
            filled = self._trading.get_order_by_id(alpaca_id)
            if filled.filled_avg_price is not None:
                fill_price = float(filled.filled_avg_price)
                break

        latency_ms = (time.perf_counter() - t0) * 1000.0

        # Step 6: Reconcile
        realized_bps: float | None = None
        error_bps: float | None = None
        status = "SUBMITTED"

        if fill_price is not None:
            realized_bps = self._model.realized_slippage_bps(
                mid_price, fill_price, self.side
            )
            error_bps = self._model.model_error_bps(estimate, fill_price)
            status = "FILLED"
            print(
                f"[FILL RECONCILED] fill={fill_price:.4f} "
                f"realized={realized_bps:.2f}bps error={error_bps:.2f}bps"
            )

        record = OrderRecord(
            symbol=self.symbol,
            side=str(self.side),
            quantity=self.quantity,
            mid_price=mid_price,
            atr=atr,
            predicted_slippage_bps=estimate.predicted_bps,
            adjusted_price=estimate.adjusted_price,
            alpaca_order_id=alpaca_id,
            fill_price=fill_price,
            realized_slippage_bps=realized_bps,
            model_error_bps=error_bps,
            status=status,
            timestamp_utc=ts_utc,
            latency_ms=latency_ms,
        )
        self._logger.log(record)
        return record

    def _compute_atr(self) -> float:
        """Fetch 30 daily bars and compute ATR[14]."""
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        import pandas as pd

        bars_req = StockBarsRequest(
            symbol_or_symbols=self.symbol,
            timeframe=TimeFrame.Day,
            limit=30,
            feed=DataFeed.IEX,
        )
        bars_resp = self._data.get_stock_bars(bars_req)
        if self.symbol not in bars_resp:
            available = ", ".join(sorted(bars_resp.keys())) or "(none)"
            raise RuntimeError(
                f"No bars returned for {self.symbol}. "
                f"Available symbols in response: {available}. "
                "This is commonly caused by market data entitlement (SIP vs IEX) or an invalid symbol."
            )
        bars = bars_resp[self.symbol]

        highs = np.array([b.high for b in bars], dtype=np.float64)
        lows = np.array([b.low for b in bars], dtype=np.float64)
        closes = np.array([b.close for b in bars], dtype=np.float64)

        atr_series = compute_atr_series(highs, lows, closes, self._atr_period)
        # Last non-NaN value
        valid = atr_series[~np.isnan(atr_series)]
        if len(valid) == 0:
            raise RuntimeError("Insufficient bars to compute ATR")
        return float(valid[-1])

    def shutdown(self) -> None:
        self._logger.stop()
