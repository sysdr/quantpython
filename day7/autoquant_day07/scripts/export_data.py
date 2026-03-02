#!/usr/bin/env python3
"""
Export trade journal data in tabular format.
"""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

journal = Path("logs/trade_journal.jsonl")

if not journal.exists():
    print("Error: trade_journal.jsonl not found")
    sys.exit(1)

records = []
for line in journal.read_text().splitlines():
    if line.strip():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass

# Format as requested (most recent first)
print("Timestamp\tLevel\tMessage\tSymbol\tSide\tSlippage (bps)\tLatency (ms)")
print("=" * 100)

for r in reversed(records):
    # Parse timestamp
    ts_str = r['ts'].replace('Z', '+00:00')
    try:
        from datetime import timezone
        ts_utc = datetime.fromisoformat(ts_str)
        # Convert to local time (adjust timezone as needed)
        # For now, use UTC directly or convert to local
        ts = ts_utc.astimezone()  # Convert to local timezone
        # Format: 2/3/2026, 11:38:43 am
        # Remove leading zeros from day/month
        day = str(ts.day)
        month = str(ts.month)
        year = ts.year
        hour = ts.strftime("%-I")  # 12-hour format without leading zero
        minute = ts.strftime("%M")
        second = ts.strftime("%S")
        ampm = ts.strftime("%p").lower()
        ts_formatted = f"{day}/{month}/{year}, {hour}:{minute}:{second} {ampm}"
    except Exception as e:
        ts_formatted = r['ts']
    
    level = r.get('level', '—')
    msg = r.get('msg', '—')
    symbol = r.get('symbol', '—')
    side = r.get('side', '—')
    
    # Format slippage
    if r.get('slippage_bps') is not None:
        slippage = f"{r.get('slippage_bps'):.4f}"
    else:
        slippage = '—'
    
    # Format latency
    if r.get('latency_ms') is not None:
        latency = f"{r.get('latency_ms'):.2f}"
    else:
        latency = '—'
    
    print(f"{ts_formatted}\t{level}\t{msg}\t{symbol}\t{side}\t{slippage}\t{latency}")

