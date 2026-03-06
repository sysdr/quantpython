"""
return_engine.py
────────────────
Vectorised daily log-return computation for a universe of N symbols.

Design invariants
-----------------
1. All compute is on NumPy 2-D arrays [N_symbols × T_days]. Zero loops.
2. Log-returns are the internal canonical form.
3. NaN propagation is explicit; silent fills are forbidden.
4. Corporate-action spikes are flagged BEFORE corrupting downstream signals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Any single-day arithmetic return beyond ±40% is treated as a
# suspected corporate action (split / reverse-split).
SPLIT_THRESHOLD: float = 0.40

# ────────────────────────────────────────────────────────────────────────
# Data containers
# ────────────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class ReturnTensor:
    """Output of ReturnEngine.compute().

    Attributes
    ----------
    log_returns:    np.ndarray  [N × T-1]  — NaN where invalid
    validity_mask:  np.ndarray  [N × T-1]  — True where usable
    symbols:        list[str]
    dates:          pd.DatetimeIndex        — length T-1 (return dates)
    ca_flags:       list[CorporateActionFlag]
    """

    log_returns: np.ndarray
    validity_mask: np.ndarray
    symbols: list[str]
    dates: pd.DatetimeIndex
    ca_flags: list["CorporateActionFlag"] = field(default_factory=list)

    @property
    def arithmetic_returns(self) -> np.ndarray:
        """Convert log → arithmetic at the output boundary only."""
        return np.expm1(self.log_returns)

    def coverage(self) -> float:
        """Fraction of (symbol, date) cells with valid returns."""
        total = self.validity_mask.size
        return float(self.validity_mask.sum() / total) if total else 0.0

    def nan_rate_per_symbol(self) -> dict[str, float]:
        invalid_counts = (~self.validity_mask).sum(axis=1)
        total = self.validity_mask.shape[1]
        return {
            sym: float(invalid_counts[i] / total)
            for i, sym in enumerate(self.symbols)
        }


@dataclass(slots=True, frozen=True)
class CorporateActionFlag:
    symbol: str
    date: str
    return_pct: float

    def __str__(self) -> str:
        return (
            f"[CA-FLAG] {self.symbol} on {self.date}: "
            f"{self.return_pct:+.2f}% (threshold ±{SPLIT_THRESHOLD*100:.0f}%)"
        )


# ────────────────────────────────────────────────────────────────────────
# Core engine
# ────────────────────────────────────────────────────────────────────────

class ReturnEngine:
    """Vectorised return computation over a multi-symbol price matrix."""

    def __init__(self, split_threshold: float = SPLIT_THRESHOLD) -> None:
        self._split_threshold = split_threshold

    # ── public API ───────────────────────────────────────────────────────

    def compute(
        self,
        ohlcv: dict[str, pd.DataFrame],
        date_index: pd.DatetimeIndex,
    ) -> ReturnTensor:
        """
        Parameters
        ----------
        ohlcv       : symbol → DataFrame with a 'close' column,
                      indexed by date (any frequency).
        date_index  : calendar-aligned DatetimeIndex (length T).

        Returns
        -------
        ReturnTensor with log_returns of shape [N × T-1].
        """
        symbols = sorted(ohlcv.keys())
        price_matrix, nan_mask = self._build_price_matrix(
            ohlcv, symbols, date_index
        )
        log_returns, validity_mask = self._compute_log_returns(
            price_matrix, nan_mask
        )
        ca_flags = self._detect_corporate_actions(
            log_returns, validity_mask, symbols, date_index
        )

        if ca_flags:
            for flag in ca_flags:
                logger.warning(str(flag))

        return ReturnTensor(
            log_returns=log_returns,
            validity_mask=validity_mask,
            symbols=symbols,
            dates=date_index[1:],   # returns align to t=1..T
            ca_flags=ca_flags,
        )

    # ── private helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_price_matrix(
        ohlcv: dict[str, pd.DataFrame],
        symbols: list[str],
        date_index: pd.DatetimeIndex,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Assemble close prices into a [N × T] float64 matrix.
        Missing dates produce NaN (explicit, auditable).
        """
        N, T = len(symbols), len(date_index)
        matrix = np.full((N, T), np.nan, dtype=np.float64)

        for i, sym in enumerate(symbols):
            df = ohlcv[sym]
            # reindex to the shared calendar; gaps → NaN
            aligned = df["close"].reindex(date_index)
            matrix[i, :] = aligned.to_numpy(dtype=np.float64, na_value=np.nan)

        nan_mask = ~np.isfinite(matrix)   # catches NaN AND ±inf
        return matrix, nan_mask

    @staticmethod
    def _compute_log_returns(
        price_matrix: np.ndarray,
        nan_mask: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Vectorised log-return computation.

        log_return[i, t] = log(close[i, t]) - log(close[i, t-1])

        NaN is written wherever either price endpoint is invalid.
        errstate suppresses the RuntimeWarning from log(0); we handle
        the resulting -inf explicitly via the validity mask.
        """
        with np.errstate(divide="ignore", invalid="ignore"):
            log_prices = np.log(price_matrix)           # [N × T]

        log_returns = np.diff(log_prices, axis=1)       # [N × T-1]

        # Propagate invalidity: bad price at t OR t-1 → bad return at t
        invalid = nan_mask[:, :-1] | nan_mask[:, 1:]
        log_returns[invalid] = np.nan

        validity_mask = ~invalid
        return log_returns, validity_mask

    def _detect_corporate_actions(
        self,
        log_returns: np.ndarray,
        validity_mask: np.ndarray,
        symbols: list[str],
        date_index: pd.DatetimeIndex,
    ) -> list[CorporateActionFlag]:
        """
        Flag returns exceeding ±split_threshold as suspected CAs.
        Uses arithmetic conversion only for the threshold comparison —
        log-returns remain the canonical internal representation.
        """
        arith = np.expm1(log_returns)
        suspect = (np.abs(arith) > self._split_threshold) & validity_mask

        flags: list[CorporateActionFlag] = []
        rows, cols = np.where(suspect)
        for r, c in zip(rows, cols, strict=True):
            flags.append(
                CorporateActionFlag(
                    symbol=symbols[r],
                    date=date_index[c + 1].isoformat(),  # diff shifts by 1
                    return_pct=float(arith[r, c] * 100),
                )
            )
        return flags

    # ── convenience utilities ────────────────────────────────────────────

    @staticmethod
    def to_dataframe(tensor: ReturnTensor, use_log: bool = True) -> pd.DataFrame:
        """
        Convert ReturnTensor to a Pandas DataFrame (symbols as columns).
        Invalid cells are NaN — not zero-filled.
        """
        data = tensor.log_returns if use_log else tensor.arithmetic_returns
        df = pd.DataFrame(
            data.T,
            index=tensor.dates,
            columns=tensor.symbols,
        )
        # Mask out invalids (already NaN in array, belt-and-suspenders)
        mask_df = pd.DataFrame(
            ~tensor.validity_mask.T,
            index=tensor.dates,
            columns=tensor.symbols,
        )
        df[mask_df] = np.nan
        return df
