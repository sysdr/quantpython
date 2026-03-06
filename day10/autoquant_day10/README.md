# AutoQuant-Alpha · Day 10 · Vectorized Return Engine

## Quick Start
```bash
# Create .env with your Alpaca Paper credentials (optional for demo):
#   ALPACA_API_KEY=your_key
#   ALPACA_SECRET_KEY=your_secret
pip install -r requirements.txt
python start.py           # fetch data + compute returns (requires .env)
python demo.py            # live Rich dashboard (uses synthetic data if no .env)
python verify.py          # full test suite
python cleanup.py         # remove generated data
```

## Layout
```
autoquant_day10/
├── src/
│   ├── return_engine.py      # core vectorised computation
│   ├── data_validator.py     # gap / split / duplicate guard
│   ├── alpaca_loader.py      # Alpaca historical bar loader
│   └── dashboard.py          # Rich CLI dashboard
├── tests/
│   ├── test_return_engine.py
│   └── stress_test.py
├── data/                     # auto-created, git-ignored
├── start.py
├── demo.py
├── verify.py
└── cleanup.py
```
