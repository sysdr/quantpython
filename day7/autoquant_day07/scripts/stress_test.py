#!/usr/bin/env python3
"""
Stress test: hammer the QueueHandler with 50,000 records across 8 threads.
Measures throughput and queue depth under load.
"""
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.journal import FillRecord, LoggingSubsystem, log_fill

LOG_DIR = Path("logs/stress")
RECORDS_PER_THREAD = 6_250
NUM_THREADS = 8
TOTAL = RECORDS_PER_THREAD * NUM_THREADS


def worker(trade_log, thread_id: int) -> None:
    for i in range(RECORDS_PER_THREAD):
        fill = FillRecord(
            order_id=str(uuid4()),
            symbol="SPY",
            side="buy" if i % 2 == 0 else "sell",
            qty=float(i % 100 + 1),
            limit_price=500.00,
            fill_price=500.00 + (i % 10) * 0.01,
            submission_ts=time.perf_counter(),
        )
        log_fill(trade_log, fill)


def main() -> None:
    print(f"Stress test: {TOTAL:,} records across {NUM_THREADS} threads")
    subsystem = LoggingSubsystem(LOG_DIR)
    trade_log, _ = subsystem.start()

    start = time.perf_counter()
    threads = [
        threading.Thread(target=worker, args=(trade_log, t), name=f"Worker-{t}")
        for t in range(NUM_THREADS)
    ]
    for t in threads:
        t.start()

    # Monitor queue depth while threads run
    peak_depth = 0
    while any(t.is_alive() for t in threads):
        d = subsystem.queue_depth
        if d > peak_depth:
            peak_depth = d
        time.sleep(0.05)

    for t in threads:
        t.join()

    # Drain
    time.sleep(1.0)
    subsystem.stop()
    elapsed = time.perf_counter() - start

    print(f"  Total records : {TOTAL:,}")
    print(f"  Elapsed       : {elapsed:.2f}s")
    print(f"  Throughput    : {TOTAL / elapsed:,.0f} records/sec")
    print(f"  Peak queue    : {peak_depth} / {subsystem.queue.maxsize}")

    journal = LOG_DIR / "trade_journal.jsonl"
    if journal.exists():
        lines = len([l for l in journal.read_text().splitlines() if l.strip()])
        print(f"  Journal lines : {lines:,}")


if __name__ == "__main__":
    main()
