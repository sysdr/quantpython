#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "→ Cleaning generated data..."
rm -rf data/cold data/warm
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
echo "✓ Cleanup complete."
