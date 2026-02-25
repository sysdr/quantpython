"""
Centralised configuration and environment bootstrap.
All constants live here — no magic numbers in business logic.
"""
from __future__ import annotations

import os
import logging
import logging.handlers
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

def build_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Rotating file handler — never fills the disk
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / f"{name}.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.WARNING)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

# ── Market constants ──────────────────────────────────────────────────────
TRADING_DAYS_PER_YEAR: int = 252

# Tenor name → trading days
TENORS: dict[str, int] = {
    "1W":   5,
    "1M":  21,
    "3M":  63,
    "6M": 126,
    "1Y": 252,
    "2Y": 504,
    "3Y": 756,
    "5Y": 1260,
}

TENOR_ORDER: list[str] = list(TENORS.keys())

# ── Alpaca config ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AlpacaConfig:
    api_key: str = field(default_factory=lambda: os.environ.get("ALPACA_API_KEY", ""))
    secret_key: str = field(default_factory=lambda: os.environ.get("ALPACA_SECRET_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.environ.get(
            "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
        )
    )

    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

ALPACA_CFG = AlpacaConfig()
