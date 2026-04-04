# AutoQuant-Alpha · Day 30: Slippage-Aware Market Order Engine

## Quick Start
Create a `.env` file in the project root with your Alpaca **paper** API key and secret, for example:
`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, optional `ALPACA_QUOTE_FEED=iex`, `ALPACA_QUOTE_MAX_AGE_MS` (large value when the equity market is closed), `SLIPPAGE_ALERT_BPS`, `ORDER_FILL_TIMEOUT_S`.

```bash
pip install -r requirements.txt
pytest tests/ -v
python scripts/demo.py --symbol AAPL --qty 5 --side buy
python scripts/verify.py
```

## Project Layout
```
src/
  execution/
    market_order.py    # SlippageAwareMarketOrder
    slippage_model.py  # SlippageModel (rolling stats + regime detection)
  data/
    quote_feed.py      # QuoteFeed (live bid/ask from Alpaca)
  utils/
    logger.py          # AtomicTradeLogger (thread-safe CSV)
tests/
  test_slippage_model.py
  stress_test.py
scripts/
  demo.py              # Rich CLI dashboard — live paper trading
  verify.py            # Validate trade_log.csv
  start.sh
  cleanup.sh
data/
  trade_log.csv        # Written at runtime
```
