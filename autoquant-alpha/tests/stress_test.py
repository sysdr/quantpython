"""
AutoQuant-Alpha | Stress Test: Configuration loading under concurrent access.
Not a unit test — run directly: python tests/stress_test.py
"""
from __future__ import annotations

import os
import threading
import time

from src.config import AlpacaConfig
from src.logger import get_logger

log = get_logger(__name__)

os.environ["ALPACA_API_KEY"] = "stress_test_key"
os.environ["ALPACA_SECRET_KEY"] = "stress_test_secret"


def load_config_thread(thread_id: int, results: list[bool]) -> None:
    try:
        cfg = AlpacaConfig.from_env()
        assert cfg.api_key == "stress_test_key"
        results.append(True)
    except Exception as exc:
        log.error(f"Thread {thread_id} failed | error={exc!r}")
        results.append(False)


def main() -> None:
    n_threads = 50
    results: list[bool] = []
    threads = [
        threading.Thread(
            target=load_config_thread, args=(i, results), daemon=True
        )
        for i in range(n_threads)
    ]

    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed_ms = round((time.monotonic() - t0) * 1000, 2)

    successes = sum(results)
    log.info(
        f"Stress test complete | threads={n_threads}"
        f" | successes={successes}"
        f" | failures={n_threads - successes}"
        f" | elapsed_ms={elapsed_ms}"
    )
    assert successes == n_threads, f"Only {successes}/{n_threads} threads succeeded"
    print(f"\n✓ Stress test passed: {n_threads}/{n_threads} threads | {elapsed_ms}ms")


if __name__ == "__main__":
    main()
