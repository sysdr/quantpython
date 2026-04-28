#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "=== AutoQuant-Alpha Day 50 Setup ==="
echo "Working directory: $ROOT"

if [ ! -f ".env" ]; then
    echo "ℹ  No .env file — project runs in simulation unless you create .env with Alpaca Paper keys."
fi

echo "Installing dependencies..."
pip install -q -r requirements.txt

echo "Running unit tests..."
python -m pytest tests/test_fill_engine.py -v --tb=short

echo ""
echo "✓  Environment ready. Run:"
echo "   python scripts/demo.py --symbol SPY --qty 10 --side buy"
echo "   python scripts/verify.py"
