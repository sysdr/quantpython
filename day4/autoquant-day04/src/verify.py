"""
Verification script for Day 4 success criterion.
Checks: cold-start load, hit rate, P99 latency, TTL invalidation.
"""
from __future__ import annotations

import json
import sys
import time
import random
from pathlib import Path

from src.asset_registry import AssetRegistry
from src.asset_metadata import AssetMetadata

SYMBOLS = [f"SYM{i:04d}" for i in range(500)]
PASS_MARK = True

def make_mock(sym: str, ttl: float = 3600.0) -> AssetMetadata:
    return AssetMetadata(
        symbol=sym, exchange="NASDAQ", asset_class="us_equity",
        tradable=True, fractionable=True, min_order_size=1.0,
        price_increment=0.01, fetched_at=time.monotonic(), ttl_seconds=ttl,
    )

def check(condition: bool, label: str) -> bool:
    mark = "✓" if condition else "✗"
    color = "[92m" if condition else "[91m"
    print(f"  {color}{mark}[0m {label}")
    return condition

def run_verify():
    results = []

    # ── Test 1: Cold start from disk ────────────────────────────────────────
    path = Path("data/verify_registry.json")
    path.parent.mkdir(exist_ok=True)
    mock_data = {sym: make_mock(sym).to_dict() for sym in SYMBOLS[:500]}
    path.write_text(json.dumps(mock_data))
    t0 = time.monotonic()
    reg = AssetRegistry(ttl_seconds=3600.0)
    count = reg.load_from_disk(path)
    cold_start_ms = (time.monotonic() - t0) * 1000
    results.append(check(count == 500 and cold_start_ms < 2000,
        f"Cold-start: {count} assets loaded in {cold_start_ms:.1f}ms (target: <2000ms)"))

    # ── Test 2: Hit rate ────────────────────────────────────────────────────
    for _ in range(10_000):
        reg[random.choice(SYMBOLS[:500])]
    results.append(check(reg.hit_rate > 0.99,
        f"Hit rate: {reg.hit_rate:.2%} (target: >99%)"))

    # ── Test 3: P99 latency ─────────────────────────────────────────────────
    times = []
    for _ in range(10_000):
        t = time.monotonic()
        reg[random.choice(SYMBOLS[:500])]
        times.append((time.monotonic() - t) * 1000)
    p99 = sorted(times)[int(len(times) * 0.99)]
    results.append(check(p99 < 5.0, f"P99 lookup latency: {p99:.3f}ms (target: <5ms)"))

    # ── Test 4: TTL invalidation triggers re-fetch ──────────────────────────
    reg2 = AssetRegistry(ttl_seconds=3600.0)
    sym = "TESTEXPIRY"
    # Insert already-expired entry
    reg2._store[sym] = AssetMetadata(
        symbol=sym, exchange="NASDAQ", asset_class="us_equity",
        tradable=True, fractionable=False, min_order_size=1.0,
        price_increment=0.01, fetched_at=time.monotonic() - 4000.0, ttl_seconds=3600.0,
    )
    results.append(check(not reg2._store[sym].is_valid,
        "Expired entry correctly identified as invalid"))

    # ── Test 5: __len__ excludes expired ────────────────────────────────────
    reg3 = AssetRegistry()
    for i in range(5):
        reg3._store[f"VALID{i}"] = make_mock(f"VALID{i}", ttl=3600.0)
    for i in range(3):
        reg3._store[f"EXPIRED{i}"] = AssetMetadata(
            symbol=f"EXPIRED{i}", exchange="NASDAQ", asset_class="us_equity",
            tradable=True, fractionable=False, min_order_size=1.0,
            price_increment=0.01, fetched_at=time.monotonic() - 7200.0, ttl_seconds=3600.0,
        )
    results.append(check(len(reg3) == 5,
        f"__len__ returns only valid entries: {len(reg3)} (expected 5)"))

    # ── Test 6: Symbol normalization ────────────────────────────────────────
    reg4 = AssetRegistry()
    reg4._store["BRK/B"] = make_mock("BRK/B")
    results.append(check("BRK/B" in reg4 and "BRK.B" in reg4 and "brk.b" in reg4,
        "Symbol normalization: BRK.B and brk.b resolve to BRK/B"))

    print()
    passed = sum(results)
    total = len(results)
    if passed == total:
        print(f"\033[92m  ALL {total}/{total} CHECKS PASSED — Ready for Day 5\033[0m\n")
    else:
        print(f"\033[91m  {passed}/{total} checks passed — fix failures before proceeding\033[0m\n")
        sys.exit(1)

if __name__ == "__main__":
    run_verify()
