"""
AssetMetadata — immutable, schema-validated representation of a single asset.
Uses __slots__ for memory efficiency and frozen=True for hashability.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field, asdict
import json

try:
    from alpaca.trading.models import Asset
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    Asset = None  # type: ignore


@dataclass(frozen=True, slots=True)
class AssetMetadata:
    """
    Immutable snapshot of an asset's tradability and sizing constraints.
    fetched_at uses time.monotonic() — not wall-clock — for stable TTL math.
    """
    symbol: str
    exchange: str
    asset_class: str
    tradable: bool
    fractionable: bool
    min_order_size: float
    price_increment: float
    fetched_at: float  # time.monotonic() timestamp
    ttl_seconds: float = 3600.0

    # ── Validity ────────────────────────────────────────────────────────
    @property
    def is_valid(self) -> bool:
        """True if TTL has not expired."""
        return (time.monotonic() - self.fetched_at) < self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.fetched_at

    # ── Constructors ─────────────────────────────────────────────────────
    @classmethod
    def from_alpaca_asset(cls, asset: "Asset", ttl_seconds: float = 3600.0) -> "AssetMetadata":
        """
        Parse Alpaca Asset model into validated AssetMetadata.
        All numeric fields are explicitly cast — Alpaca returns some as strings.
        """
        return cls(
            symbol=str(asset.symbol),
            exchange=str(asset.exchange.value) if hasattr(asset.exchange, "value") else str(asset.exchange),
            asset_class=str(asset.asset_class.value) if hasattr(asset.asset_class, "value") else str(asset.asset_class),
            tradable=bool(asset.tradable),
            fractionable=bool(asset.fractionable),
            min_order_size=float(asset.min_order_size) if asset.min_order_size is not None else 1.0,
            price_increment=float(asset.price_increment) if asset.price_increment is not None else 0.01,
            fetched_at=time.monotonic(),
            ttl_seconds=ttl_seconds,
        )

    @classmethod
    def from_dict(cls, d: dict, ttl_seconds: float = 3600.0) -> "AssetMetadata":
        """Deserialize from JSON-safe dict. fetched_at resets to now on load."""
        return cls(
            symbol=d["symbol"],
            exchange=d["exchange"],
            asset_class=d["asset_class"],
            tradable=bool(d["tradable"]),
            fractionable=bool(d["fractionable"]),
            min_order_size=float(d["min_order_size"]),
            price_increment=float(d["price_increment"]),
            fetched_at=time.monotonic(),  # reset — will revalidate within first TTL
            ttl_seconds=ttl_seconds,
        )

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict. fetched_at is excluded (not meaningful across processes)."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "asset_class": self.asset_class,
            "tradable": self.tradable,
            "fractionable": self.fractionable,
            "min_order_size": self.min_order_size,
            "price_increment": self.price_increment,
        }
