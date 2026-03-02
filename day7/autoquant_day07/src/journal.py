"""
src/journal.py
AutoQuant-Alpha Day 7 — Non-blocking trade journal using QueueHandler.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import queue
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

QUEUE_MAXSIZE: Final[int] = 10_000
DEDUP_WINDOW_SECONDS: Final[float] = 1.0
DEDUP_CACHE_SIZE: Final[int] = 1_000


# ── Structured record ────────────────────────────────────────────────────

@dataclass(slots=True, frozen=True)
class FillRecord:
    order_id: str
    symbol: str
    side: str          # "buy" | "sell"
    qty: float
    limit_price: float
    fill_price: float
    submission_ts: float = field(repr=False)  # perf_counter at submission

    @property
    def slippage_bps(self) -> float:
        raw = (self.fill_price - self.limit_price) / self.limit_price * 10_000
        return round(raw if self.side == "buy" else -raw, 4)

    @property
    def latency_ms(self) -> float:
        return round((time.perf_counter() - self.submission_ts) * 1_000, 3)


# ── Formatters ───────────────────────────────────────────────────────────

class JsonTradeFormatter(logging.Formatter):
    """
    Emits JSON Lines for trade records.
    Includes LRU deduplication keyed on order_id within DEDUP_WINDOW_SECONDS.
    format() runs in the *calling* thread — no extra locks needed.
    """

    TRADE_FIELDS: Final[frozenset[str]] = frozenset({
        "order_id", "symbol", "side", "qty",
        "fill_price", "limit_price", "slippage_bps", "latency_ms",
    })

    def __init__(self) -> None:
        super().__init__()
        # OrderedDict as bounded LRU: key=order_id, value=first_seen_wall_time
        self._seen: OrderedDict[str, float] = OrderedDict()

    def _is_duplicate(self, order_id: str) -> bool:
        now = time.monotonic()
        if order_id in self._seen:
            if now - self._seen[order_id] < DEDUP_WINDOW_SECONDS:
                return True
            # Expired entry — remove so we can re-register
            del self._seen[order_id]

        # Register; evict oldest if at capacity
        if len(self._seen) >= DEDUP_CACHE_SIZE:
            self._seen.popitem(last=False)
        self._seen[order_id] = now
        return False

    def format(self, record: logging.LogRecord) -> str | None:  # type: ignore[override]
        order_id: str | None = getattr(record, "order_id", None)
        if order_id is not None and self._is_duplicate(order_id):
            return None  # Signal to handler: skip emit

        import datetime
        payload: dict = {
            "ts": datetime.datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for f in self.TRADE_FIELDS:
            if (val := getattr(record, f, None)) is not None:
                payload[f] = val
        return json.dumps(payload, separators=(",", ":"))


class DeduplicatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """
    Wraps TimedRotatingFileHandler to honour formatter returning None
    (deduplication signal) and skip the emit.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if msg is None:
                return  # deduplicated
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


# ── Subsystem factory ────────────────────────────────────────────────────

class LoggingSubsystem:
    """
    Manages the QueueHandler + QueueListener pair.
    Call .start() before use, .stop() on shutdown.
    """

    def __init__(self, log_dir: Path) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir = log_dir
        self.queue: queue.Queue[logging.LogRecord] = queue.Queue(maxsize=QUEUE_MAXSIZE)
        self._listener: logging.handlers.QueueListener | None = None

    def start(self) -> tuple[logging.Logger, logging.Logger]:
        # Trade journal: daily rotation, 30-day retention
        journal_handler = DeduplicatingFileHandler(
            self.log_dir / "trade_journal.jsonl",
            when="midnight", utc=True, backupCount=30,
        )
        journal_handler.setFormatter(JsonTradeFormatter())
        journal_handler.setLevel(logging.INFO)

        # System log: size-based rotation
        system_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / "system.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        system_handler.setFormatter(logging.Formatter(
            "%(asctime)s.%(msecs)03d [%(threadName)s] %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        ))
        system_handler.setLevel(logging.DEBUG)

        self._listener = logging.handlers.QueueListener(
            self.queue,
            journal_handler,
            system_handler,
            respect_handler_level=True,
        )
        self._listener.start()

        queue_handler = logging.handlers.QueueHandler(self.queue)

        trade_log = logging.getLogger("autoquant.trade")
        trade_log.setLevel(logging.INFO)
        trade_log.handlers.clear()
        trade_log.addHandler(queue_handler)
        trade_log.propagate = False

        sys_log = logging.getLogger("autoquant.system")
        sys_log.setLevel(logging.DEBUG)
        sys_log.handlers.clear()
        sys_log.addHandler(queue_handler)
        sys_log.propagate = False

        return trade_log, sys_log

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()

    @property
    def queue_depth(self) -> int:
        return self.queue.qsize()


# ── Helper: log a FillRecord ──────────────────────────────────────────────

def log_fill(logger: logging.Logger, fill: FillRecord) -> None:
    logger.info(
        "ORDER_FILL",
        extra={
            "order_id": fill.order_id,
            "symbol": fill.symbol,
            "side": fill.side,
            "qty": fill.qty,
            "fill_price": fill.fill_price,
            "limit_price": fill.limit_price,
            "slippage_bps": fill.slippage_bps,
            "latency_ms": fill.latency_ms,
        },
    )
