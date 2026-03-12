#!/usr/bin/env bash
set -euo pipefail
echo "Cleaning workspace..."
rm -f data/dlq/dead_letters.csv
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
rm -rf .pytest_cache .ruff_cache
echo "Done."
