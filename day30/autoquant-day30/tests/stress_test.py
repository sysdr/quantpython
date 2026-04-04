"""
Stress Test: 1,000 synthetic OrderRecords
------------------------------------------
Tests AtomicTradeLogger under concurrent write load (10 threads × 100 records).
Verifies: no row corruption, correct record count, CSV integrity.

Run: python tests/stress_test.py
"""

from __future__ import annotations

import csv
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.execution.market_order import OrderRecord
from src.utils.logger import AtomicTradeLogger


def _generate_record(thread_id: int, seq: int) -> OrderRecord:
    slip = Decimal(str(round(thread_id * 0.1 + seq * 0.01, 2)))
    return OrderRecord(
        symbol=f"SYM{thread_id:02d}",
        side="buy" if seq % 2 == 0 else "sell",
        qty=10 + seq,
        expected_price=Decimal("100.00"),
        submitted_at=datetime.now(tz=timezone.utc),
        order_id=f"thread-{thread_id:02d}-seq-{seq:04d}",
        fill_price=Decimal("100.00") + slip / Decimal("100"),
        filled_at=datetime.now(tz=timezone.utc),
        slippage_bps=slip,
        status="FILLED",
    )


def _writer_thread(logger: AtomicTradeLogger, thread_id: int, n: int) -> None:
    for i in range(n):
        logger.log(_generate_record(thread_id, i))


def run_stress_test(n_threads: int = 10, records_per_thread: int = 100) -> None:
    total = n_threads * records_per_thread
    print(f"Stress test: {n_threads} threads × {records_per_thread} records = {total} writes")

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        log_path = Path(tmp.name)

    logger = AtomicTradeLogger(log_path)

    threads = [
        threading.Thread(target=_writer_thread, args=(logger, t, records_per_thread))
        for t in range(n_threads)
    ]

    t0 = time.perf_counter()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    elapsed = time.perf_counter() - t0

    # Verify
    with log_path.open() as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == total, f"Expected {total} rows, got {len(rows)}"

    # Check no corrupted rows (order_id should match expected pattern)
    for row in rows:
        oid = row["order_id"]
        assert oid.startswith("thread-"), f"Corrupted order_id: {oid!r}"

    print(f"  ✓ {total} rows written in {elapsed:.3f}s ({total / elapsed:.0f} rows/s)")
    print(f"  ✓ No row corruption detected")
    log_path.unlink(missing_ok=True)


if __name__ == "__main__":
    run_stress_test()
