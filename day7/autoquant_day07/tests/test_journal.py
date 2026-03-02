"""
Unit tests for src/journal.py
Run: python -m pytest tests/ -v
"""
import json
import logging
import tempfile
import threading
import time
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.journal import (
    FillRecord,
    JsonTradeFormatter,
    LoggingSubsystem,
    log_fill,
)


# ── FillRecord math ──────────────────────────────────────────────────────

class TestFillRecord:
    def _make(self, limit: float, fill: float, side: str = "buy") -> FillRecord:
        return FillRecord(
            order_id="test-001",
            symbol="SPY",
            side=side,
            qty=10.0,
            limit_price=limit,
            fill_price=fill,
            submission_ts=time.perf_counter(),
        )

    def test_buy_adverse_slippage(self):
        fill = self._make(500.0, 502.5)
        # (502.5 - 500) / 500 * 10000 = 50 bps adverse for buy
        assert abs(fill.slippage_bps - 50.0) < 0.001

    def test_buy_favorable_slippage(self):
        fill = self._make(500.0, 499.0)
        # negative: filled below limit — favorable for buyer
        assert fill.slippage_bps < 0

    def test_sell_adverse_slippage(self):
        # Selling: adverse = fill_price < limit_price (got less)
        fill = self._make(500.0, 497.5, side="sell")
        # raw = (497.5 - 500) / 500 * 10000 = -50; negated = +50 adverse
        assert abs(fill.slippage_bps - 50.0) < 0.001

    def test_latency_positive(self):
        fill = self._make(500.0, 500.0)
        time.sleep(0.01)
        assert fill.latency_ms > 0

    def test_exact_fill_zero_slippage(self):
        fill = self._make(500.0, 500.0)
        assert fill.slippage_bps == 0.0


# ── JsonTradeFormatter deduplication ─────────────────────────────────────

class TestJsonTradeFormatter:
    def _make_record(self, order_id: str, msg: str = "ORDER_FILL") -> logging.LogRecord:
        record = logging.LogRecord(
            name="autoquant.trade",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        record.order_id = order_id
        return record

    def test_first_record_not_deduplicated(self):
        fmt = JsonTradeFormatter()
        rec = self._make_record("order-1")
        result = fmt.format(rec)
        assert result is not None
        payload = json.loads(result)
        assert payload["msg"] == "ORDER_FILL"

    def test_duplicate_within_window_returns_none(self):
        fmt = JsonTradeFormatter()
        rec1 = self._make_record("order-dup")
        rec2 = self._make_record("order-dup")
        fmt.format(rec1)  # first: registers
        assert fmt.format(rec2) is None  # second: duplicate

    def test_different_orders_not_deduplicated(self):
        fmt = JsonTradeFormatter()
        r1 = self._make_record("order-A")
        r2 = self._make_record("order-B")
        assert fmt.format(r1) is not None
        assert fmt.format(r2) is not None

    def test_no_order_id_passes_through(self):
        fmt = JsonTradeFormatter()
        record = logging.LogRecord(
            name="autoquant.system", level=logging.INFO,
            pathname="", lineno=0, msg="system boot",
            args=(), exc_info=None,
        )
        assert fmt.format(record) is not None


# ── LoggingSubsystem integration ─────────────────────────────────────────

class TestLoggingSubsystem:
    def test_fill_written_to_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            subsystem = LoggingSubsystem(log_dir)
            trade_log, _ = subsystem.start()

            fill = FillRecord(
                order_id="integ-001",
                symbol="AAPL",
                side="buy",
                qty=5.0,
                limit_price=200.0,
                fill_price=200.5,
                submission_ts=time.perf_counter(),
            )
            log_fill(trade_log, fill)

            time.sleep(0.3)  # Let listener drain
            subsystem.stop()

            journal = log_dir / "trade_journal.jsonl"
            assert journal.exists()
            lines = [l for l in journal.read_text().splitlines() if l.strip()]
            assert len(lines) >= 1
            record = json.loads(lines[-1])
            assert record["order_id"] == "integ-001"
            assert record["symbol"] == "AAPL"

    def test_thread_safety(self):
        """50 threads each log 100 records — no corruption."""
        with tempfile.TemporaryDirectory() as tmp:
            subsystem = LoggingSubsystem(Path(tmp))
            trade_log, _ = subsystem.start()

            def worker(tid: int):
                for i in range(100):
                    fill = FillRecord(
                        order_id=f"thr{tid}-{i:03d}",
                        symbol="SPY",
                        side="buy",
                        qty=1.0,
                        limit_price=500.0,
                        fill_price=500.0,
                        submission_ts=time.perf_counter(),
                    )
                    log_fill(trade_log, fill)

            threads = [threading.Thread(target=worker, args=(t,)) for t in range(50)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            time.sleep(0.5)
            subsystem.stop()

            journal = Path(tmp) / "trade_journal.jsonl"
            lines = [l for l in journal.read_text().splitlines() if l.strip()]
            fills = [json.loads(l) for l in lines if json.loads(l).get("msg") == "ORDER_FILL"]
            # 50 threads × 100 records = 5000; dedup is per order_id
            # all order_ids are unique so all should be written
            assert len(fills) == 5000
