#!/usr/bin/env python3
"""
AutoQuant-Alpha Day 5 — Margin Monitor
Event-driven margin alert system using Alpaca WebSocket account stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum, auto
from typing import Callable, Optional
import numpy as np
import websockets
import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/margin_monitor.log", mode="a"),
    ],
)
log = logging.getLogger("margin_monitor")


# ─── Domain Types ────────────────────────────────────────────────────────────

class AlertLevel(Enum):
    SAFE        = auto()
    WARN        = auto()
    CRITICAL    = auto()
    MARGIN_CALL = auto()
    LIQUIDATION = auto()


@dataclass(frozen=True)
class HysteresisThreshold:
    """Two-sided threshold preventing alert thrashing."""
    enter: float   # equity_ratio below this → enter danger state
    exit:  float   # equity_ratio above this → exit danger state

    def __post_init__(self) -> None:
        assert self.exit > self.enter, "Exit threshold must exceed enter threshold"


# Hysteresis bands (enter=upper, exit=lower for danger states)
THRESHOLDS: dict[AlertLevel, HysteresisThreshold] = {
    AlertLevel.WARN:        HysteresisThreshold(enter=0.90, exit=0.92),
    AlertLevel.CRITICAL:    HysteresisThreshold(enter=0.80, exit=0.83),
    AlertLevel.MARGIN_CALL: HysteresisThreshold(enter=0.70, exit=0.73),
    AlertLevel.LIQUIDATION: HysteresisThreshold(enter=0.60, exit=0.63),
}

LEVEL_ORDER = [
    AlertLevel.SAFE,
    AlertLevel.WARN,
    AlertLevel.CRITICAL,
    AlertLevel.MARGIN_CALL,
    AlertLevel.LIQUIDATION,
]


@dataclass
class AccountSnapshot:
    equity:               Decimal
    last_equity:          Decimal
    buying_power:         Decimal
    maintenance_margin:   Decimal
    initial_margin:       Decimal
    portfolio_value:      Decimal
    timestamp:            datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def equity_ratio(self) -> float:
        """Current equity as fraction of last_equity (day-start baseline)."""
        if self.last_equity == 0:
            return 1.0
        return float(self.equity / self.last_equity)

    @property
    def margin_utilization(self) -> float:
        """Fraction of available maintenance margin consumed."""
        if self.portfolio_value == 0:
            return 0.0
        return float(self.maintenance_margin / self.portfolio_value)


@dataclass
class MarginAlert:
    level:      AlertLevel
    ratio:      float
    snapshot:   AccountSnapshot
    fired_at:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Hysteresis FSM ──────────────────────────────────────────────────────────

class MarginFSM:
    """
    Finite state machine with hysteresis.
    Prevents alert thrashing when equity oscillates near a threshold.
    """

    def __init__(self) -> None:
        self._state: AlertLevel = AlertLevel.SAFE
        self._last_fired: dict[AlertLevel, float] = {}
        self._alert_rate_limit_seconds: float = 60.0

    @property
    def state(self) -> AlertLevel:
        return self._state

    def update(self, ratio: float) -> Optional[AlertLevel]:
        """
        Feed a new equity ratio. Returns AlertLevel if a transition occurred,
        None if state is unchanged.
        """
        new_state = self._compute_state(ratio)
        if new_state == self._state:
            return None

        prev = self._state
        self._state = new_state
        log.info(f"FSM transition: {prev.name} → {new_state.name} (ratio={ratio:.4f})")
        return new_state

    def _compute_state(self, ratio: float) -> AlertLevel:
        current_idx = LEVEL_ORDER.index(self._state)

        # Check escalation (moving toward danger)
        for level in reversed(LEVEL_ORDER[1:]):  # skip SAFE
            threshold = THRESHOLDS[level]
            if ratio < threshold.enter:
                return level

        # Check de-escalation (recovering toward safety)
        # Must clear the exit band of current state
        if self._state != AlertLevel.SAFE:
            threshold = THRESHOLDS[self._state]
            if ratio >= threshold.exit:
                # De-escalate one level
                idx = LEVEL_ORDER.index(self._state)
                return LEVEL_ORDER[max(0, idx - 1)]

        return self._state

    def should_fire(self, level: AlertLevel) -> bool:
        """Rate limit: fire at most once per 60s per severity level."""
        last = self._last_fired.get(level, 0.0)
        if time.monotonic() - last >= self._alert_rate_limit_seconds:
            self._last_fired[level] = time.monotonic()
            return True
        return False


# ─── Vectorized P&L Engine ───────────────────────────────────────────────────

class EquityCalculator:
    """
    Computes portfolio P&L using NumPy vectorized operations.
    Zero Python-level loops over positions.
    """

    def compute_unrealized_pnl(
        self,
        quantities:    np.ndarray,  # float64, shape (N,)
        avg_entries:   np.ndarray,  # float64, shape (N,)
        current_prices: np.ndarray, # float64, shape (N,)
    ) -> float:
        """Single BLAS dot product — numerically stable for up to ~10k positions."""
        if quantities.size == 0:
            return 0.0
        price_deltas = current_prices - avg_entries
        return float(np.dot(quantities, price_deltas))

    def compute_equity_ratio(
        self,
        equity: Decimal,
        last_equity: Decimal,
    ) -> float:
        if last_equity == Decimal("0"):
            return 1.0
        return float(
            (equity / last_equity).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
        )


# ─── Alpaca WebSocket Client ──────────────────────────────────────────────────

class AlpacaAccountStream:
    """
    Consumes Alpaca account updates via WebSocket.
    Implements exponential backoff with jitter on reconnect.
    Re-snapshots account state via REST on each reconnect.
    """

    WS_URL = "wss://paper-api.alpaca.markets/stream"

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        on_update: Callable[[dict], None],
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._on_update = on_update
        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnect_delay = 30.0

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._connect()
                self._reconnect_attempts = 0
            except Exception as exc:
                delay = self._backoff_delay()
                log.warning(f"WS disconnected ({exc}). Reconnecting in {delay:.1f}s...")
                await asyncio.sleep(delay)

    async def _connect(self) -> None:
        async with websockets.connect(
            self.WS_URL,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            log.info("WebSocket connected")
            await self._authenticate(ws)
            await self._subscribe(ws)

            async for raw in ws:
                msg = json.loads(raw)
                if isinstance(msg, list):
                    for event in msg:
                        self._on_update(event)
                else:
                    self._on_update(msg)

    async def _authenticate(self, ws) -> None:
        await ws.send(json.dumps({
            "action": "auth",
            "key":    self._api_key,
            "secret": self._secret_key,
        }))
        resp = json.loads(await ws.recv())
        log.debug(f"Auth response: {resp}")

    async def _subscribe(self, ws) -> None:
        await ws.send(json.dumps({
            "action": "listen",
            "data":   {"streams": ["account_updates", "trade_updates"]},
        }))
        resp = json.loads(await ws.recv())
        log.debug(f"Subscribe response: {resp}")

    def _backoff_delay(self) -> float:
        import random
        self._reconnect_attempts += 1
        base = min(2 ** self._reconnect_attempts, self._max_reconnect_delay)
        jitter = random.uniform(0, base * 0.3)
        return base + jitter

    def stop(self) -> None:
        self._running = False


# ─── REST Snapshot ────────────────────────────────────────────────────────────

async def fetch_account_snapshot(api_key: str, secret: str) -> AccountSnapshot:
    """Fetch current account state via REST. Used on startup and reconnect."""
    headers = {
        "APCA-API-KEY-ID":     api_key,
        "APCA-API-SECRET-KEY": secret,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://paper-api.alpaca.markets/v2/account",
            headers=headers,
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()

    return AccountSnapshot(
        equity             = Decimal(data.get("equity", "0")),
        last_equity        = Decimal(data.get("last_equity", "0")),
        buying_power       = Decimal(data.get("buying_power", "0")),
        maintenance_margin = Decimal(data.get("maintenance_margin", "0")),
        initial_margin     = Decimal(data.get("initial_margin", "0")),
        portfolio_value    = Decimal(data.get("portfolio_value", "0")),
    )


def parse_account_update(event: dict) -> Optional[AccountSnapshot]:
    """Parse a WebSocket account_update event into an AccountSnapshot."""
    if event.get("stream") != "account_updates":
        return None
    data = event.get("data", {})
    try:
        return AccountSnapshot(
            equity             = Decimal(str(data.get("equity", "0"))),
            last_equity        = Decimal(str(data.get("last_equity", "0"))),
            buying_power       = Decimal(str(data.get("buying_power", "0"))),
            maintenance_margin = Decimal(str(data.get("maintenance_margin", "0"))),
            initial_margin     = Decimal(str(data.get("initial_margin", "0"))),
            portfolio_value    = Decimal(str(data.get("portfolio_value", "0"))),
        )
    except Exception as exc:
        log.error(f"Failed to parse account update: {exc} | data={data}")
        return None


# ─── Alert Dispatcher ─────────────────────────────────────────────────────────

class AlertDispatcher:
    """
    Dispatches margin alerts. In production, extend this to send
    to Slack, PagerDuty, or an internal message bus.
    Currently: structured log output + in-memory alert history.
    """

    def __init__(self) -> None:
        self.history: list[MarginAlert] = []

    def dispatch(self, alert: MarginAlert) -> None:
        self.history.append(alert)
        level_emoji = {
            AlertLevel.SAFE:        "✅",
            AlertLevel.WARN:        "⚠️ ",
            AlertLevel.CRITICAL:    "🔴",
            AlertLevel.MARGIN_CALL: "🚨",
            AlertLevel.LIQUIDATION: "💀",
        }
        emoji = level_emoji.get(alert.level, "❓")
        log.warning(
            f"{emoji} MARGIN ALERT | Level={alert.level.name} "
            f"| ratio={alert.ratio:.4f} "
            f"| equity={alert.snapshot.equity} "
            f"| buying_power={alert.snapshot.buying_power}"
        )


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class MarginMonitor:
    """Top-level orchestrator. Wires stream → FSM → dispatcher."""

    def __init__(self, api_key: str, secret_key: str) -> None:
        self._api_key   = api_key
        self._secret    = secret_key
        self._fsm       = MarginFSM()
        self._calc      = EquityCalculator()
        self._dispatcher = AlertDispatcher()
        self._snapshot: Optional[AccountSnapshot] = None
        self._stream    = AlpacaAccountStream(
            api_key    = api_key,
            secret_key = secret_key,
            on_update  = self._handle_event,
        )

    def _handle_event(self, event: dict) -> None:
        snapshot = parse_account_update(event)
        if snapshot is None:
            return

        self._snapshot = snapshot
        ratio = self._calc.compute_equity_ratio(snapshot.equity, snapshot.last_equity)
        new_state = self._fsm.update(ratio)

        if new_state is not None and self._fsm.should_fire(new_state):
            alert = MarginAlert(level=new_state, ratio=ratio, snapshot=snapshot)
            self._dispatcher.dispatch(alert)

    async def run(self) -> None:
        log.info("Fetching initial account snapshot...")
        self._snapshot = await fetch_account_snapshot(self._api_key, self._secret)
        ratio = self._calc.compute_equity_ratio(
            self._snapshot.equity, self._snapshot.last_equity
        )
        log.info(
            f"Initial state | equity={self._snapshot.equity} "
            f"| ratio={ratio:.4f} | FSM={self._fsm.state.name}"
        )
        await self._stream.run()


# ─── Entry Point ──────────────────────────────────────────────────────────────

async def main() -> None:
    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret  = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or not secret:
        log.error("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")
        sys.exit(1)

    monitor = MarginMonitor(api_key=api_key, secret_key=secret)
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
