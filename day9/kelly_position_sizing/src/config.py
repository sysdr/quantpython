"""
Central config — loaded once at process startup from environment.
All numeric params are typed; fail-fast on bad env rather than silently using defaults.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _req(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Required env var {key!r} is not set. Copy .env.example → .env")
    return val


def _float(key: str, default: float) -> float:
    raw = os.getenv(key, str(default))
    try:
        return float(raw)
    except ValueError:
        raise EnvironmentError(f"Env var {key!r} must be a float, got {raw!r}")


def _int(key: str, default: int) -> int:
    raw = os.getenv(key, str(default))
    try:
        return int(raw)
    except ValueError:
        raise EnvironmentError(f"Env var {key!r} must be an int, got {raw!r}")


@dataclass(frozen=True, slots=True)
class Config:
    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_base_url: str

    # Kelly tuning
    kelly_fraction: float          # Fractional multiplier, typically 0.5 (half-Kelly)
    max_position_fraction: float   # Hard ceiling regardless of Kelly output
    spread_bps: float              # Assumed round-trip spread cost in basis points
    min_edge_ratio: float          # Minimum b-ratio after spread adj to allow a trade
    bootstrap_n: int               # Number of bootstrap resamples
    bootstrap_seed: int
    bootstrap_confidence_pct: float  # e.g. 5 → use p5 of bootstrap distribution

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            alpaca_api_key=_req("ALPACA_API_KEY"),
            alpaca_secret_key=_req("ALPACA_SECRET_KEY"),
            alpaca_base_url=os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
            kelly_fraction=_float("KELLY_FRACTION", 0.5),
            max_position_fraction=_float("MAX_POSITION_FRACTION", 0.15),
            spread_bps=_float("SPREAD_BPS", 5.0),
            min_edge_ratio=_float("MIN_EDGE_RATIO", 1.05),
            bootstrap_n=_int("BOOTSTRAP_N", 10_000),
            bootstrap_seed=_int("BOOTSTRAP_SEED", 42),
            bootstrap_confidence_pct=_float("BOOTSTRAP_CONFIDENCE_PCT", 5.0),
        )


# Module-level singleton — import this everywhere
CFG = Config.from_env()
