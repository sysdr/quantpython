# AutoQuant-Alpha — Day 40: Fill Lifecycle Tracking

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Copy and fill credentials
cp .env.example .env && source .env

# Demo (simulates fills if no credentials; Rich live dashboard)
python scripts/demo.py
# Or from any cwd:
#   ./scripts/start_demo.sh
# CI / automation (no TTY dashboard; still writes data/lifecycle_log.jsonl):
#   AUTOQUANT_DEMO_NO_DASHBOARD=1 python scripts/demo.py

# Tests
pytest tests/ -v

# Stress test
python tests/stress_test.py

# Verify log
python scripts/verify.py data/lifecycle_log.jsonl
```

## Key Concepts

| Field | Source | Use |
|---|---|---|
| `broker_timestamp` | `data.timestamp` from Alpaca | Broker-side fill time |
| `local_receipt_at` | `datetime.now(timezone.utc)` at top of handler | Network latency baseline |
| `submission_latency_ms` | `accepted_at - submitted_at` | API round-trip |
| `fill_latency_ms` | `last_fill_at - accepted_at` | Market execution time |
| `network_latency_ms` | `local_receipt_at - last_fill_at` | Infrastructure latency |

**Never mix broker and local timestamps in a single latency formula.**

## Success Criterion

`verify.py` must output `✅ PASS` for all FILLED orders, and the log must show
`network_latency_ms < 500ms` for every fill event.
