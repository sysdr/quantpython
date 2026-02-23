#!/usr/bin/env bash
set -euo pipefail
echo "→ Running test suite..."
docker run --rm --env-file .env autoquant-alpha:day1 python -m pytest tests/ -v
echo "→ Running stress test..."
docker run --rm --env-file .env -e PYTHONPATH=/workspace autoquant-alpha:day1 python tests/stress_test.py
echo "✓ All verification checks passed."
