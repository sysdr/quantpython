    # AutoQuant-Alpha | Day 3: CAGR Module

    ## Quick Start
```bash
    bash scripts/start.sh       # Install deps + copy .env.example
    # Edit .env with Alpaca Paper credentials
    python -m pytest tests/ -v  # Run test suite
    python -m src.demo          # Live Rich dashboard
    python -m src.verify --symbol SPY --tenor 1Y
    python -m src.stress_test   # 100-symbol stress test
```

    ## Project Structure
```
    autoquant_cagr/
    ├── src/
    │   ├── config.py        # Constants, logging, Alpaca config
    │   ├── cagr.py          # Core CAGR engine (pure functions)
    │   ├── data_feed.py     # Alpaca OHLCV fetch + GBM synthetic
    │   ├── dashboard.py     # Rich CLI visualizer
    │   ├── demo.py          # Entry point
    │   ├── verify.py        # Verification script
    │   └── stress_test.py   # 100-symbol stress harness
    ├── tests/
    │   └── test_cagr.py     # Unit + property tests
    ├── scripts/
    │   ├── start.sh / demo.sh / verify.sh / cleanup.sh
    ├── data/                # Reserved for cached price data
    ├── logs/                # Rotating log files (auto-created)
    └── requirements.txt
```

    ## Success Criterion
```
    [PASS] SPY 1Y CAGR: +24.31% | Computation: 1.2ms | NaN ratio: 0.000%
    [PASS] Inversion scan: 100 symbols in < 100ms
```
