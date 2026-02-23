#!/usr/bin/env bash
set -euo pipefail
echo "→ Removing Docker image..."
docker rmi autoquant-alpha:day1 2>/dev/null || echo "Image not found, skipping."
echo "→ Cleaning Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
echo "✓ Cleanup complete."
