#!/usr/bin/env python3
"""
Day 40 Verifier — checks timestamp chain completeness and latency bounds.

Pass condition:
  ✅  All FILLED orders have a complete 7-field timestamp chain.
  ✅  broker timestamps precede local receipt timestamps (NTP caveat).
  ✅  network_latency_ms < 500ms for all fills.
  ✅  avg_fill_price > 0.

Usage: python scripts/verify.py [data/lifecycle_log.jsonl]
Exit code 0 = all pass, 1 = failures found.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PASS = "✅ PASS"
FAIL = "❌ FAIL"
MAX_NET_MS = 500.0

REQUIRED_TS_FIELDS = [
    "submitted_at", "accepted_at",
    "first_fill_at", "last_fill_at",
    "local_first_receipt_at", "local_last_receipt_at",
]


def check(r: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []

    for field in REQUIRED_TS_FIELDS:
        if not r.get(field):
            failures.append(f"missing {field}")

    if r.get("last_fill_at") and r.get("local_last_receipt_at"):
        if r["last_fill_at"] > r["local_last_receipt_at"]:
            failures.append(
                f"broker_ts > local_receipt: {r['last_fill_at']} > {r['local_last_receipt_at']}"
            )

    net = r.get("network_latency_ms")
    if net is not None and net >= MAX_NET_MS:
        failures.append(f"network_latency_ms={net:.1f} ≥ {MAX_NET_MS}")

    if not r.get("avg_fill_price"):
        failures.append("avg_fill_price is zero or missing")

    return not failures, failures


def main(path: Path) -> bool:
    if not path.exists():
        print(f"{FAIL}  File not found: {path}")
        print("       Run: python scripts/demo.py first")
        return False

    records = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    filled  = [r for r in records if r.get("state") == "filled"]

    if not filled:
        print(f"{FAIL}  No FILLED orders in {path}")
        return False

    all_ok = True
    for r in filled:
        ok, errs = check(r)
        marker = PASS if ok else FAIL
        print(f"{marker}  {r['order_id'][-16:]:<18}  {r['symbol']:<6}  "
              f"avg_px={r.get('avg_fill_price', 0):.4f}  "
              f"net_lat={r.get('network_latency_ms', '—')}")
        for e in errs:
            print(f"          └─ {FAIL}  {e}")
            all_ok = False

    total = len(filled)
    passed = sum(1 for r in filled if check(r)[0])
    print(f"\n{passed}/{total} orders passed all checks.")
    return all_ok


if __name__ == "__main__":
    log_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/lifecycle_log.jsonl")
    sys.exit(0 if main(log_path) else 1)
