"""Unit tests for AssetMetadata dataclass."""
import time
import pytest
from src.asset_metadata import AssetMetadata


def _meta(ttl=3600.0, age=0.0) -> AssetMetadata:
    return AssetMetadata(
        symbol="AAPL", exchange="NASDAQ", asset_class="us_equity",
        tradable=True, fractionable=True, min_order_size=1.0,
        price_increment=0.01, fetched_at=time.monotonic() - age,
        ttl_seconds=ttl,
    )


def test_is_valid_fresh():
    assert _meta(ttl=3600.0, age=0.0).is_valid is True


def test_is_valid_expired():
    assert _meta(ttl=3600.0, age=4000.0).is_valid is False


def test_age_seconds_approx():
    meta = _meta(age=100.0)
    assert 99.0 < meta.age_seconds < 101.0


def test_to_dict_roundtrip():
    original = _meta()
    restored = AssetMetadata.from_dict(original.to_dict())
    assert restored.symbol == original.symbol
    assert restored.exchange == original.exchange
    assert restored.min_order_size == original.min_order_size
    assert restored.is_valid  # from_dict resets fetched_at to now


def test_frozen_immutability():
    meta = _meta()
    with pytest.raises(Exception):  # FrozenInstanceError
        meta.symbol = "TSLA"  # type: ignore


def test_min_order_size_is_float():
    meta = AssetMetadata(
        symbol="X", exchange="NYSE", asset_class="us_equity",
        tradable=True, fractionable=False,
        min_order_size=float("1"),  # explicitly cast
        price_increment=0.01, fetched_at=time.monotonic(),
    )
    assert isinstance(meta.min_order_size, float)
    # Verify arithmetic works (would fail if string)
    result = meta.min_order_size * 150.0
    assert result == 150.0
