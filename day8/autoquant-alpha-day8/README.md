# AutoQuant-Alpha — Day 8: Signal Templates

## Quick Start
```bash
pip install -r requirements.txt
python scripts/demo.py        # No credentials needed
python scripts/verify.py      # Run all checks
```

## Live Trading (Paper)
```bash
cp .env.example .env
# Fill in your Alpaca paper credentials
python scripts/start.py
```

## Tests
```bash
pytest tests/test_ring_buffer.py tests/test_on_tick.py -v
python tests/stress_test.py
```

## Key Files
| File | Purpose |
|------|---------|
| `src/core/interface.py` | `OnTickInterface` ABC — the contract |
| `src/core/ring_buffer.py` | Fixed-alloc numpy ring buffer |
| `src/strategies/momentum_scalp.py` | EMA crossover implementation |
| `src/execution/order_manager.py` | Async order queue + Alpaca submit |
| `src/execution/alpaca_bridge.py` | WebSocket with reconnection |
| `src/dashboard/cli_dashboard.py` | Rich live dashboard |
