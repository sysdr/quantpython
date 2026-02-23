"""
AutoQuant-Alpha | src/config.py
Centralized configuration loaded from environment variables.
Fails loudly at import time if required variables are missing.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()  # loads .env file if present; silently skips if absent


def _require_env(key: str) -> str:
    """Fetch a required environment variable or raise immediately."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example to .env and populate it."
        )
    return value


@dataclass(frozen=True)
class AlpacaConfig:
    api_key: str
    secret_key: str
    base_url: str

    @classmethod
    def from_env(cls) -> "AlpacaConfig":
        return cls(
            api_key=_require_env("ALPACA_API_KEY"),
            secret_key=_require_env("ALPACA_SECRET_KEY"),
            base_url=os.getenv(
                "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
            ),
        )


@dataclass(frozen=True)
class AppConfig:
    alpaca: AlpacaConfig = field(default_factory=AlpacaConfig.from_env)
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )
