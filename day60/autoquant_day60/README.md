# AutoQuant-Alpha | Day 60: ATR-Based Volatility Slippage

## Quick Start

```bash
cp .env.example .env         # fill in your Alpaca paper keys
pip install -r requirements.txt

python scripts/demo.py --symbol AAPL --ticks 300    # synthetic demo
python scripts/start.py --symbol AAPL --quantity 1  # live paper trade
python scripts/verify.py                             # sanity checks
pytest tests/ -v                                     # full test suite
python tests/stress_test.py                          # 100K tick stress test
python scripts/cleanup.py                            # remove data files
```

## Project Structure
```
src/
  atr_engine.py       — Wilder ATR, ring buffer, vectorized batch
  slippage_model.py   — ATR-scaled slippage estimation + reconciliation
  order_logger.py     — Non-blocking JSONL order logger
  alpaca_executor.py  — End-to-end Alpaca paper execution pipeline
scripts/
  demo.py             — Rich CLI live dashboard (no API key needed)
  start.py            — Live paper trade execution
  verify.py           — Workspace sanity checks
  cleanup.py          — Remove generated data
tests/
  test_atr_engine.py  — ATR unit tests
  test_slippage_model.py — Slippage model unit tests
  stress_test.py      — 100K tick performance benchmark
data/                 — JSONL order logs (generated at runtime)
```
