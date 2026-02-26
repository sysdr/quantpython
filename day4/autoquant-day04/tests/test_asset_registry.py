"""Unit tests for AssetRegistry MutableMapping."""
import json
import time
import pytest
from pathlib import Path
from src.asset_registry import AssetRegistry, _normalize_symbol
from src.asset_metadata import AssetMetadata


def _mock_meta(sym="AAPL", ttl=3600.0, age=0.0) -> AssetMetadata:
    return AssetMetadata(
        symbol=sym, exchange="NASDAQ", asset_class="us_equity",
        tradable=True, fractionable=True, min_order_size=1.0,
        price_increment=0.01, fetched_at=time.monotonic() - age,
        ttl_seconds=ttl,
    )


# ── Normalization ────────────────────────────────────────────────────────────

def test_normalize_uppercase():
    assert _normalize_symbol("aapl") == "AAPL"

def test_normalize_dot_to_slash():
    assert _normalize_symbol("BRK.B") == "BRK/B"

def test_normalize_strip_whitespace():
    assert _normalize_symbol("  TSLA  ") == "TSLA"


# ── Cache Behavior ───────────────────────────────────────────────────────────

def test_getitem_returns_valid_cached():
    reg = AssetRegistry()
    reg._store["AAPL"] = _mock_meta("AAPL")
    result = reg["AAPL"]
    assert result.symbol == "AAPL"
    assert reg._hit_count == 1
    assert reg._miss_count == 0


def test_expired_entry_triggers_miss():
    reg = AssetRegistry()
    reg._store["TSLA"] = _mock_meta("TSLA", ttl=3600.0, age=4000.0)
    # Without a client, __missing__ will raise. Check miss is counted.
    with pytest.raises(RuntimeError, match="No Alpaca client"):
        reg["TSLA"]
    assert reg._miss_count == 1


def test_contains_excludes_expired():
    reg = AssetRegistry()
    reg._store["EXPIRED"] = _mock_meta("EXPIRED", ttl=10.0, age=100.0)
    assert "EXPIRED" not in reg


def test_len_excludes_expired():
    reg = AssetRegistry()
    reg._store["VALID"] = _mock_meta("VALID", age=0.0)
    reg._store["DEAD"] = _mock_meta("DEAD", ttl=10.0, age=100.0)
    assert len(reg) == 1


def test_invalidate_removes_entry():
    reg = AssetRegistry()
    reg._store["SPY"] = _mock_meta("SPY")
    reg.invalidate("SPY")
    assert "SPY" not in reg._store


def test_case_insensitive_lookup():
    reg = AssetRegistry()
    reg._store["AAPL"] = _mock_meta("AAPL")
    result = reg["aapl"]
    assert result.symbol == "AAPL"


# ── Persistence ──────────────────────────────────────────────────────────────

def test_persist_and_reload(tmp_path):
    path = tmp_path / "registry.json"
    reg = AssetRegistry()
    reg._store["NVDA"] = _mock_meta("NVDA")
    reg._store["META"] = _mock_meta("META")
    reg.persist(path)

    reg2 = AssetRegistry()
    count = reg2.load_from_disk(path)
    assert count == 2
    assert reg2._store["NVDA"].symbol == "NVDA"
    assert reg2._store["META"].is_valid


def test_persist_excludes_expired(tmp_path):
    path = tmp_path / "registry.json"
    reg = AssetRegistry()
    reg._store["ALIVE"] = _mock_meta("ALIVE", age=0.0)
    reg._store["DEAD"] = _mock_meta("DEAD", ttl=10.0, age=100.0)
    reg.persist(path)
    saved = json.loads(path.read_text())
    assert "ALIVE" in saved
    assert "DEAD" not in saved


# ── Hit Rate ─────────────────────────────────────────────────────────────────

def test_hit_rate_calculation():
    reg = AssetRegistry()
    reg._store["QQQ"] = _mock_meta("QQQ")
    for _ in range(9):
        reg["QQQ"]
    reg._miss_count = 1  # simulate one initial miss
    assert reg.hit_rate == pytest.approx(9 / 10)
