#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "AutoQuant-Alpha · Day 30 · Environment Setup"
echo "  Project root: $PROJECT_ROOT"

if [ ! -f .env ]; then
    cat > .env << 'EOF'
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
SLIPPAGE_ALERT_BPS=15.0
ORDER_FILL_TIMEOUT_S=30.0
ALPACA_QUOTE_FEED=iex
ALPACA_QUOTE_MAX_AGE_MS=604800000
EOF
    echo "  Created .env — set ALPACA_API_KEY and ALPACA_SECRET_KEY for live paper demo"
fi

pip install -r requirements.txt -q

echo "  Running unit tests..."
pytest tests/ -v --tb=short

echo "  Running stress test..."
python tests/stress_test.py

echo ""
echo "  Setup complete. Run:"
echo "    python scripts/demo.py --symbol AAPL --qty 5 --side buy"
echo "    python scripts/demo.py --dry-run"
