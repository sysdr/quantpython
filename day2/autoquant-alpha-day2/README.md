# AutoQuant-Alpha — Day 2: Bond Pricing Engine

## Quick Start
```bash
pip install -r requirements.txt
python -m pytest tests/ -v
python scripts/demo.py
python scripts/verify.py
python tests/stress_test.py
```

## Project Layout
```
src/
  day_count.py      — Day count conventions (30/360, Act/Act, Act/360, Act/365)
  bond_math.py      — FV, PV, discount factors, duration, YTM solver
  bond_pricer.py    — BondSpec, BondPricer, PriceResult (public API)
  dashboard.py      — Rich CLI live dashboard
  alpaca_bridge.py  — Alpaca Paper Trading ETF price fetcher
tests/
  test_bond_math.py — Unit tests (all financial math validated)
  stress_test.py    — 10,000 bond portfolio reprice benchmark
scripts/
  demo.py           — Launch live dashboard
  verify.py         — Full verification suite
diagrams/           — SVG architecture diagrams
```

## Add Alpaca credentials
Copy `.env.example` to `.env` and fill in your paper trading API keys.
