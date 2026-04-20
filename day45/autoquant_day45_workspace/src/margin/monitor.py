"""
margin/monitor.py
Background thread polling MarginAccount health and emitting state transitions.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional

from .account import MarginAccount, MarginHealth, MarginSnapshot


@dataclass
class HealthTransition:
    from_health: MarginHealth
    to_health: MarginHealth
    margin_ratio: Decimal
    equity: Decimal
    timestamp_ns: int


class MarginMonitor:
    """
    Runs a daemon thread at `interval_ms` heartbeat.
    Publishes HealthTransition events to `event_queue` on state changes.
    Optional `on_margin_call` callback fires synchronously on MARGIN_CALL/LIQUIDATING.
    """

    def __init__(
        self,
        account: MarginAccount,
        event_queue: queue.Queue,
        interval_ms: int = 500,
        on_margin_call: Optional[Callable[[HealthTransition], None]] = None,
    ) -> None:
        self._account = account
        self._event_queue = event_queue
        self._interval_s = interval_ms / 1000.0
        self._on_margin_call = on_margin_call
        self._current_health = MarginHealth.HEALTHY
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"MarginMonitor-{account.account_id[:8]}"
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            start = time.perf_counter_ns()
            try:
                snap = self._account.snapshot()
                new_health = snap.health

                if new_health != self._current_health:
                    transition = HealthTransition(
                        from_health=self._current_health,
                        to_health=new_health,
                        margin_ratio=snap.margin_ratio,
                        equity=snap.equity,
                        timestamp_ns=time.time_ns(),
                    )
                    self._event_queue.put_nowait(transition)
                    if new_health in (MarginHealth.MARGIN_CALL, MarginHealth.LIQUIDATING):
                        if self._on_margin_call:
                            self._on_margin_call(transition)
                    self._current_health = new_health

            except Exception:
                pass  # never crash the monitor thread

            elapsed_s = (time.perf_counter_ns() - start) / 1e9
            sleep_s = max(0.0, self._interval_s - elapsed_s)
            time.sleep(sleep_s)
