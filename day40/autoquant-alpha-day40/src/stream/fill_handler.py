from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.models.order_lifecycle import FillEvent
from src.tracking.lifecycle_tracker import LifecycleTracker

log = logging.getLogger(__name__)

try:
    from alpaca.trading.stream import TradingStream
    from alpaca.trading.enums import TradeEvent
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    log.warning("alpaca-py not installed — FillStreamHandler in simulation-only mode")


def _parse_ts(ts: Any) -> datetime:
    """Normalise Alpaca timestamp to UTC-aware datetime."""
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc)
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    return datetime.now(timezone.utc)


class FillStreamHandler:
    """
    Bridges Alpaca TradingStream WebSocket events to LifecycleTracker.

    Timestamp contract
    ------------------
    local_receipt_at = datetime.now(timezone.utc) is the FIRST statement
    executed in _handle_trade_update — before any await, any attribute
    access, any other computation. This minimises measurement noise.

    broker_timestamp = data.timestamp (Alpaca server-side event time, UTC).
    This is NOT exchange fill time (requires co-location data for that).

    Reconnection: exponential backoff, 1s→60s cap.
    """

    def __init__(
        self,
        tracker: LifecycleTracker,
        api_key: str,
        secret_key: str,
        paper: bool = True,
    ) -> None:
        self._tracker = tracker
        self._api_key = api_key
        self._secret_key = secret_key
        self._paper = paper

    def _build_stream(self) -> Any:
        if not ALPACA_AVAILABLE:
            raise RuntimeError("alpaca-py not installed")
        stream = TradingStream(self._api_key, self._secret_key, paper=self._paper)
        stream.subscribe_trade_updates(self._handle_trade_update)
        return stream

    async def _handle_trade_update(self, data: Any) -> None:
        # ⚠ Capture local receipt time FIRST — before any other work
        local_receipt_at = datetime.now(timezone.utc)

        event_type = getattr(data, "event", None)
        order = getattr(data, "order", None)
        if order is None:
            return

        order_id = str(order.id)
        broker_ts = _parse_ts(getattr(data, "timestamp", None))

        if event_type == TradeEvent.ACCEPTED:
            await self._tracker.mark_accepted(order_id, broker_ts)
            log.info("ACCEPTED order_id=%s broker_ts=%s", order_id, broker_ts.isoformat())

        elif event_type in (TradeEvent.FILL, TradeEvent.PARTIAL_FILL):
            qty   = float(getattr(data, "qty",   None) or getattr(order, "filled_qty", 0) or 0)
            price = float(getattr(data, "price", None) or getattr(order, "filled_avg_price", 0) or 0)

            fill = FillEvent(
                fill_id=str(uuid.uuid4()),
                qty=qty,
                price=price,
                broker_timestamp=broker_ts,
                local_receipt_at=local_receipt_at,
            )
            lc = await self._tracker.on_fill_event(order_id, fill)
            if lc:
                net_lat = fill.network_latency_ms()
                if net_lat < 0:
                    log.warning("Negative network latency %.2fms on order %s — NTP skew?",
                                net_lat, order_id)
                log.info(
                    "FILL %s order_id=%s state=%s filled=%.4f/%.4f avg_px=%.4f net_lat=%.2fms",
                    event_type.value,
                    order_id,
                    lc.state.value,
                    lc.filled_qty,
                    lc.qty,
                    lc.avg_fill_price,
                    net_lat,
                )

        elif event_type == TradeEvent.CANCELED:
            await self._tracker.mark_cancelled(order_id)
            log.info("CANCELLED order_id=%s", order_id)

        elif event_type in (TradeEvent.REJECTED, TradeEvent.EXPIRED):
            log.info("TERMINAL event=%s order_id=%s", event_type, order_id)

    async def run(self) -> None:
        """Run stream with exponential-backoff reconnection."""
        backoff = 1.0
        while True:
            try:
                stream = self._build_stream()
                log.info("TradingStream connecting (paper=%s)…", self._paper)
                await stream._run_forever()
                backoff = 1.0
            except Exception as exc:
                log.error("Stream error: %s — reconnecting in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
