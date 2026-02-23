"""
AutoQuant-Alpha | src/health_check.py
Verifies Alpaca Paper Trading sandbox connectivity.

Exit codes:
    0 — Healthy
    1 — Unhealthy (auth failed, equity <= 0, unexpected error)

Usage:
    python src/health_check.py
"""
from __future__ import annotations

import sys
import time

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest

from src.config import AlpacaConfig
from src.logger import get_logger

log = get_logger(__name__)


def check_alpaca_health(config: AlpacaConfig) -> bool:
    """
    Authenticate to Alpaca Paper Trading and verify account is funded.
    Returns True if healthy, False otherwise.
    Logs structured JSON with latency_ms on every call.
    """
    t_start = time.monotonic()
    try:
        client = TradingClient(
            api_key=config.api_key,
            secret_key=config.secret_key,
            paper=True,
        )
        account = client.get_account()
        latency_ms = round((time.monotonic() - t_start) * 1000, 2)

        equity = float(account.equity)  # type: ignore[arg-type]
        if equity <= 0:
            log.error(
                f"Alpaca account equity is zero or negative | equity={equity}"
            )
            return False

        log.info(
            f"Alpaca sandbox healthy | equity={equity:.2f}"
            f" | latency_ms={latency_ms}"
            f" | account_id={account.id}"
            f" | status={account.status}"
        )
        return True

    except Exception as exc:
        latency_ms = round((time.monotonic() - t_start) * 1000, 2)
        log.error(
            f"Alpaca health check failed | error={exc!r}"
            f" | latency_ms={latency_ms}"
        )
        return False


def main() -> None:
    try:
        config = AlpacaConfig.from_env()
    except EnvironmentError as exc:
        log.error(f"Configuration error | error={exc}")
        sys.exit(1)

    healthy = check_alpaca_health(config)
    sys.exit(0 if healthy else 1)


if __name__ == "__main__":
    main()
