#!/usr/bin/env python3
"""
start.py — Fetch Alpaca bars, validate, compute returns, print summary.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent / "src"))

from alpaca_loader import build_common_date_index, load_bars
from data_validator import DataValidator
from return_engine import ReturnEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("start")


def main() -> None:
    logger.info("── AutoQuant-Alpha · Day 10 ─────────────────────────────")

    # 1. Load raw bars
    raw_ohlcv = load_bars(lookback_days=252)
    logger.info("Loaded %d symbols", len(raw_ohlcv))

    # 2. Validate
    validator = DataValidator()
    clean_ohlcv, results = validator.validate_universe(raw_ohlcv)

    failed = [s for s, r in results.items() if not r.passed]
    if failed:
        logger.warning("Dropped symbols: %s", failed)

    # 3. Build shared date index
    date_index = build_common_date_index(clean_ohlcv)
    logger.info("Date index: %s → %s (%d days)",
                date_index[0].date(), date_index[-1].date(), len(date_index))

    # 4. Compute returns
    engine = ReturnEngine()
    tensor = engine.compute(clean_ohlcv, date_index)

    # 5. Report
    logger.info("Return tensor shape: %s", tensor.log_returns.shape)
    logger.info("Coverage: %.2f%%", tensor.coverage() * 100)
    logger.info("CA flags: %d", len(tensor.ca_flags))

    # 6. Show last 5 days as DataFrame preview
    df = ReturnEngine.to_dataframe(tensor, use_log=False)
    print("\n── Last 5 trading days (arithmetic returns) ─────────────")
    print((df.tail(5) * 100).round(4).to_string(float_format=lambda x: f"{x:+.4f}%"))
    print()

    logger.info("Done. Run `python demo.py` for the full dashboard.")


if __name__ == "__main__":
    main()
