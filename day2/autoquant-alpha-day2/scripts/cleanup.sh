#!/usr/bin/env bash
echo "[cleanup] Removing __pycache__ and .pytest_cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
echo "[cleanup] Done."
