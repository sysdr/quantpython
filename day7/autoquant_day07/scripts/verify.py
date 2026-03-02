#!/usr/bin/env python3
"""
Verify: parse trade_journal.jsonl and assert success criteria.
PASS: order_id present, slippage_bps < 5, latency_ms < 500.
"""
import json, sys
from pathlib import Path

journal = Path("logs/trade_journal.jsonl")
if not journal.exists():
    print("[FAIL] logs/trade_journal.jsonl not found. Run scripts/demo.py first.")
    sys.exit(1)

records = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
fills = [r for r in records if r.get("msg") == "ORDER_FILL"]

if not fills:
    print("[FAIL] No ORDER_FILL records found in journal.")
    sys.exit(1)

latest = fills[-1]
failures: list[str] = []

if not latest.get("order_id"):
    failures.append("order_id missing")

slip = latest.get("slippage_bps")
if slip is None:
    failures.append("slippage_bps missing")
elif abs(slip) >= 5.0:
    failures.append(f"slippage_bps={slip:.4f} >= 5 bps threshold")

latency = latest.get("latency_ms")
if latency is None:
    failures.append("latency_ms missing")
elif latency >= 500.0:
    failures.append(f"latency_ms={latency:.1f} >= 500 ms threshold")

if failures:
    print("[FAIL] Criteria not met:")
    for f in failures:
        print(f"  ✗ {f}")
    sys.exit(1)

print("[PASS] All success criteria met:")
print(f"  ✓ order_id   = {latest['order_id']}")
print(f"  ✓ slippage   = {latest['slippage_bps']:.4f} bps  (< 5 bps)")
print(f"  ✓ latency    = {latest['latency_ms']:.1f} ms  (< 500 ms)")
print("\nReady for Day 8: Order State Machine.")
