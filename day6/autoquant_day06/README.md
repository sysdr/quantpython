# AutoQuant-Alpha | Day 6: Resilient API Retry Wrapper

## Quick Start
```bash
pip install -e ".[dev]"
export ALPACA_API_KEY=...
export ALPACA_SECRET_KEY=...

python scripts/demo.py       # Live CLI dashboard
python scripts/verify.py     # Acceptance criteria check
pytest tests/ -v             # Full test suite
python tests/stress_test.py  # Circuit breaker stress test
python scripts/cleanup.py    # Cancel paper orders
```

## Architecture
- `src/retry_wrapper.py`  — Core: RetryWrapper + CircuitBreaker
- `src/alpaca_client.py`  — Alpaca SDK normalization layer
- `src/fault_injector.py` — Deterministic fault injection harness
- `scripts/demo.py`       — Rich live dashboard
- `scripts/verify.py`     — Automated acceptance checks
- `tests/`                — Unit + stress tests
