#!/usr/bin/env bash
set -euo pipefail
echo "Cleaning up..."
cd "$(dirname "$0")/.."
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
rm -f logs/*.log
echo "Done."
