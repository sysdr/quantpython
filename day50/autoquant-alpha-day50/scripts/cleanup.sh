#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo "Cleaning up data and cache..."
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find data/ -name "*.csv" -delete 2>/dev/null || true
find data/ -name "*.json" -delete 2>/dev/null || true
echo "✓  Cleanup complete."
