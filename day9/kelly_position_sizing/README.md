# AutoQuant-Alpha | Week 2, Day 9
## Kelly Criterion Position Sizing Engine

### Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
# Edit .env with your Alpaca paper-trading keys

# 3. Run live dashboard
python scripts/demo.py

# 4. Run verification
python scripts/verify.py

# 5. Run test suite
pytest tests/ -v

# 6. Run stress tests
python tests/stress_test.py
```

### Architecture
```
Signal Engine → KellyEstimator → PositionSizer → RiskGuard → AlpacaBroker
                     ↑
               (bootstrap p5 of win rate distribution over 10k resamples)
```

### Key Files
| File | Purpose |
|------|---------|
| `src/kelly/estimator.py` | Bootstrap Kelly estimation (vectorised) |
| `src/kelly/sizer.py` | NAV fraction + correlation haircut |
| `src/kelly/risk_guard.py` | Hard pre-trade limits |
| `src/broker/alpaca_client.py` | Async Alpaca with retry/backoff |
| `src/dashboard/cli.py` | Rich live dashboard |
| `tests/test_kelly.py` | Unit tests |
| `tests/stress_test.py` | Performance + stability tests |
