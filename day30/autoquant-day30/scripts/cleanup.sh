#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$(cd "$SCRIPT_DIR/.." && pwd)"
echo "Cleaning up generated data..."
rm -f data/trade_log.csv
echo "  Removed data/trade_log.csv"
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
rm -rf .pytest_cache
echo "  Cleaned __pycache__ and .pytest_cache"
echo "Done."
