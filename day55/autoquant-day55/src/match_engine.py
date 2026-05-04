"""
match_engine.py — Simulated match engine with microsecond latency recording.

Two execution paths:
  1. Alpaca Paper Trading (real HTTP RTT, requires .env keys)
  2. Pure simulation   (random sleep in configurable µs range, no keys needed)

The measurement discipline is identical on both paths:
  t1 = time.perf_counter_ns()   # last line before I/O
  <single I/O call>
  t2 = time.perf_counter_ns()   # first line after I/O
"""
from __future__ import annotations

import json
import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .timer import LatencyRecorder, LatencySample

# ---------------------------------------------------------------------------
# Optional Alpaca import — engine degrades gracefully without it
# ---------------------------------------------------------------------------
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
    from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

    _ALPACA_AVAILABLE = True
except ImportError:
    _ALPACA_AVAILABLE = False


@dataclass(frozen=True)
class MatchResult:
    """Immutable result of a single order submission."""

    order_id: str
    symbol: str
    side: str
    qty: float
    latency_sample: LatencySample
    filled: bool = True
    fill_price: Optional[float] = None
    source: str = "simulation"  # "alpaca" | "simulation"

    def to_dict(self) -> dict[str, object]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "filled": self.filled,
            "fill_price": self.fill_price,
            "source": self.source,
            **self.latency_sample.to_dict(),
        }


class EngineConfigError(Exception):
    pass


class SimulatedMatchEngine:
    """
    Single-threaded match engine with pluggable execution backend.

    Parameters
    ----------
    recorder        : LatencyRecorder  Shared ring-buffer recorder.
    api_key         : str              Alpaca paper API key (optional).
    secret_key      : str              Alpaca paper secret key (optional).
    paper           : bool             Always True for this lesson.
    sim_latency_range_us : tuple       (min_us, max_us) for simulation mode.
    log_path        : Path | None      If set, append JSONL records here.
    """

    def __init__(
        self,
        recorder: LatencyRecorder,
        api_key: str = "",
        secret_key: str = "",
        paper: bool = True,
        sim_latency_range_us: tuple[float, float] = (50_000.0, 500_000.0),
        log_path: Optional[Path] = None,
    ) -> None:
        self.recorder = recorder
        self._sim_range = sim_latency_range_us
        self._log_path = log_path
        self._client: Optional[object] = None
        self._source = "simulation"

        if api_key and secret_key:
            if not _ALPACA_AVAILABLE:
                raise EngineConfigError(
                    "alpaca-py is not installed. Run: pip install alpaca-py"
                )
            self._client = TradingClient(api_key, secret_key, paper=paper)
            self._source = "alpaca"

        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)

    def submit_order(
        self, symbol: str, qty: float, side: str
    ) -> MatchResult:
        """
        Submit a market order. Stamps T1/T2 around the I/O boundary only.

        Returns MatchResult with embedded LatencySample.
        """
        order_id = str(uuid.uuid4())
        fill_price: Optional[float] = None

        if self._client:
            # ── Alpaca paper path ──────────────────────────────────────────
            # Clearing open orders for this symbol avoids 403 wash-trade rejects
            # when flipping BUY/SELL before the prior market order settles.
            open_req = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                symbols=[symbol],
                limit=100,
            )
            for o in self._client.get_orders(open_req):  # type: ignore[union-attr]
                self._client.cancel_order_by_id(o.id)  # type: ignore[union-attr]

            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            t1_ns = time.perf_counter_ns()
            order = self._client.submit_order(req)  # type: ignore[union-attr]
            t2_ns = time.perf_counter_ns()
            order_id = str(order.id)
        else:
            # ── Pure simulation path ───────────────────────────────────────
            # Inject realistic latency distribution: log-normal centred on
            # 200ms for a paper API is typical; simulation uses uniform for
            # clean histogram shapes during testing.
            lat_us = random.uniform(*self._sim_range)
            t1_ns = time.perf_counter_ns()
            time.sleep(lat_us / 1_000_000.0)
            t2_ns = time.perf_counter_ns()

        sample = self.recorder.record(order_id, t1_ns, t2_ns)

        result = MatchResult(
            order_id=order_id,
            symbol=symbol,
            side=side.upper(),
            qty=qty,
            latency_sample=sample,
            filled=True,
            fill_price=fill_price,
            source=self._source,
        )

        if self._log_path:
            self._append_log(result)

        return result

    def _append_log(self, result: MatchResult) -> None:
        """Append a JSONL record. Opens/closes file per write (safe, not fast)."""
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(result.to_dict()) + "\n")
