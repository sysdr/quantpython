"""
Tests for src/config.py — environment variable loading.
"""
from __future__ import annotations

import os

import pytest

from src.config import AlpacaConfig, _require_env


class TestRequireEnv:
    def test_raises_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TEST_NONEXISTENT_VAR", raising=False)
        with pytest.raises(EnvironmentError, match="TEST_NONEXISTENT_VAR"):
            _require_env("TEST_NONEXISTENT_VAR")

    def test_returns_value_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_VAR", "hello")
        assert _require_env("TEST_VAR") == "hello"

    def test_raises_on_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_EMPTY", "")
        with pytest.raises(EnvironmentError):
            _require_env("TEST_EMPTY")


class TestAlpacaConfig:
    def test_from_env_loads_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALPACA_API_KEY", "test_key_id")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test_secret")
        monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

        cfg = AlpacaConfig.from_env()
        assert cfg.api_key == "test_key_id"
        assert cfg.secret_key == "test_secret"
        assert "paper-api" in cfg.base_url

    def test_raises_when_key_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        with pytest.raises(EnvironmentError):
            AlpacaConfig.from_env()

    def test_config_is_immutable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALPACA_API_KEY", "k")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
        cfg = AlpacaConfig.from_env()
        with pytest.raises((AttributeError, TypeError)):
            cfg.api_key = "mutated"  # type: ignore[misc]
