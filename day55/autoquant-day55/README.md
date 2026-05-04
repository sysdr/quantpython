# AutoQuant-Alpha — Day 55: Microsecond Timing

**Week 8: The Matchmaking Engine**

Record and analyze latency for simulated order matches using
`time.perf_counter_ns()`, a lock-free ring buffer, and a Rich live dashboard.

## Quick Start

```bash
pip install -r requirements.txt
# Optional: create `.env` with ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER=true for paper API

# Run live demo (simulation mode, no keys required)
./scripts/start.sh --orders 200 --symbol AAPL
# or: python scripts/demo.py --orders 200 --symbol AAPL

# Unit tests
python -m pytest tests/test_timer.py -v

# Stress test
python tests/stress_test.py --n 1000

# Verify Day 55 success criterion
python scripts/verify.py --log data/latency_samples.jsonl
```

## Project Structure

```
autoquant-day55/
├── src/
│   ├── timer.py          # LatencySample, LatencyRecorder
│   ├── match_engine.py   # SimulatedMatchEngine (Alpaca + simulation)
│   └── dashboard.py      # Rich live CLI dashboard
├── tests/
│   ├── test_timer.py     # Unit tests
│   └── stress_test.py    # SLA stress test
├── scripts/
│   ├── demo.py           # Live demo with dashboard
│   └── verify.py         # Day 55 success criterion checker
└── data/
    └── latency_samples.jsonl  (written at runtime)
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ALPACA_API_KEY` | `""` | Paper trading key (optional) |
| `ALPACA_SECRET_KEY` | `""` | Paper trading secret (optional) |
| `ALPACA_PAPER` | `true` | Always true for this lesson |

Without keys, the engine runs in pure simulation mode.
