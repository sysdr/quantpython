"""
AssetRegistry — lazy-loading, TTL-invalidated, on-disk-persisted MutableMapping.

Design contract:
  - Callers access registry["AAPL"] and get a valid AssetMetadata.
  - Cache misses trigger a single Alpaca REST call with exponential backoff.
  - On shutdown, call registry.persist() to save to disk.
  - On startup, call registry.load_from_disk() for sub-second cold start.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Generator

from src.asset_metadata import AssetMetadata

logger = logging.getLogger(__name__)

# ── Backoff Generator ────────────────────────────────────────────────────────

def _exponential_delays(
    base: float = 0.5, factor: float = 2.0, cap: float = 30.0
) -> Generator[float, None, None]:
    """Yields exponentially increasing delays, capped at `cap` seconds."""
    delay = base
    while True:
        yield min(delay, cap)
        delay *= factor


# ── Canonical Key ─────────────────────────────────────────────────────────────

def _normalize_symbol(raw: str) -> str:
    """
    Normalize ticker symbol to Alpaca canonical form.
    BRK.B -> BRK/B, lowercase -> uppercase, strip whitespace.
    """
    return raw.strip().upper().replace(".", "/")


# ── Registry ──────────────────────────────────────────────────────────────────

class AssetRegistry(MutableMapping):
    """
    Thread-unsafe (by design — single-threaded event loop assumed) asset cache.
    Key: normalized symbol string (str)
    Value: AssetMetadata

    Use prefetch() at strategy startup to warm the cache in a single API batch call.
    """

    _PERSIST_PATH = Path("data/asset_registry.json")

    def __init__(
        self,
        ttl_seconds: float = 3600.0,
        max_retries: int = 3,
        alpaca_client=None,
    ) -> None:
        self._store: dict[str, AssetMetadata] = {}
        self._ttl = ttl_seconds
        self._max_retries = max_retries
        self._client = alpaca_client  # alpaca.trading.TradingClient
        self._miss_count = 0
        self._hit_count = 0

    # ── MutableMapping ABC ──────────────────────────────────────────────────

    def __getitem__(self, symbol: str) -> AssetMetadata:
        key = _normalize_symbol(symbol)
        entry = self._store.get(key)
        if entry is not None and entry.is_valid:
            self._hit_count += 1
            return entry
        # Cache miss or expired entry
        return self.__missing__(key)

    def __missing__(self, key: str) -> AssetMetadata:
        self._miss_count += 1
        logger.debug("Cache miss for %s — fetching from Alpaca", key)
        metadata = self._fetch_with_backoff(key)
        self._store[key] = metadata
        return metadata

    def __setitem__(self, symbol: str, metadata: AssetMetadata) -> None:
        self._store[_normalize_symbol(symbol)] = metadata

    def __delitem__(self, symbol: str) -> None:
        del self._store[_normalize_symbol(symbol)]

    def __iter__(self) -> Iterator[str]:
        return iter(self._store)

    def __len__(self) -> int:
        """Returns count of non-expired entries only."""
        return sum(1 for v in self._store.values() if v.is_valid)

    def __contains__(self, symbol: object) -> bool:
        if not isinstance(symbol, str):
            return False
        key = _normalize_symbol(symbol)
        entry = self._store.get(key)
        return entry is not None and entry.is_valid

    # ── Fetch Logic ──────────────────────────────────────────────────────────

    def _fetch_with_backoff(self, symbol: str) -> AssetMetadata:
        """Fetch asset from Alpaca with exponential backoff on rate-limit errors."""
        if self._client is None:
            raise RuntimeError(
                f"No Alpaca client configured. Cannot fetch metadata for {symbol!r}. "
                "Initialize registry with alpaca_client=TradingClient(...)"
            )
        last_exc: Exception | None = None
        for attempt, delay in enumerate(
            _exponential_delays(), start=1
        ):
            if attempt > self._max_retries:
                break
            try:
                asset = self._client.get_asset(symbol)
                return AssetMetadata.from_alpaca_asset(asset, ttl_seconds=self._ttl)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Attempt %d/%d failed for %s: %s — retrying in %.1fs",
                    attempt, self._max_retries, symbol, exc, delay,
                )
                time.sleep(delay)
        raise RuntimeError(
            f"Failed to fetch asset metadata for {symbol!r} "
            f"after {self._max_retries} attempts"
        ) from last_exc

    # ── Batch Prefetch ────────────────────────────────────────────────────────

    def prefetch(self, symbols: list[str]) -> dict[str, AssetMetadata | Exception]:
        """
        Populate cache for a list of symbols using individual fetches.
        Returns a dict of {symbol: AssetMetadata | Exception}.
        In production, replace with a single /v2/assets?symbols= batch call
        when Alpaca supports it.
        """
        results: dict[str, AssetMetadata | Exception] = {}
        for sym in symbols:
            try:
                results[sym] = self[sym]
            except Exception as exc:
                results[sym] = exc
                logger.error("prefetch failed for %s: %s", sym, exc)
        return results

    # ── Metrics ──────────────────────────────────────────────────────────────

    @property
    def hit_rate(self) -> float:
        total = self._hit_count + self._miss_count
        return self._hit_count / total if total > 0 else 0.0

    @property
    def stats(self) -> dict:
        return {
            "total_entries": len(self._store),
            "valid_entries": len(self),
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": f"{self.hit_rate:.2%}",
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def persist(self, path: Path | None = None) -> None:
        """Serialize valid entries to JSON for cold-start recovery."""
        target = path or self._PERSIST_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            sym: meta.to_dict()
            for sym, meta in self._store.items()
            if meta.is_valid
        }
        target.write_text(json.dumps(payload, indent=2))
        logger.info("Registry persisted: %d entries → %s", len(payload), target)

    def load_from_disk(self, path: Path | None = None) -> int:
        """
        Load entries from disk. Entries are marked with current fetched_at
        (so they are valid but will be refreshed within one TTL window).
        Returns number of entries loaded.
        """
        target = path or self._PERSIST_PATH
        if not target.exists():
            logger.info("No persisted registry found at %s", target)
            return 0
        raw = json.loads(target.read_text())
        for sym, d in raw.items():
            self._store[sym] = AssetMetadata.from_dict(d, ttl_seconds=self._ttl)
        logger.info("Registry cold-start: %d entries loaded from %s", len(raw), target)
        return len(raw)

    # ── Force Invalidate ──────────────────────────────────────────────────────

    def invalidate(self, symbol: str) -> None:
        """Remove a single entry. Next access triggers a fresh fetch."""
        key = _normalize_symbol(symbol)
        self._store.pop(key, None)

    def invalidate_all(self) -> None:
        """Nuke the entire cache. Use after a corporate action event."""
        self._store.clear()
        logger.warning("Full registry invalidation triggered.")
