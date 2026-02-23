"""
Tests for src/health_check.py — Alpaca connectivity verification.
Uses monkeypatching to avoid live API calls in CI.
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from src.config import AlpacaConfig
from src.health_check import check_alpaca_health


@dataclass
class _FakeAccount:
    equity: str = "100000.00"
    cash: str = "100000.00"
    id: str = "acct-fake-uuid-1234"
    status: str = "ACTIVE"


def _fake_config() -> AlpacaConfig:
    return AlpacaConfig(
        api_key="FAKE_KEY",
        secret_key="FAKE_SECRET",
        base_url="https://paper-api.alpaca.markets",
    )


class TestCheckAlpacaHealth:
    def test_returns_true_on_success(self) -> None:
        fake_acct = _FakeAccount()
        mock_client = MagicMock()
        mock_client.get_account.return_value = fake_acct

        with patch("src.health_check.TradingClient", return_value=mock_client):
            result = check_alpaca_health(_fake_config())

        assert result is True

    def test_returns_false_on_zero_equity(self) -> None:
        fake_acct = _FakeAccount(equity="0.00")
        mock_client = MagicMock()
        mock_client.get_account.return_value = fake_acct

        with patch("src.health_check.TradingClient", return_value=mock_client):
            result = check_alpaca_health(_fake_config())

        assert result is False

    def test_returns_false_on_exception(self) -> None:
        mock_client = MagicMock()
        mock_client.get_account.side_effect = ConnectionError("timeout")

        with patch("src.health_check.TradingClient", return_value=mock_client):
            result = check_alpaca_health(_fake_config())

        assert result is False

    def test_negative_equity_returns_false(self) -> None:
        fake_acct = _FakeAccount(equity="-500.00")
        mock_client = MagicMock()
        mock_client.get_account.return_value = fake_acct

        with patch("src.health_check.TradingClient", return_value=mock_client):
            result = check_alpaca_health(_fake_config())

        assert result is False
