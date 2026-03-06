"""
data_validator.py
─────────────────
Pre-flight validation of raw OHLCV DataFrames before ingestion
into the ReturnEngine.  Uses Python 3.11 structural pattern matching
for clean, exhaustive failure-mode classification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FailureCode(Enum):
    EMPTY_FRAME = auto()
    MISSING_CLOSE_COLUMN = auto()
    NEGATIVE_PRICES = auto()
    ZERO_PRICES = auto()
    DUPLICATE_DATES = auto()
    UNSORTED_INDEX = auto()
    ALL_NAN = auto()


@dataclass(slots=True, frozen=True)
class ValidationResult:
    symbol: str
    passed: bool
    failures: tuple[FailureCode, ...]
    rows_before: int
    rows_after: int

    @property
    def drop_rate(self) -> float:
        if self.rows_before == 0:
            return 0.0
        return 1.0 - self.rows_after / self.rows_before


class DataValidator:
    """Validates and normalises raw OHLCV DataFrames."""

    MAX_ACCEPTABLE_DROP_RATE: float = 0.05   # 5% missing rows is a warning

    def validate(
        self, symbol: str, df: pd.DataFrame
    ) -> tuple[pd.DataFrame | None, ValidationResult]:
        failures: list[FailureCode] = []
        rows_before = len(df)

        # ── structural checks ────────────────────────────────────────────
        if df.empty:
            failures.append(FailureCode.EMPTY_FRAME)

        if "close" not in df.columns:
            failures.append(FailureCode.MISSING_CLOSE_COLUMN)

        if failures:
            return None, ValidationResult(
                symbol=symbol,
                passed=False,
                failures=tuple(failures),
                rows_before=rows_before,
                rows_after=0,
            )

        # ── data-quality checks ──────────────────────────────────────────
        df = df.copy()
        df.index = pd.to_datetime(df.index)

        if df.index.duplicated().any():
            failures.append(FailureCode.DUPLICATE_DATES)
            df = df[~df.index.duplicated(keep="last")]

        if not df.index.is_monotonic_increasing:
            failures.append(FailureCode.UNSORTED_INDEX)
            df = df.sort_index()

        close = df["close"].to_numpy(dtype=np.float64)

        if np.all(~np.isfinite(close)):
            failures.append(FailureCode.ALL_NAN)
            return None, ValidationResult(
                symbol=symbol,
                passed=False,
                failures=tuple(failures),
                rows_before=rows_before,
                rows_after=0,
            )

        if np.any(close[np.isfinite(close)] < 0):
            failures.append(FailureCode.NEGATIVE_PRICES)

        if np.any(close[np.isfinite(close)] == 0):
            failures.append(FailureCode.ZERO_PRICES)

        rows_after = len(df)
        passed = len(failures) == 0

        result = ValidationResult(
            symbol=symbol,
            passed=passed,
            failures=tuple(failures),
            rows_before=rows_before,
            rows_after=rows_after,
        )

        # Python 3.11 structural pattern matching for failure reporting
        for code in failures:
            match code:
                case FailureCode.NEGATIVE_PRICES:
                    logger.error("[%s] Negative close prices detected — check feed", symbol)
                case FailureCode.ZERO_PRICES:
                    logger.warning("[%s] Zero close prices — possible halted symbol", symbol)
                case FailureCode.DUPLICATE_DATES:
                    logger.warning("[%s] Duplicate dates removed (kept last)", symbol)
                case FailureCode.UNSORTED_INDEX:
                    logger.warning("[%s] Index was unsorted — sorted ascending", symbol)
                case _:
                    logger.error("[%s] Validation failure: %s", symbol, code.name)

        if result.drop_rate > self.MAX_ACCEPTABLE_DROP_RATE:
            logger.warning(
                "[%s] High drop rate: %.1f%% of rows removed during cleaning",
                symbol,
                result.drop_rate * 100,
            )

        return df if passed else None, result

    def validate_universe(
        self, ohlcv: dict[str, pd.DataFrame]
    ) -> tuple[dict[str, pd.DataFrame], dict[str, ValidationResult]]:
        """Validate an entire symbol universe; drop failed symbols."""
        clean: dict[str, pd.DataFrame] = {}
        results: dict[str, ValidationResult] = {}

        for sym, df in ohlcv.items():
            clean_df, result = self.validate(sym, df)
            results[sym] = result
            if clean_df is not None:
                clean[sym] = clean_df
            else:
                logger.error("Dropping %s from universe: validation failed", sym)

        passed = sum(1 for r in results.values() if r.passed)
        logger.info(
            "Validation complete: %d/%d symbols passed", passed, len(results)
        )
        return clean, results
